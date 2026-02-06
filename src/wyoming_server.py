"""
Wyoming Protocol Server for Piper TTS
Licensed under the MIT License.
Copyright (c) 2026 PiperTTS Mockingbird Developers

Implements the Wyoming protocol to make Piper voices compatible with Home Assistant.
This allows voices trained in Mockingbird to be used directly in Home Assistant's voice pipeline.
"""

import asyncio
import logging
import wave
import io
import json
import tempfile
import re
from pathlib import Path
from typing import Optional, Dict
from functools import partial
import subprocess

# Wyoming protocol library (install via: pip install wyoming)
try:
    from wyoming.info import Describe, Info, TtsProgram, TtsVoice, Attribution
    from wyoming.server import AsyncEventHandler, AsyncServer, AsyncTcpServer
    from wyoming.tts import Synthesize
    from wyoming.audio import AudioChunk, AudioStart, AudioStop
    from wyoming.event import Event
    WYOMING_AVAILABLE = True
except ImportError:
    WYOMING_AVAILABLE = False
    logging.warning("Wyoming library not installed. Run: pip install wyoming")

logger = logging.getLogger(__name__)


class WyomingPiperHandler(AsyncEventHandler):
    """
    Handler for Wyoming protocol events.
    Processes TTS requests and returns audio using the Piper engine.
    Inherits from Wyoming's AsyncEventHandler to properly handle the protocol.
    """
    
    def __init__(self, wyoming_info: Info, voices_dir: Path, piper_exe: Path, *args, **kwargs):
        """
        Initialize the Wyoming handler.
        
        Args:
            wyoming_info: Service info for Wyoming protocol
            voices_dir: Directory containing .onnx voice models
            piper_exe: Path to the Piper executable
        """
        super().__init__(*args, **kwargs)
        
        self.wyoming_info = wyoming_info
        self.voices_dir = voices_dir
        self.piper_exe = piper_exe
        self._voices_cache = None
        self._last_scan = 0
        self._cache_ttl = 60  # Cache voices for 60 seconds
        self.voices = self._scan_voices()
        logger.info(f"Loaded {len(self.voices)} voices for Wyoming protocol")
    
    def _scan_voices(self) -> Dict[str, Dict]:
        """Scan voices directory and build voice catalog (with caching)."""
        import time
        
        # Return cached voices if still valid
        current_time = time.time()
        if self._voices_cache is not None and (current_time - self._last_scan) < self._cache_ttl:
            return self._voices_cache
        
        voices = {}
        
        for onnx_file in self.voices_dir.glob("*.onnx"):
            # Security: Validate that file is actually within voices_dir (prevent path traversal)
            try:
                onnx_file.resolve().relative_to(self.voices_dir.resolve())
            except ValueError:
                logger.warning(f"Skipping voice outside voices directory: {onnx_file}")
                continue
            
            json_file = onnx_file.with_suffix(".onnx.json")
            
            if not json_file.exists():
                continue
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                voice_name = onnx_file.stem
                voices[voice_name] = {
                    "onnx_path": str(onnx_file),
                    "json_path": str(json_file),
                    "language": metadata.get("language", {}).get("code", "en-us"),
                    "quality": metadata.get("audio", {}).get("quality", "medium"),
                    "num_speakers": metadata.get("num_speakers", 1),
                    "sample_rate": metadata.get("audio", {}).get("sample_rate", 22050)
                }
                
            except Exception as e:
                logger.error(f"Error loading voice {onnx_file.name}: {e}")
        
        # Update cache
        self._voices_cache = voices
        self._last_scan = current_time
        
        return voices
    
    async def handle_event(self, event: Event) -> bool:
        """
        Handle incoming Wyoming events.
        
        Args:
            event: Wyoming event from client
            
        Returns:
            True if event was handled
        """
        # Handle info request (required for Home Assistant discovery)
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info.event())
            return True
        
        # Handle TTS synthesis request
        if Synthesize.is_type(event.type):
            synthesize = Synthesize.from_event(event)
            await self._handle_synthesize(synthesize)
            return True
        
        return True
    
    async def _handle_synthesize(self, synthesize: Synthesize):
        """
        Process a TTS synthesis request and send audio back to client.
        
        Args:
            synthesize: TTS request with text and voice settings
        """
        text = synthesize.text
        voice_name = synthesize.voice.name if synthesize.voice else None
        
        # Default to first available voice if none specified
        if not voice_name or voice_name not in self.voices:
            if self.voices:
                voice_name = list(self.voices.keys())[0]
            else:
                logger.error("No voices available")
                await self.write_event(AudioStop().event())
                return
        
        logger.info(f"Synthesizing with voice '{voice_name}': {text[:50]}...")
        
        try:
            # Generate speech using Piper (returns WAV file)
            wav_data = await self._synthesize_with_piper(text, voice_name)
            
            if wav_data:
                # Read WAV file to get audio properties
                with io.BytesIO(wav_data) as wav_io:
                    with wave.open(wav_io, 'rb') as wav_file:
                        rate = wav_file.getframerate()
                        width = wav_file.getsampwidth()
                        channels = wav_file.getnchannels()
                        audio_bytes = wav_file.readframes(wav_file.getnframes())
                
                # Send AudioStart event
                await self.write_event(
                    AudioStart(
                        rate=rate,
                        width=width,
                        channels=channels
                    ).event()
                )
                
                # Send audio in chunks (Wyoming protocol standard)
                chunk_size = 8192  # 8KB chunks
                for i in range(0, len(audio_bytes), chunk_size):
                    chunk = audio_bytes[i:i + chunk_size]
                    await self.write_event(
                        AudioChunk(
                            audio=chunk,
                            rate=rate,
                            width=width,
                            channels=channels
                        ).event()
                    )
                
                # Send AudioStop event
                await self.write_event(AudioStop().event())
                logger.info(f"Successfully synthesized {len(audio_bytes)} bytes")
            else:
                logger.error("Piper returned no audio data")
                await self.write_event(AudioStop().event())
                
        except Exception as e:
            logger.error(f"Synthesis failed: {e}", exc_info=True)
            await self.write_event(AudioStop().event())
    
    async def _synthesize_with_piper(self, text: str, voice_name: str) -> Optional[bytes]:
        """
        Run Piper to synthesize speech.
        
        Args:
            text: Text to synthesize
            voice_name: Voice model to use
            
        Returns:
            WAV file bytes, or None on failure
        """
        # Validate text input (max 5000 chars, sanitize dangerous chars)
        if not text or len(text) > 5000:
            logger.warning(f"Invalid text length: {len(text) if text else 0}")
            return None
        
        # Remove null bytes and control characters except newlines/tabs
        text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
        
        # Check if sanitization left any text
        if not text.strip():
            logger.warning("Text is empty after sanitization")
            return None
        
        voice_config = self.voices[voice_name]
        onnx_path = voice_config["onnx_path"]
        
        # Prepare Piper command (output to stdout as WAV)
        cmd = [
            str(self.piper_exe),
            "--model", onnx_path,
            "--output_file", "-"  # Output to stdout
        ]
        
        try:
            # Run Piper in subprocess with timeout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 30 second timeout for synthesis
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=text.encode('utf-8')),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                logger.error("Piper synthesis timed out (30s)")
                return None
            
            if process.returncode == 0:
                return stdout  # WAV file bytes
            else:
                logger.error(f"Piper error: {stderr.decode('utf-8', errors='ignore')}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to run Piper: {e}")
            return None



class WyomingPiperServer:
    """
    Wyoming protocol server for Piper TTS.
    Allows Home Assistant and other Wyoming clients to use Piper voices.
    """
    
    def __init__(self, 
                 voices_dir: Path,
                 piper_exe: Path,
                 host: str = "127.0.0.1",
                 port: int = 10200):
        """
        Initialize Wyoming server.
        
        Args:
            voices_dir: Directory with voice models
            piper_exe: Path to Piper executable
            host: Server bind address (default: localhost only. Use 0.0.0.0 for network access)
            port: Server port (default 10200 is Wyoming standard for TTS)
        """
        self.voices_dir = voices_dir
        self.piper_exe = piper_exe
        self.host = host
        self.port = port
        self.wyoming_info = self._build_info()
        self.server: Optional[AsyncServer] = None
        self._running = False
        self._server_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        # For status tracking from piper_server.py
        self.handler = type('Handler', (), {'voices': {}})()
        self._update_handler_voices()
    
    def _update_handler_voices(self):
        """Update handler voice list for status API."""
        voices = {}
        for onnx_file in self.voices_dir.rglob("*.onnx"):
            json_file = onnx_file.with_suffix(".onnx.json")
            if json_file.exists():
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    voices[onnx_file.stem] = {
                        "language": metadata.get("language", {}).get("code", "en-us")
                    }
                except (IOError, json.JSONDecodeError, KeyError) as e:
                    logger.debug(f"Could not load metadata for {onnx_file.stem}: {e}")
        self.handler.voices = voices
    
    def _build_info(self) -> Info:
        """Build service info for Wyoming describe response."""
        # Scan voices directory
        tts_voices = []
        
        for onnx_file in self.voices_dir.rglob("*.onnx"):
            # Security: Validate that file is actually within voices_dir (prevent path traversal)
            try:
                onnx_file.resolve().relative_to(self.voices_dir.resolve())
            except ValueError:
                logger.warning(f"Skipping voice outside voices directory: {onnx_file}")
                continue
            
            json_file = onnx_file.with_suffix(".onnx.json")
            
            if not json_file.exists():
                continue
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                voice_name = onnx_file.stem
                language = metadata.get("language", {}).get("code", "en-us")
                quality = metadata.get("audio", {}).get("quality", "medium")
                num_speakers = metadata.get("num_speakers", 1)
                
                # Get speaker names if available
                speakers = []
                if num_speakers > 1:
                    speaker_id_map = metadata.get("speaker_id_map", {})
                    speakers = [{"name": name} for name in speaker_id_map.keys()]
                
                tts_voices.append(
                    TtsVoice(
                        name=voice_name,
                        description=f"{quality} quality voice",
                        attribution=Attribution(
                            name="PiperTTS Mockingbird",
                            url="https://github.com/yourusername/piper_tts_server"
                        ),
                        installed=True,
                        languages=[language],
                        speakers=speakers if speakers else None,
                        version="1.0"
                    )
                )
                
            except Exception as e:
                logger.error(f"Error loading voice metadata for {onnx_file.name}: {e}")
        
        return Info(
            tts=[
                TtsProgram(
                    name="piper",
                    description="Piper neural text-to-speech via Mockingbird",
                    attribution=Attribution(
                        name="Piper TTS + Mockingbird Studio",
                        url="https://github.com/rhasspy/piper"
                    ),
                    installed=True,
                    voices=tts_voices,
                    version="1.0"
                )
            ]
        )
    
    async def start(self):
        """Start the Wyoming server."""
        async with self._lock:
            if not WYOMING_AVAILABLE:
                raise RuntimeError("Wyoming library not installed. Run: pip install wyoming")
            
            if self._running:
                logger.warning("Wyoming server already running")
                return
            
            if self.host == "0.0.0.0":
                logger.warning("⚠️  Server binding to 0.0.0.0 - accessible from entire network! Consider using 127.0.0.1 for localhost only.")
            
            logger.info(f"Starting Wyoming server on {self.host}:{self.port}")
            
            self._running = True
        
        try:
            # Create Wyoming TCP server (matching official wyoming-piper pattern)
            server = AsyncTcpServer(self.host, self.port)
            self.server = server
            
            # Run server with handler factory
            await server.run(
                partial(
                    WyomingPiperHandler,
                    self.wyoming_info,
                    self.voices_dir,
                    self.piper_exe
                )
            )
                        
        except asyncio.CancelledError:
            logger.info("Wyoming server cancelled")
        except Exception as e:
            logger.error(f"Wyoming server error: {e}", exc_info=True)
            raise
        finally:
            async with self._lock:
                self._running = False
                self.server = None
            logger.info("Wyoming server stopped")
    
    async def stop(self):
        """Stop the Wyoming server."""
        async with self._lock:
            if not self._running:
                logger.warning("Wyoming server not running")
                return
            
            logger.info("Stopping Wyoming server...")
            self._running = False
        
        # Cancel the server task if it exists
        if self._server_task and not self._server_task.done():
            self._server_task.cancel()
            try:
                await asyncio.wait_for(self._server_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Wyoming server shutdown timed out after 5s")
            except asyncio.CancelledError:
                pass
    
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running



# Convenience function to run server from command line
async def main():
    """Run Wyoming server standalone."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Wyoming Protocol Server for Piper")
    parser.add_argument("--voices-dir", type=Path, default=Path("voices"),
                        help="Directory containing voice models")
    parser.add_argument("--piper-exe", type=Path, default=Path("src/piper/piper.exe"),
                        help="Path to Piper executable")
    parser.add_argument("--host", default="127.0.0.1", help="Server host (use 0.0.0.0 for network access)")
    parser.add_argument("--port", type=int, default=10200, help="Server port")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    
    # Create and start server
    server = WyomingPiperServer(
        voices_dir=args.voices_dir,
        piper_exe=args.piper_exe,
        host=args.host,
        port=args.port
    )
    
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
