"""
Piper TTS Server - Local Text-to-Speech API
Licensed under the MIT License.
Copyright (c) 2026 PiperTTS Mockingbird Developers
"""

from __future__ import annotations

import json
import os
import sys
import subprocess
import tempfile
import threading
import time
import re
import asyncio
from pathlib import Path

from fastapi import FastAPI, Response, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Optional
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import shutil
import urllib.request
import zipfile
import io
from logging.handlers import RotatingFileHandler
from training_manager import training_manager

# Common utilities for sanitization and config management
from common_utils import validate_voice_name, safe_config_save, safe_config_load

# Home Assistant & Wyoming integration imports
from ha_export import HomeAssistantExporter
from wyoming_server import WyomingPiperServer

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).resolve().parent

# Root folder where Piper training "dojos" live.
DOJO_ROOT = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo"


def _validate_voice_name(voice: str) -> str:
    """Wrapper for the common sanitization utility."""
    return validate_voice_name(voice)

# Setup logging
LOGS_DIR = SCRIPT_DIR.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

log_file = LOGS_DIR / "server.log"
error_log_file = LOGS_DIR / "errors.log"

# Create formatters
detailed_formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
simple_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# Main log handler (INFO and above)
main_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
main_handler.setLevel(logging.INFO)
main_handler.setFormatter(detailed_formatter)

# Error log handler (ERROR and above only) - shared across all components
error_handler = RotatingFileHandler(error_log_file, maxBytes=5*1024*1024, backupCount=3)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(detailed_formatter)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(simple_formatter)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[main_handler, error_handler, console_handler]
)

logger = logging.getLogger("piper_server")

# Initialize FastAPI application
app = FastAPI(
    title="PiperTTS Mockingbird API",
    description="Local, private text-to-speech server with custom voice training",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Security headers middleware (invisible protection)
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

# API Key authentication middleware (opt-in for production security)
# By default, no authentication is required for local development (zero-config)
# To enable: set PIPER_API_KEY="your-custom-key" in .env or environment
# The server is protected by CORS and localhost binding by default
DEFAULT_API_KEY = ""
API_KEY = os.getenv("PIPER_API_KEY", DEFAULT_API_KEY).strip()

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip authentication if no API key is configured
        if not API_KEY:
            return await call_next(request)
        
        # Allow health check and docs without authentication
        if request.url.path in ["/", "/health", "/api/docs", "/api/redoc", "/api/openapi.json"]:
            return await call_next(request)
        
        # Check for API key in header or query parameter
        provided_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        
        if provided_key != API_KEY:
            return Response(content="Unauthorized: Invalid or missing API key", status_code=401)
        
        return await call_next(request)

app.add_middleware(APIKeyMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# CORS restricted to localhost and local network for developer-friendly security
# Allows localhost, 127.0.0.1, IPv6 localhost, and private network ranges (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://((localhost|127\.0\.0\.1|\[::\]|0\.0\.0\.0)|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3})(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional environment variable overrides:
# - PIPER_MODEL: full path to a .onnx model to use as default
# - PIPER_SPEAKER: speaker id/name for multi-speaker voices
# - PIPER_EXE: full path to the piper executable
PIPER_MODEL_ENV = "PIPER_MODEL"
PIPER_SPEAKER_ENV = "PIPER_SPEAKER"
PIPER_EXE_ENV = "PIPER_EXE"
PIPER_SENTENCE_SILENCE_ENV = "PIPER_SENTENCE_SILENCE"

# Default piper executable name or path from environment
PIPER_EXE = os.environ.get(PIPER_EXE_ENV, "piper")

# Timeout configuration
REQUEST_TIMEOUT_SECONDS = 30  # Maximum time for a single TTS request
PROCESS_IDLE_TIMEOUT_SECONDS = 120  # Clean up processes idle for 2 minutes (memory optimization)
MAX_CONCURRENT_PROCESSES = int(os.environ.get("PIPER_MAX_PROCESSES", "3"))  # Limit concurrent voice processes
MAX_TEXT_LENGTH = int(os.environ.get("PIPER_MAX_TEXT_LENGTH", "100000"))  # Max characters (will be chunked)
CHUNK_SIZE = int(os.environ.get("PIPER_CHUNK_SIZE", "5000"))  # Characters per chunk for long texts

# Default model to prefer if multiple are found
PREFERRED_MODEL = "en_US-hfc_female-medium.onnx"

# Keywords to identify female voices in filenames
FEMALE_VOICE_HINTS = [
    "female",
    "amy",
    "ljspeech",
    "kathleen",
    "jenny",
]

STARTER_MODELS = {
    "Ryan (High)": {
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx?download=true",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx.json?download=true",
        "rel_path": "voices/Ryan/en_US-ryan-high.onnx"
    },
    "Cori (High)": {
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/cori/high/en_GB-cori-high.onnx?download=true",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/cori/high/en_GB-cori-high.onnx.json?download=true",
        "rel_path": "voices/Cori/en_GB-cori-high.onnx"
    },
    "Female (Medium)": {
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx?download=true",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx.json?download=true",
        "rel_path": "voices/female/en_US-hfc_female-medium.onnx"
    },
    "Male (Medium)": {
        "onnx_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_male/medium/en_US-hfc_male-medium.onnx?download=true",
        "json_url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_male/medium/en_US-hfc_male-medium.onnx.json?download=true",
        "rel_path": "voices/male/en_US-hfc_male-medium.onnx"
    }
}

# Cache for available models to avoid frequent disk scans
_MODEL_CACHE: list[Path] = []
_LAST_CACHE_UPDATE: float = 0

# Cache for model configurations (sample rates, etc.) to avoid repeated JSON reads
_MODEL_CONFIG_CACHE: dict[str, dict] = {}  # model_path -> config_dict
_CONFIG_CACHE_TTL = 300  # Cache configs for 5 minutes
_CONFIG_CACHE_MAX_SIZE = 100  # Maximum number of cached configs

# Pre-compiled regex patterns for performance
_PARAGRAPH_SPLIT_PATTERN = re.compile(r'\n\s*\n|\n(?=\s{2,})')
_SENTENCE_SPLIT_PATTERN = re.compile(r'([.!?]+(?:[\s"\')]|$))')
_INVISIBLE_CHARS = ['\u200b', '\u200c', '\u200d', '\ufeff']


class TTSReq(BaseModel):
    """Request model for the TTS endpoint."""
    text: str
    voice_model: str | None = None
    stream: bool = False


class NicknameReq(BaseModel):
    """Request model for setting a voice nickname."""
    voice_name: str
    nickname: str


class ErrorResponse(BaseModel):
    """Standard error response format."""
    success: bool = False
    error: str
    error_code: str | None = None


class VoiceInfo(BaseModel):
    """Details about a playable voice model."""
    name: str
    path: str
    size: int
    nickname: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""
    ok: bool
    version: str = "1.0.0"
    uptime_seconds: float
    loaded_voices: int
    memory_mb: float | None = None
    stuck_processes: int = 0
    available_voices: list[VoiceInfo] = []
    model: str | None = None


class VoicesResponse(BaseModel):
    """Voice list response."""
    success: bool
    voices: list[str]
    count: int


NICKNAMES_FILE = SCRIPT_DIR / "nicknames.json"
_NICKNAMES_CACHE: dict[str, str] | None = None
_NICKNAMES_CACHE_MTIME: float = 0

def load_nicknames() -> dict[str, str]:
    """Load nicknames from disk with caching based on file modification time."""
    global _NICKNAMES_CACHE, _NICKNAMES_CACHE_MTIME
    
    if NICKNAMES_FILE.exists():
        try:
            current_mtime = NICKNAMES_FILE.stat().st_mtime
            # Use cached version if file hasn't changed
            if _NICKNAMES_CACHE is not None and current_mtime == _NICKNAMES_CACHE_MTIME:
                return _NICKNAMES_CACHE
            
            # Load fresh data
            nicknames = json.loads(NICKNAMES_FILE.read_text(encoding="utf-8"))
            _NICKNAMES_CACHE = nicknames
            _NICKNAMES_CACHE_MTIME = current_mtime
            return nicknames
        except Exception:
            pass
    
    # Return cached version if file is gone but we have cache
    if _NICKNAMES_CACHE is not None:
        return _NICKNAMES_CACHE
    
    return {}

def save_nicknames(nicknames: dict[str, str]):
    """Save nicknames to disk with backup protection."""
    global _NICKNAMES_CACHE, _NICKNAMES_CACHE_MTIME
    if not safe_config_save(NICKNAMES_FILE, nicknames):
        logger.error(f"Failed to save nicknames to {NICKNAMES_FILE}")
    else:
        # Update cache after successful save
        _NICKNAMES_CACHE = nicknames.copy()
        if NICKNAMES_FILE.exists():
            _NICKNAMES_CACHE_MTIME = NICKNAMES_FILE.stat().st_mtime


def _cleanup_model_config_cache():
    """Remove expired entries from model config cache using LRU eviction."""
    global _MODEL_CONFIG_CACHE
    
    now = time.time()
    # Remove expired entries
    expired_keys = [
        k for k, v in _MODEL_CONFIG_CACHE.items()
        if 'cached_at' in v and (now - v['cached_at']) > _CONFIG_CACHE_TTL
    ]
    
    for key in expired_keys:
        del _MODEL_CONFIG_CACHE[key]
    
    # If still over limit, remove oldest entries (LRU)
    if len(_MODEL_CONFIG_CACHE) > _CONFIG_CACHE_MAX_SIZE:
        sorted_items = sorted(
            _MODEL_CONFIG_CACHE.items(),
            key=lambda x: x[1].get('cached_at', 0)
        )
        # Keep only the newest MAX_SIZE entries
        keys_to_remove = [k for k, v in sorted_items[:len(_MODEL_CONFIG_CACHE) - _CONFIG_CACHE_MAX_SIZE]]
        for key in keys_to_remove:
            del _MODEL_CONFIG_CACHE[key]
        
        if keys_to_remove:
            logger.debug(f"Evicted {len(keys_to_remove)} old config cache entries")


def get_model_config(config_path: Path) -> dict:
    """Load model configuration with caching to avoid repeated file reads.
    
    Returns cached config if available and fresh, otherwise reads from disk.
    """
    global _MODEL_CONFIG_CACHE
    
    cache_key = str(config_path.resolve())
    
    # Check if we have a cached version
    if cache_key in _MODEL_CONFIG_CACHE:
        cached = _MODEL_CONFIG_CACHE[cache_key]
        # Check if cache is still fresh (check both time and file modification)
        if 'cached_at' in cached and 'mtime' in cached:
            age = time.time() - cached['cached_at']
            try:
                current_mtime = config_path.stat().st_mtime
                if age < _CONFIG_CACHE_TTL and current_mtime == cached['mtime']:
                    # Update last access time for LRU
                    cached['cached_at'] = time.time()
                    return cached['config']
            except (OSError, FileNotFoundError):
                pass
    
    # Cleanup cache periodically (every 50 accesses to avoid overhead)
    if len(_MODEL_CONFIG_CACHE) % 50 == 0 and len(_MODEL_CONFIG_CACHE) > 0:
        _cleanup_model_config_cache()
    
    # Load from disk
    try:
        config_data = json.loads(config_path.read_text(encoding="utf-8"))
        mtime = config_path.stat().st_mtime
        
        # Cache it
        _MODEL_CONFIG_CACHE[cache_key] = {
            'config': config_data,
            'cached_at': time.time(),
            'mtime': mtime
        }
        
        return config_data
    except Exception as e:
        logger.warning(f"Failed to load model config from {config_path}: {e}")
        return {}


def sanitize_text_input(text: str) -> str:
    """Remove dangerous control characters while preserving legitimate Unicode.
    
    Only removes null bytes and other truly dangerous characters that could break Piper.
    Preserves Unicode characters for international text support.
    """
    if not text:
        return text
    # Only remove null bytes and a few truly problematic control characters
    # Preserve most Unicode including international characters
    sanitized = text.replace('\x00', '')  # Null byte
    sanitized = sanitized.replace('\x0b', '')  # Vertical tab
    sanitized = sanitized.replace('\x0c', '')  # Form feed
    # Optionally remove zero-width characters (can cause confusion but usually harmless)
    # Comment out if you need these for certain languages
    for char in _INVISIBLE_CHARS:
        sanitized = sanitized.replace(char, '')
    return sanitized


def chunk_text(text: str, max_chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into chunks at sentence boundaries for better TTS.
    
    Optimized to respect paragraph breaks and natural sentence boundaries.
    Uses pre-compiled regex patterns for better performance.
    """
    if len(text) <= max_chunk_size:
        return [text]
    
    # First try to split by paragraphs (double newlines or single newlines with indentation)
    paragraphs = _PARAGRAPH_SPLIT_PATTERN.split(text)
    
    chunks = []
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        # If paragraph fits in current chunk, add it
        if current_chunk and len(current_chunk) + len(para) + 2 <= max_chunk_size:
            current_chunk += "\n\n" + para
        # If paragraph alone is small enough, start new chunk with it
        elif len(para) <= max_chunk_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = para
        # If paragraph is too large, split by sentences
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            # Split paragraph by sentences
            sentences = _SENTENCE_SPLIT_PATTERN.split(para)
            for i in range(0, len(sentences), 2):
                sentence = sentences[i]
                separator = sentences[i + 1] if i + 1 < len(sentences) else ""
                
                if not sentence.strip():
                    continue
                
                # If sentence fits in current chunk, add it
                if len(current_chunk) + len(sentence) + len(separator) <= max_chunk_size:
                    current_chunk += sentence + separator
                else:
                    # Chunk is full, save it and start new one
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    # If single sentence exceeds chunk size, force split
                    if len(sentence + separator) > max_chunk_size:
                        for j in range(0, len(sentence), max_chunk_size):
                            chunks.append(sentence[j:j+max_chunk_size])
                        current_chunk = ""
                    else:
                        current_chunk = sentence + separator
    
    # Add any remaining text
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    # Fallback: if no chunks were created, force split by size
    if not chunks:
        chunks = [text[i:i+max_chunk_size] for i in range(0, len(text), max_chunk_size)]
    
    return chunks


def concatenate_wav_files(wav_chunks: list[bytes]) -> bytes:
    """Concatenate multiple WAV files into a single WAV file.
    
    Optimized for memory efficiency - streams frames instead of loading all at once.
    """
    if not wav_chunks:
        return b""
    if len(wav_chunks) == 1:
        return wav_chunks[0]
    
    import wave
    
    # Read first WAV to get parameters
    first_wav = io.BytesIO(wav_chunks[0])
    params = None
    
    # Create output buffer
    output = io.BytesIO()
    
    with wave.open(output, 'wb') as out_wf:
        # Process first chunk to get parameters
        with wave.open(first_wav, 'rb') as wf:
            params = wf.getparams()
            out_wf.setparams(params)
            # Stream frames in chunks to reduce memory usage
            while True:
                frames = wf.readframes(4096)  # Read in smaller chunks
                if not frames:
                    break
                out_wf.writeframes(frames)
        
        # Process remaining chunks
        for wav_data in wav_chunks[1:]:
            wav_io = io.BytesIO(wav_data)
            with wave.open(wav_io, 'rb') as wf:
                # Stream frames instead of loading all at once
                while True:
                    frames = wf.readframes(4096)
                    if not frames:
                        break
                    out_wf.writeframes(frames)
    
    return output.getvalue()



class PiperProcess:
    """Manages a persistent Piper process for faster synthesis."""
    def __init__(self, model_path, config_path, speaker, piper_exe, cwd):
        self.model_path = model_path
        self.config_path = config_path
        self.speaker = speaker
        self.piper_exe = piper_exe
        self.cwd = cwd
        self.process = None
        self.lock = threading.Lock()
        self.last_used = time.time()
        self.processing_start = None
        self.cancel_current = False  # Flag to cancel current synthesis
        self.active_request_id = None  # Track active request for cancellation

    def ensure_started(self):
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                logger.info(f"Starting persistent process for {self.model_path.name}...")
                cmd = [self.piper_exe, "--model", str(self.model_path), "--json-input"]
                if self.config_path and self.config_path.exists():
                    cmd += ["--config", str(self.config_path)]
                if self.speaker:
                    # Validate speaker parameter to prevent command injection
                    # Allow alphanumeric, underscores, hyphens, dots, and spaces (common in speaker names)
                    if not re.match(r'^[a-zA-Z0-9_\-\. ]+$', str(self.speaker)):
                        logger.error(f"Invalid speaker parameter: {self.speaker}")
                        raise ValueError(f"Invalid speaker parameter format")
                    cmd += ["--speaker", str(self.speaker)]

                # Reduce (or eliminate) built-in pauses between sentences.
                # Default Piper is ~0.2s which can feel choppy when we split text.
                sentence_silence = get_sentence_silence_seconds()
                if sentence_silence is not None:
                    cmd += ["--sentence_silence", str(sentence_silence)]
                
                logger.info(f"Command: {cmd}")
                
                popen_kwargs = {}
                if os.name == "nt":
                    popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    try:
                        si = subprocess.STARTUPINFO()
                        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        si.wShowWindow = subprocess.SW_HIDE
                        popen_kwargs["startupinfo"] = si
                    except Exception:
                        pass

                try:
                    self.process = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=self.cwd,
                        **popen_kwargs
                    )
                    self.last_used = time.time()
                    logger.info("Process started successfully.")
                except Exception as e:
                    logger.error(f"Failed to start Piper process: {e}")
                    raise

    def stop(self):
        """Stops the underlying Piper process with proper cleanup."""
        if self.process:
            try:
                # Try graceful termination first
                self.process.terminate()
                try:
                    self.process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    # Force kill if terminate doesn't work
                    logger.warning(f"Process for {self.model_path.name} didn't terminate gracefully, forcing kill")
                    self.process.kill()
                    self.process.wait(timeout=1.0)
                
                # Close pipes to free resources
                if self.process.stdin:
                    try:
                        self.process.stdin.close()
                    except Exception:
                        pass
                if self.process.stdout:
                    try:
                        self.process.stdout.close()
                    except Exception:
                        pass
                if self.process.stderr:
                    try:
                        self.process.stderr.close()
                    except Exception:
                        pass
                        
            except Exception as e:
                logger.error(f"Error stopping process for {self.model_path.name}: {e}")
            finally:
                self.process = None
    
    def cancel_synthesis(self):
        """Cancel the current synthesis operation (but keep process alive)."""
        with self.lock:
            self.cancel_current = True
            logger.info(f"Cancellation requested for {self.model_path.name}")

    def synthesize(self, text, request_id=None):
        self.ensure_started()
        with self.lock:
            # Cancel any previous request for this process
            if self.active_request_id and self.active_request_id != request_id:
                logger.info(f"New request {request_id} canceling old request {self.active_request_id}")
                self.cancel_current = True
            
            self.active_request_id = request_id
            self.cancel_current = False  # Reset cancellation flag for new request
            self.last_used = time.time()
            self.processing_start = time.time()
            
            # Create a temp file for this request (will be cleaned up in finally block)
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav")
            os.close(tmp_fd)  # Close file descriptor immediately, Piper will write to it
            
            try:
                # Check if cancelled before starting
                if self.cancel_current:
                    logger.info(f"Synthesis cancelled before starting (request {request_id})")
                    raise Exception("Synthesis cancelled")
                
                # Clean text for JSON
                clean_text = text.strip()
                if not clean_text:
                    return b""
                
                logger.info(f"Synthesizing text (request {request_id}, len={len(clean_text)}): {clean_text[:50]}...")
                
                req = {"text": clean_text, "output_file": tmp_path}
                try:
                    self.process.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
                    self.process.stdin.flush()
                except Exception as e:
                    logger.error(f"Error writing to Piper stdin: {e}")
                    # Try to read stderr to see what happened
                    stderr_out = self.process.stderr.read() if self.process.stderr else b""
                    logger.error(f"Piper stderr: {stderr_out}")
                    self.process = None # Force restart next time
                    raise
                
                # Check if cancelled while writing
                if self.cancel_current:
                    logger.info(f"Synthesis cancelled during write (request {request_id})")
                    raise Exception("Synthesis cancelled")
                
                # Piper outputs the filename to stdout when done
                # Check for timeout
                start_time = time.time()
                while True:
                    if self.cancel_current:
                        logger.info(f"Synthesis cancelled while waiting for output (request {request_id})")
                        raise Exception("Synthesis cancelled")
                    
                    elapsed = time.time() - start_time
                    if elapsed > REQUEST_TIMEOUT_SECONDS:
                        logger.error(f"Request timeout after {elapsed:.1f}s (request {request_id})")
                        self.process = None  # Force restart
                        raise Exception(f"TTS request timed out after {REQUEST_TIMEOUT_SECONDS}s")
                    
                    # Try reading with a short timeout
                    import select
                    # Windows doesn't support select() on pipes/file descriptors, only on sockets.
                    if os.name != 'nt' and hasattr(select, 'select'):
                        ready, _, _ = select.select([self.process.stdout], [], [], 0.1)
                        if ready:
                            line = self.process.stdout.readline().decode("utf-8").strip()
                            break
                    else:
                        # Windows or systems without select(): fallback to blocking read.
                        # This means cancellation won't be checked during the actual synthesis, 
                        # but it prevents the WinError 10038 crash.
                        line = self.process.stdout.readline().decode("utf-8").strip()
                        break
                
                if not line:
                    # Process might have died
                    stderr_out = self.process.stderr.read() if self.process.stderr else b""
                    logger.error(f"Piper process terminated unexpectedly. Stderr: {stderr_out}")
                    self.process = None
                    raise Exception("Piper process terminated unexpectedly")
                
                # On Windows, Piper might output the path with different slashes or relative
                # We just check if it's non-empty for now, or matches the end
                if not line.endswith(os.path.basename(tmp_path)):
                    logger.warning(f"Unexpected output from Piper: {line}")
                
                # Check if cancelled after synthesis but before reading
                if self.cancel_current:
                    logger.info(f"Synthesis cancelled after completion (request {request_id})")
                    raise Exception("Synthesis cancelled")

                with open(tmp_path, "rb") as f:
                    logger.info(f"Synthesis complete for request {request_id}.")
                    return f.read()
            except Exception as e:
                logger.error(f"Synthesis failed: {e}")
                raise
            finally:
                self.processing_start = None
                self.active_request_id = None
                self.cancel_current = False
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except:
                        pass

class PiperManager:
    """Manages multiple Piper processes."""
    def __init__(self):
        self.processes = {}
        self.lock = threading.Lock()
        self._start_cleanup_thread()

    def get_process(self, model_path, config_path, speaker, piper_exe, cwd) -> PiperProcess:
        key = (str(model_path), speaker)
        with self.lock:
            if key not in self.processes:
                # Enforce process limit to prevent memory bloat
                if len(self.processes) >= MAX_CONCURRENT_PROCESSES:
                    logger.warning(f"Process limit ({MAX_CONCURRENT_PROCESSES}) reached. Cleaning oldest idle process.")
                    self._evict_oldest_idle_process()
                self.processes[key] = PiperProcess(model_path, config_path, speaker, piper_exe, cwd)
            return self.processes[key]
    
    def _evict_oldest_idle_process(self):
        """Evict the oldest idle process to free memory (called with lock held)."""
        oldest_key = None
        oldest_time = float('inf')
        
        for key, process in self.processes.items():
            # Skip if currently processing
            if process.processing_start is not None:
                continue
            if process.last_used < oldest_time:
                oldest_time = process.last_used
                oldest_key = key
        
        if oldest_key:
            logger.info(f"Evicting idle process {oldest_key} to stay within limit")
            self.processes[oldest_key].stop()
            del self.processes[oldest_key]
    
    def _start_cleanup_thread(self):
        """Starts a background thread to clean up idle processes."""
        def cleanup_idle_processes():
            while True:
                time.sleep(60)  # Check every minute
                try:
                    now = time.time()
                    to_remove = []
                    
                    with self.lock:
                        for key, process in self.processes.items():
                            # Don't clean up if currently processing
                            if process.processing_start is not None:
                                # Invisible security: Kill processes stuck for more than 5 minutes
                                if now - process.processing_start > 300:
                                    logger.warning(f"Force-killing stuck process {key} (running for {now - process.processing_start:.0f}s)")
                                    process.stop()
                                    to_remove.append(key)
                                continue
                            
                            idle_time = now - process.last_used
                            if idle_time > PROCESS_IDLE_TIMEOUT_SECONDS:
                                logger.info(f"Cleaning up idle process {key} (idle for {idle_time:.0f}s)")
                                process.stop()
                                to_remove.append(key)
                        
                        for key in to_remove:
                            del self.processes[key]
                    
                    if to_remove:
                        logger.info(f"Cleaned up {len(to_remove)} idle process(es)")
                except Exception as e:
                    logger.error(f"Error in cleanup thread: {e}")
        
        thread = threading.Thread(target=cleanup_idle_processes, daemon=True, name="ProcessCleanup")
        thread.start()
        logger.info(f"Started process cleanup thread (idle timeout: {PROCESS_IDLE_TIMEOUT_SECONDS}s)")

manager = PiperManager()


def get_sentence_silence_seconds() -> float | None:
    """Returns the Piper --sentence_silence value (seconds), or None to use Piper defaults."""
    raw = os.environ.get(PIPER_SENTENCE_SILENCE_ENV, "0").strip()
    if raw == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    if value < 0:
        return 0.0
    return value


def format_bytes(size: int) -> str:
    """Formats bytes into human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def cors_headers() -> dict[str, str]:
    """Backward-compatible CORS header helper.

    We primarily rely on CORSMiddleware now, but some routes still reference
    this helper.
    """
    return {}


_PIPER_EXE_CACHE = None

def resolve_piper_exe() -> str:
    """
    Locate the Piper executable (Cached).
    """
    global _PIPER_EXE_CACHE
    if _PIPER_EXE_CACHE:
        return _PIPER_EXE_CACHE

    exe_name = "piper.exe" if os.name == "nt" else "piper"

    # 1) next to this script
    local_exe = SCRIPT_DIR / exe_name
    if local_exe.exists():
        _PIPER_EXE_CACHE = str(local_exe)
        return _PIPER_EXE_CACHE

    # 2) ./piper/piper.exe (common zip extraction)
    subfolder_exe = SCRIPT_DIR / "piper" / exe_name
    if subfolder_exe.exists():
        _PIPER_EXE_CACHE = str(subfolder_exe)
        return _PIPER_EXE_CACHE

    # 3) Try to auto-download if missing
    try:
        # Only try download if we really can't find it and it's not in PATH (simple check)
        if shutil.which(exe_name) is None: 
            logger.info("Piper executable not found. Attempting to download...")
            from download_piper import download_and_extract_piper
            if download_and_extract_piper(SCRIPT_DIR):
                # Check again after download
                if subfolder_exe.exists():
                    _PIPER_EXE_CACHE = str(subfolder_exe)
                    return _PIPER_EXE_CACHE
                nested_exe = SCRIPT_DIR / "piper" / "piper" / exe_name
                if nested_exe.exists():
                     _PIPER_EXE_CACHE = str(nested_exe)
                     return _PIPER_EXE_CACHE
    except Exception as e:
        logger.error(f"Failed to auto-download Piper: {e}")

    # 4) env var override
    if PIPER_EXE and PIPER_EXE != "piper":
        _PIPER_EXE_CACHE = PIPER_EXE
        return PIPER_EXE

    # 5) hope it's on PATH
    _PIPER_EXE_CACHE = "piper"
    return "piper"


_MODEL_MAP_CACHE: dict[str, Path] = {}  # Map filename -> Path
_LAST_CACHE_UPDATE: float = 0
_VOICES_DIR_MTIME: float = 0  # Track modification time of voices directory


def invalidate_voice_cache() -> None:
    """Force the next request to rescan disk for available .onnx voices."""
    global _MODEL_MAP_CACHE, _LAST_CACHE_UPDATE, _VOICES_DIR_MTIME
    _MODEL_MAP_CACHE = {}
    _LAST_CACHE_UPDATE = 0
    _VOICES_DIR_MTIME = 0


def get_size_bytes(path: Path) -> int:
    """Robustly calculates size in bytes for a file or directory."""
    total = 0
    try:
        if not path.exists(): return 0
        if path.is_file(): return path.stat().st_size
        for root, dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except (OSError, PermissionError):
                    continue
    except Exception:
        pass
    return total


def get_model_path_by_name(name: str) -> Path | None:
    """Efficiently lookup a model path by name.

    Supports:
    - Filename (e.g. 'en_US-amy-medium.onnx')
    - Stem (e.g. 'en_US-amy-medium')
    - Parent folder alias (e.g. 'Cori')
    - Nested relative alias (e.g. 'custom/myteam/voice')
    
    Uses filesystem modification time for intelligent cache invalidation.
    """
    global _MODEL_MAP_CACHE, _LAST_CACHE_UPDATE, _VOICES_DIR_MTIME
    
    # Check if voices directory has been modified
    voices_dir = SCRIPT_DIR.parent / "voices"
    should_refresh = not _MODEL_MAP_CACHE
    
    if voices_dir.exists():
        try:
            current_mtime = voices_dir.stat().st_mtime
            if current_mtime != _VOICES_DIR_MTIME:
                should_refresh = True
                _VOICES_DIR_MTIME = current_mtime
        except (OSError, PermissionError):
            pass
    
    # Also refresh if cache is older than 5 minutes (fallback)
    now = time.time()
    if now - _LAST_CACHE_UPDATE > 300:
        should_refresh = True
    
    # Refresh if needed
    if should_refresh:
        new_map = {}
        search_roots = [(SCRIPT_DIR.parent / "voices", True), (SCRIPT_DIR, False)]
        
        for root, recursive in search_roots:
            if not root.exists(): continue
            
            pattern = "*.onnx"
            iterator = root.rglob(pattern) if recursive else root.glob(pattern)
            
            for path in iterator:
                if ".venv" in path.parts or any(p.startswith(".") for p in path.parts if p != "."):
                     continue
                
                # 1. Map by filename (e.g. amy.onnx)
                if path.name not in new_map:
                    new_map[path.name] = path

                # 1b. Map by stem (e.g. amy)
                if path.stem not in new_map:
                    new_map[path.stem] = path
                
                # 2. Map by direct parent directory name (e.g. voices/Cori/cori.onnx -> "Cori")
                # This handles the standard Piper folder structure.
                if path.parent != root:
                    parent_name = path.parent.name
                    if parent_name not in new_map:
                        new_map[parent_name] = path
                
                # 3. Map by relative path from voices/ for nested custom voices
                # e.g. voices/custom/myteam/voice.onnx -> "custom/myteam"
                try:
                    rel_p = str(path.relative_to(root).with_suffix("")).replace("\\", "/")
                    if rel_p not in new_map:
                        new_map[rel_p] = path
                except Exception:
                    pass
        
        _MODEL_MAP_CACHE = new_map
        _LAST_CACHE_UPDATE = now

    return _MODEL_MAP_CACHE.get(name)

def iter_candidate_models():
    """Generator that yields paths to all .onnx models found in standard locations."""
    # Ensure cache is populated
    get_model_path_by_name("ensure_cache") 
    # Use a set to de-duplicate paths, as the cache may have multiple keys for one path
    seen = set()
    for path in _MODEL_MAP_CACHE.values():
        abs_p = str(path.resolve())
        if abs_p not in seen:
            seen.add(abs_p)
            yield path


@app.post("/api/reload-voices", tags=["Voice Management"])
def reload_voices():
    """
    Invalidate the voice cache and rescan for new models.
    
    Use this after adding new voices or exporting trained models.
    Returns the count of available voices after refresh.
    """
    invalidate_voice_cache()
    # Force a scan now so callers can rely on immediate availability.
    get_model_path_by_name("ensure_cache")
    return {"ok": True, "count": len(_MODEL_MAP_CACHE)}


@app.get("/api/voices", response_model=VoicesResponse, tags=["Voice Management"])
def list_voices():
    """
    Get a lightweight list of available voice names.
    
    Perfect for:
    - Connection checks
    - Populating voice selector dropdowns
    - Quick availability checks
    
    For detailed voice info including training status, use `/api/dojos`.
    """
    try:
        # Refresh voice cache logic
        get_model_path_by_name("ensure_cache")
        
        # Extract unique voice names
        voices = sorted(list({p.stem for p in iter_candidate_models()}))
        
        return VoicesResponse(success=True, voices=voices, count=len(voices))
    except Exception as e:
        logger.error(f"Error listing voices: {e}")
        return VoicesResponse(success=False, voices=[], count=0)


def load_config() -> dict:
    """Load config.json safely with backup recovery."""
    config_path = SCRIPT_DIR / "config.json"
    return safe_config_load(config_path)


def resolve_model_path(requested_voice: str | None = None) -> Path:
    """
    Determine which .onnx model to use for synthesis.
    Priority:
    1. requested_voice (if provided in the API call)
    2. PIPER_MODEL environment variable
    3. voice_model setting in config.json
    4. PREFERRED_MODEL (en_US-hfc_female-medium.onnx)
    5. First model containing a 'female' hint
    6. First available .onnx model
    """
    requested_voice = (requested_voice or "").strip()
    
    # Allowed directories for security (prevent path traversal)
    dojo_root = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo"
    allowed_roots = [SCRIPT_DIR.parent / "voices", SCRIPT_DIR, dojo_root]

    if requested_voice:
        # Allow either an explicit path to a .onnx file, or a bare filename.
        candidate_path = Path(requested_voice)
        if not candidate_path.is_absolute():
            # Resolve relative paths against the server directory.
            candidate_path = (SCRIPT_DIR / candidate_path).resolve()
        else:
            candidate_path = candidate_path.resolve()

        # Security check: Ensure the path is within allowed roots using is_relative_to()
        is_allowed = any(
            candidate_path.is_relative_to(root.resolve()) 
            for root in allowed_roots
        )
        
        if is_allowed and candidate_path.exists() and candidate_path.is_file() and candidate_path.suffix.lower() == ".onnx":
            return candidate_path

        # If not a direct path, search by filename using cache map
        found = get_model_path_by_name(requested_voice)
        if found:
            return found

        raise FileNotFoundError(f"Requested voice_model not found or access denied: {requested_voice}")

    override = os.environ.get(PIPER_MODEL_ENV, "").strip()
    if override:
        p = Path(override)
        if p.exists() and p.is_file() and p.suffix.lower() == ".onnx":
            return p
        raise FileNotFoundError(f"{PIPER_MODEL_ENV} points to missing/invalid .onnx: {override}")

    # Check config.json for user-selected voice
    cfg = load_config()
    selected_voice = cfg.get("voice_model", "").strip()
    if selected_voice:
        # Search for this voice in voices/ folder
        for candidate in iter_candidate_models():
            # Accept either a full filename (e.g. model.onnx) or a stem (e.g. model)
            if candidate.name == selected_voice or candidate.stem == selected_voice:
                return candidate

    models = list(iter_candidate_models())
    if not models:
        raise FileNotFoundError(
            "No Piper .onnx voices found. Put voices under ./voices/ or set PIPER_MODEL to a .onnx path."
        )

    # 1) Prefer exact model name
    for m in models:
        if m.name == PREFERRED_MODEL:
            return m

    # 2) Prefer female-ish by filename/path hints
    lowered = [(m, str(m).lower()) for m in models]
    for hint in FEMALE_VOICE_HINTS:
        for m, s in lowered:
            if hint in s:
                return m

    # 3) Fallback: first model
    return models[0]


_SERVER_START_TIME = time.time()

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health():
    """
    Health check endpoint with server status, uptime, and resource usage.
    
    Returns:
        - ok: Server is running
        - version: API version
        - uptime_seconds: Time since server start
        - loaded_voices: Number of available voices
        - memory_mb: Current memory usage (if available)
        - stuck_processes: Count of processes stuck for >60s
        - available_voices: List of playable ONNX models
    """
    uptime = time.time() - _SERVER_START_TIME
    
    # Get memory usage
    memory_mb = None
    try:
        import psutil
        process = psutil.Process()
        memory_mb = round(process.memory_info().rss / 1024 / 1024, 2)
    except Exception:
        pass
    
    # Refresh voice cache
    get_model_path_by_name("ensure_cache")
    
    # Build unique voice list using list comprehension for better performance
    nicknames = load_nicknames()
    
    # Use list comprehension to build voice infos in one pass
    voice_infos = sorted(
        [
            VoiceInfo(
                name=path.stem,
                path=str(path),
                size=get_size_bytes(path),
                nickname=nicknames.get(path.stem)
            )
            for path in iter_candidate_models()
        ],
        key=lambda x: x.name
    )
    
    # Check for stuck processes (using sum with generator for efficiency)
    now = time.time()
    stuck = sum(
        1 for proc in manager.processes.values()
        if proc.processing_start and (now - proc.processing_start > 60)
    )
            
    # Determine current default model
    current_model = None
    try:
        p = resolve_model_path(None)
        if p and p.exists():
            current_model = str(p)
    except Exception:
        pass
        
    return HealthResponse(
        ok=True,
        version="1.0.0",
        uptime_seconds=round(uptime, 2),
        loaded_voices=len(voice_infos),
        memory_mb=memory_mb,
        stuck_processes=stuck,
        available_voices=voice_infos,
        model=current_model
    )


@app.get("/api/config", tags=["Configuration"])
def get_config():
    """Get current server configuration including host, port, default voice, and preferences."""
    return load_config()


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    # WebUI doesn't ship a favicon.ico in all builds; avoid noisy 404s in the browser console.
    return Response(content=b"", status_code=204)


@app.post("/api/voice/nickname", tags=["Voice Management"])
def set_nickname_api(req: NicknameReq):
    """Set a nickname for a voice model with validation."""
    from common_utils import validate_nickname
    
    voice_name = _validate_voice_name(req.voice_name)
    # Nicknames are display names - less strict validation
    nickname = validate_nickname(req.nickname)
    
    nicknames = load_nicknames()
    nicknames[voice_name] = nickname
    save_nicknames(nicknames)
    return {"ok": True}


@app.options("/api/tts")
def tts_options():
    """Handle CORS preflight requests."""
    return Response(content=b"", status_code=204, headers=cors_headers())


@app.post("/api/warmup", tags=["Text-to-Speech"])
def warmup(req: TTSReq):
    """
    Pre-load a voice model into memory for faster first synthesis.
    
    Recommended for production deployments to eliminate cold-start latency.
    Call this during app initialization or when switching voices.
    """
    try:
        model_path = resolve_model_path(req.voice_model)
        piper_exe = resolve_piper_exe()
        speaker = os.environ.get(PIPER_SPEAKER_ENV, "").strip()
        
        config_path = model_path.with_suffix(model_path.suffix + ".json")
        if not config_path.exists():
            config_path = model_path.with_suffix(".json")

        cwd = None
        try:
            piper_path = Path(piper_exe)
            if piper_path.exists():
                cwd = str(piper_path.resolve().parent)
        except Exception:
            pass

        process = manager.get_process(model_path, config_path, speaker, piper_exe, cwd)
        process.ensure_started()
        return Response(content="Warmed up", status_code=200, media_type="text/plain")
    except Exception as e:
        # Warmup is a best-effort optimization. Do not fail the request (or spam the WebUI
        # with network errors) if the voice can't be preloaded for any reason.
        logger.warning(f"Warmup skipped: {e}")
        return Response(content=f"Warmup skipped: {e}", status_code=200, media_type="text/plain")


@app.post("/api/tts", tags=["Text-to-Speech"])
async def tts(req: TTSReq, request: Request):
    """
    Synthesize text to speech and return WAV audio.
    
    **Features:**
    - Automatic chunking for texts up to 100,000 characters
    - Intelligent splitting at sentence/paragraph boundaries
    - Seamless audio concatenation
    - Client disconnection detection
    
    **Example:**
    ```json
    {
      "text": "Hello, this is a test.",
      "voice_model": "Cori"
    }
    ```
    
    **Error Codes:**
    - 400: Text is required or invalid
    - 404: Voice model not found
    - 413: Text exceeds 100,000 character limit
    - 499: Client disconnected during synthesis
    """
    # Validate text
    if not req.text or not req.text.strip():
        return Response(content="Text is required", status_code=400, media_type="text/plain", headers=cors_headers())
    
    # Safety limit to prevent abuse
    if len(req.text) > MAX_TEXT_LENGTH:
        msg = f"Text too long. Maximum {MAX_TEXT_LENGTH} characters allowed. Got {len(req.text)} characters."
        logger.warning(f"Request rejected: {msg}")
        return Response(content=msg, status_code=413, media_type="text/plain", headers=cors_headers())
    
    # Chunk text if needed
    text_chunks = chunk_text(req.text, CHUNK_SIZE)
    if len(text_chunks) > 1:
        logger.info(f"Split text into {len(text_chunks)} chunks ({len(req.text)} chars total)")
    
    # Generate unique request ID for tracking and cancellation
    request_id = f"{time.time()}_{id(request)}"
    
    if req.voice_model:
        logger.info(f"Requested voice_model: {req.voice_model} (request {request_id})")
    
    try:
        model_path = resolve_model_path(req.voice_model)
    except FileNotFoundError as e:
        logger.warning(f"Voice model not found: {e}")
        return Response(content=str(e), status_code=404, media_type="text/plain", headers=cors_headers())

    # Early disconnection check - client may have cancelled immediately
    if await request.is_disconnected():
        logger.info(f"Client disconnected before synthesis started (request {request_id}) - skipping")
        return Response(content="Client disconnected", status_code=499, media_type="text/plain")

    piper_exe = resolve_piper_exe()
    speaker = os.environ.get(PIPER_SPEAKER_ENV, "").strip()

    # Look for the .json config file associated with the model
    config_path = model_path.with_suffix(model_path.suffix + ".json")
    if not config_path.exists():
        config_path = model_path.with_suffix(".json")

    # Determine sample rate using cached config
    sample_rate = 22050 # Default for many Piper models
    if config_path.exists():
        try:
            cfg_data = get_model_config(config_path)
            sample_rate = cfg_data.get("audio", {}).get("sample_rate", 22050)
        except Exception as e:
            logger.debug(f"Error reading config for sample rate: {e}")

    try:
        cwd = None
        try:
            piper_path = Path(piper_exe)
            if piper_path.exists():
                cwd = str(piper_path.resolve().parent)
        except Exception:
            pass

        # Use persistent process manager
        process = manager.get_process(model_path, config_path, speaker, piper_exe, cwd)
        
        # Check if client is still connected before starting synthesis
        if await request.is_disconnected():
            logger.info(f"Client disconnected before synthesis (request {request_id}) - skipping")
            # Cancel this request if it's queued
            process.cancel_synthesis()
            return Response(content="Client disconnected", status_code=499, media_type="text/plain")
        
        # Process chunks and collect audio (using thread pool for blocking I/O)
        audio_chunks = []
        for i, chunk in enumerate(text_chunks):
            # Check for disconnection between chunks
            if await request.is_disconnected():
                logger.info(f"Client disconnected during chunk {i+1}/{len(text_chunks)} (request {request_id})")
                return Response(content="Client disconnected", status_code=499, media_type="text/plain")
            
            if len(text_chunks) > 1:
                logger.info(f"Processing chunk {i+1}/{len(text_chunks)} ({len(chunk)} chars)")
            
            # Run blocking synthesis in thread pool to avoid blocking event loop
            chunk_audio = await asyncio.to_thread(
                process.synthesize, chunk, f"{request_id}_chunk{i}"
            )
            audio_chunks.append(chunk_audio)
        
        # Concatenate chunks if needed (also run in thread pool)
        if len(audio_chunks) > 1:
            logger.info(f"Concatenating {len(audio_chunks)} audio chunks")
            audio_data = await asyncio.to_thread(concatenate_wav_files, audio_chunks)
        else:
            audio_data = audio_chunks[0]
        
        # Final check before sending response
        if await request.is_disconnected():
            logger.info(f"Client disconnected after synthesis (request {request_id}) - discarding result")
            return Response(content="Client disconnected", status_code=499, media_type="text/plain")
        
        return Response(content=audio_data, media_type="audio/wav")

    except Exception as e:
        logger.error(f"TTS Error: {e}")
        return Response(
            content=f"Server error: {str(e)}",
            status_code=500,
            media_type="text/plain",
        )


@app.post("/api/cancel", tags=["Text-to-Speech"])
def cancel_all():
    """
    Cancel all active synthesis operations immediately.
    
    Stops speech generation without terminating processes.
    Useful for "Stop" buttons in UI.
    """
    logger.info("Received cancel request. Cancelling all active synthesis operations.")
    count = 0
    with manager.lock:
        # Use values() since we don't need the keys
        for process_wrapper in manager.processes.values():
            if process_wrapper.processing_start is not None:
                process_wrapper.cancel_synthesis()
                count += 1
    
    logger.info(f"Cancelled {count} active synthesis operation(s)")
    return {"status": "ok", "cancelled_count": count}


@app.get("/api/logs", tags=["System"])
async def get_logs():
    """Return the last 100 lines of the server log for debugging."""
    if log_file.exists():
        try:
            # Read with errors="replace" to handle non-utf8 characters (like Windows quotes)
            # Use async I/O to avoid blocking
            content = await asyncio.to_thread(
                log_file.read_text, encoding="utf-8", errors="replace"
            )
            lines = content.splitlines()
            return {"logs": lines[-100:]}
        except Exception as e:
            logger.error(f"Failed to read log file: {e}")
            return {"logs": [f"Error reading log: {str(e)}"]}
    return {"logs": ["Log file not found."]}


@app.get("/api/dojos", tags=["Voice Management"])
def list_dojos():
    """
    List all voice training projects with detailed metadata.
    
    Returns comprehensive information including:
    - Training status (ready, training, not started)
    - Checkpoint counts
    - Dataset statistics
    - Export status
    
    For a simple list of voice names, use `/api/voices` instead.
    """
    return {"dojos": training_manager.list_dojos()}


class DojoCreateRequest(BaseModel):
    name: str
    quality: str = "M"
    gender: str = "F"
    scratch: bool = False


class SlicerRequest(BaseModel):
    voice: str
    # Parameters to match auto_split.py behavior
    min_silence_len_ms: int = 600
    silence_thresh_offset_db: float = -16.0
    keep_silence_ms: int = 250


class DetectNonsilentRequest(BaseModel):
    voice: str
    # Parameters to match the Python slicer's auto-detect behavior
    min_silence_len_ms: int = 300
    silence_thresh_offset_db: float = -16.0
    pad_ms: int = 200
    min_segment_ms: int = 500


class SegmentMs(BaseModel):
    start_ms: float
    end_ms: float


class VoiceLabelRequest(BaseModel):
    voice: str
    segments: list[SegmentMs]
    k: int = 2


class VoiceSplitRequest(BaseModel):
    voice: str
    base_segments: list[SegmentMs] | None = None
    win_s: float = 1.5
    hop_s: float = 0.5
    thresh: float = 0.78
    min_seg_s: float = 1.0


class VoiceFilterRequest(BaseModel):
    voice: str
    segments: list[SegmentMs]
    ref_start_ms: float
    ref_end_ms: float
    threshold: float = 0.78
    mode: str = "keep"  # keep|remove


@app.post("/api/training/create")
def create_dojo(request: DojoCreateRequest):
    """Create a new training dojo."""
    try:
        result = training_manager.create_dojo(
            voice_name=request.name,
            quality=request.quality,
            gender=request.gender,
            scratch=request.scratch
        )
        if not result.get("ok"):
            return Response(content=result.get("error", "Unknown error"), status_code=500)
        return result
    except Exception as e:
        logger.error(f"Error creating dojo: {e}")
        return Response(content=str(e), status_code=500)


@app.get("/api/training/audio-files")
def get_audio_files(voice: str):
    """List audio files in dojo dataset."""
    return {"files": training_manager.get_audio_files(voice)}


@app.get("/api/training/master-info")
def get_master_info(voice: str):
    """Get information about the master audio file for a dojo."""
    return training_manager.get_master_audio_info(voice)


@app.get("/api/training/deps-status")
def training_deps_status():
    """Report optional dependencies used by slicer features.

    The Python slicer can prompt-install these interactively.
    The web slicer can't safely auto-install, so we provide a status endpoint
    the UI can use to show actionable guidance.
    """

    missing: List[str] = []

    # ffmpeg is needed for importing mp3/m4a/etc via pydub.
    has_ffmpeg = bool(shutil.which("ffmpeg"))
    if not has_ffmpeg:
        missing.append("ffmpeg")

    # Voice tools (resemblyzer/torch/numpy) are optional.
    has_voice_deps = True
    try:
        import numpy  # noqa: F401
    except Exception:
        has_voice_deps = False
        missing.append("numpy")
    try:
        import torch  # noqa: F401
    except Exception:
        has_voice_deps = False
        missing.append("torch")
    try:
        import resemblyzer  # noqa: F401
    except Exception:
        has_voice_deps = False
        missing.append("resemblyzer")

    # pydub is required for slicing/export.
    has_pydub = True
    try:
        import pydub  # noqa: F401
    except Exception:
        has_pydub = False
        missing.append("pydub")

    return {
        "ok": True,
        "ffmpeg": has_ffmpeg,
        "voice_tools": has_voice_deps,
        "pydub": has_pydub,
        "missing": sorted(set(missing)),
    }


class SegmentExportRequest(BaseModel):
    voice: str
    start_ms: int
    end_ms: int
    name: Optional[str] = None
    naming_mode: str = "numeric"

@app.post("/api/training/export-segment")
def export_segment(req: SegmentExportRequest):
    """Export a specific segment from master audio."""
    try:
        req.voice = _validate_voice_name(req.voice)
    except Exception as e:
        return Response(content=str(e), status_code=400)

    result = training_manager.export_segment(
        req.voice,
        int(req.start_ms),
        int(req.end_ms),
        str(req.name or ""),
        naming_mode=str(req.naming_mode or "numeric"),
    )
    if not result.get("ok"):
        return Response(content=result.get("error", "Failed to export"), status_code=500)
    return result


@app.get("/api/training/download-wavs-zip")
def download_wavs_zip(voice: str):
    """Download the dojo's dataset/wav folder as a ZIP (web equivalent of 'export to folder')."""
    try:
        voice = _validate_voice_name(voice)
    except Exception as e:
        return Response(content=str(e), status_code=400)

    dojo_path = DOJO_ROOT / f"{voice}_dojo"
    wav_folder = dojo_path / "dataset" / "wav"
    if not wav_folder.exists():
        return Response(content="No dataset/wav folder found for this voice.", status_code=404)

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(wav_folder.glob("*.wav")):
            # Store only filename in zip to mimic 'export folder' behavior
            zf.write(p, arcname=p.name)
        # include metadata.csv if present
        meta = dojo_path / "dataset" / "metadata.csv"
        if meta.exists():
            zf.write(meta, arcname="metadata.csv")

    mem.seek(0)
    headers = {
        "Content-Disposition": f'attachment; filename="{voice}_dataset_wavs.zip"'
    }
    return StreamingResponse(mem, media_type="application/zip", headers=headers)


@app.post("/api/training/upload-audio")
async def upload_audio(voice: str, file: UploadFile = File(...), auto_split: bool = False):
    """Upload a master audio file for slicing."""
    # Sanitize filename to prevent path traversal
    safe_filename = Path(file.filename).name if file.filename else "upload.wav"
    # Remove dangerous characters but preserve spaces and international characters
    safe_filename = safe_filename.replace('\0', '').replace('..', '').replace('/', '').replace('\\', '')
    
    temp_dir = Path(tempfile.gettempdir())
    dest_path = temp_dir / safe_filename
    
    with dest_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    dojo_path = DOJO_ROOT / f"{voice}_dojo"
    raw_folder = dojo_path / "dataset" / "raw"
    raw_folder.mkdir(parents=True, exist_ok=True)
    master_wav_path = raw_folder / "master.wav"

    # Normalize uploads into a real WAV file so downstream tools work.
    # For MP3/M4A/etc this requires ffmpeg.
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(str(dest_path))
        audio = audio.set_frame_rate(22050).set_channels(1)
        audio.export(str(master_wav_path), format="wav")
    except Exception as e:
        logger.error(f"Failed to process uploaded audio: {e}")
        msg = str(e)
        if "ffmpeg" in msg.lower() or "ffprobe" in msg.lower():
            msg = (
                "ffmpeg is required to import this audio format (e.g. mp3). "
                "Install ffmpeg and restart the server, then try the upload again. "
                f"Original error: {e}"
            )
        return Response(content=msg, status_code=500, media_type="text/plain")

    if auto_split:
        # Trigger auto split immediately (legacy behavior)
        result = training_manager.run_auto_split(voice, str(master_wav_path))
    else:
        # Just save it for manual slicing
        result = {"ok": True, "status": "saved"}
    
    # Clean up temp file
    try:
        dest_path.unlink()
    except:
        pass
        
    return result


@app.post("/api/training/run-slicer")
def run_slicer_api(req: SlicerRequest):
    """Run the auto-splitter on the dojo's master audio."""
    try:
        req.voice = _validate_voice_name(req.voice)
    except Exception as e:
        return Response(content=str(e), status_code=400)

    # Check if master audio exists
    info = training_manager.get_master_audio_info(req.voice)
    if not info.get("exists"):
        return Response(content="Master audio not found for this voice. Upload one first.", status_code=404)
    
    # Run slicing
    dojo_path = DOJO_ROOT / f"{req.voice}_dojo"
    master_path = dojo_path / "dataset" / "raw" / "master.wav"
    
    result = training_manager.run_auto_split(
        req.voice,
        str(master_path),
        min_silence_len_ms=int(req.min_silence_len_ms),
        silence_thresh_offset_db=float(req.silence_thresh_offset_db),
        keep_silence_ms=int(req.keep_silence_ms),
    )
    if not result.get("ok"):
        return Response(content=result.get("error", "Slicing failed"), status_code=500)
    
    return {"status": "ok", "count": result.get("count", 0)}


@app.post("/api/training/detect-nonsilent")
def detect_nonsilent_api(req: DetectNonsilentRequest):
    """Return non-silent segment ranges for the master audio (no export).

    This is the web equivalent of the Python slicer's Auto-Detect Silence: it creates
    candidate segments which the user can preview/edit, then export.
    """
    try:
        req.voice = _validate_voice_name(req.voice)
    except Exception as e:
        return Response(content=str(e), status_code=400)

    info = training_manager.get_master_audio_info(req.voice)
    if not info.get("exists"):
        return Response(content="Master audio not found for this voice. Upload one first.", status_code=404)

    dojo_path = DOJO_ROOT / f"{req.voice}_dojo"
    master_path = dojo_path / "dataset" / "raw" / "master.wav"

    result = training_manager.detect_nonsilent_segments(
        req.voice,
        str(master_path),
        min_silence_len_ms=int(req.min_silence_len_ms),
        silence_thresh_offset_db=float(req.silence_thresh_offset_db),
        pad_ms=int(req.pad_ms),
        min_segment_ms=int(req.min_segment_ms),
    )
    if not result.get("ok"):
        return Response(content=result.get("error", "Detection failed"), status_code=500)

    return {"status": "ok", "segments": result.get("segments", [])}


@app.post("/api/training/segments/voice-label")
def voice_label_segments_api(req: VoiceLabelRequest):
    try:
        voice = _validate_voice_name(req.voice)
    except Exception as e:
        return Response(content=str(e), status_code=400)

    master_path = DOJO_ROOT / f"{voice}_dojo" / "dataset" / "raw" / "master.wav"
    if not master_path.exists():
        return Response(content="Master audio not found for this voice.", status_code=404)

    try:
        from voice_tools import VoiceDepsMissing, load_master_wav, voice_label_segments

        wav = load_master_wav(master_path)
        segments_ms = [(float(s.start_ms), float(s.end_ms)) for s in req.segments]
        voice_ids = voice_label_segments(wav=wav, segments_ms=segments_ms, k=int(req.k))
        out_segments = [
            {"start_ms": float(seg[0]), "end_ms": float(seg[1]), "voice_id": int(vid)}
            for seg, vid in zip(segments_ms, voice_ids)
        ]
        return {
            "status": "ok",
            "used_trim_silence": bool(wav.used_trim_silence),
            "segments": out_segments,
        }
    except VoiceDepsMissing as e:
        return Response(content=str(e), status_code=501)
    except Exception as e:
        logger.exception("Voice labeling failed")
        return Response(content=str(e), status_code=500)


@app.post("/api/training/segments/voice-split")
def voice_split_segments_api(req: VoiceSplitRequest):
    try:
        voice = _validate_voice_name(req.voice)
    except Exception as e:
        return Response(content=str(e), status_code=400)

    master_path = DOJO_ROOT / f"{voice}_dojo" / "dataset" / "raw" / "master.wav"
    if not master_path.exists():
        return Response(content="Master audio not found for this voice.", status_code=404)

    try:
        from voice_tools import VoiceDepsMissing, load_master_wav, voice_split_by_changes

        wav = load_master_wav(master_path)
        if req.base_segments and len(req.base_segments) > 0:
            base_segments = [(float(s.start_ms), float(s.end_ms)) for s in req.base_segments]
        else:
            base_segments = [(0.0, (len(wav.wav) / wav.sr) * 1000.0)]

        new_segments = voice_split_by_changes(
            wav=wav,
            base_segments_ms=base_segments,
            win_s=float(req.win_s),
            hop_s=float(req.hop_s),
            thresh=float(req.thresh),
            min_seg_s=float(req.min_seg_s),
        )
        return {
            "status": "ok",
            "used_trim_silence": bool(wav.used_trim_silence),
            "segments": [{"start_ms": float(s), "end_ms": float(e)} for (s, e) in new_segments],
        }
    except VoiceDepsMissing as e:
        return Response(content=str(e), status_code=501)
    except Exception as e:
        logger.exception("Voice split failed")
        return Response(content=str(e), status_code=500)


@app.post("/api/training/segments/voice-filter")
def voice_filter_segments_api(req: VoiceFilterRequest):
    try:
        voice = _validate_voice_name(req.voice)
    except Exception as e:
        return Response(content=str(e), status_code=400)

    master_path = DOJO_ROOT / f"{voice}_dojo" / "dataset" / "raw" / "master.wav"
    if not master_path.exists():
        return Response(content="Master audio not found for this voice.", status_code=404)

    try:
        from voice_tools import VoiceDepsMissing, load_master_wav, voice_filter_segments

        wav = load_master_wav(master_path)
        segments_ms = [(float(s.start_ms), float(s.end_ms)) for s in req.segments]
        mode = (req.mode or "keep").strip().lower()
        if mode not in ("keep", "remove"):
            return Response(content="mode must be 'keep' or 'remove'", status_code=400)

        def update_progress(current: int, total: int):
            training_manager.set_filter_progress(req.voice, current, total)

        kept, kept_count = voice_filter_segments(
            wav=wav,
            segments_ms=segments_ms,
            ref_ms=(float(req.ref_start_ms), float(req.ref_end_ms)),
            threshold=float(req.threshold),
            mode=mode,  # type: ignore[arg-type]
            progress_callback=update_progress,
        )
        training_manager.clear_filter_progress(req.voice)
        return {
            "status": "ok",
            "used_trim_silence": bool(wav.used_trim_silence),
            "kept": int(kept_count),
            "total": int(len(segments_ms)),
            "segments": [{"start_ms": float(s), "end_ms": float(e)} for (s, e) in kept],
        }
    except VoiceDepsMissing as e:
        return Response(content=str(e), status_code=501)
    except Exception as e:
        logger.exception("Voice filter failed")
        return Response(content=str(e), status_code=500)


@app.post("/api/training/segments/voice-filter-upload")
async def voice_filter_segments_upload_api(
    voice: str = Form(...),
    threshold: float = Form(0.78),
    mode: str = Form("keep"),
    segments_json: str = Form(...),
    file: UploadFile = File(...),
):
    """Voice filter segments using an uploaded reference audio file."""
    try:
        voice = _validate_voice_name(voice)
    except Exception as e:
        return Response(content=str(e), status_code=400)

    master_path = DOJO_ROOT / f"{voice}_dojo" / "dataset" / "raw" / "master.wav"
    if not master_path.exists():
        return Response(content="Master audio not found for this voice.", status_code=404)

    mode_norm = (mode or "keep").strip().lower()
    if mode_norm not in ("keep", "remove"):
        return Response(content="mode must be 'keep' or 'remove'", status_code=400)

    try:
        segs_raw = json.loads(segments_json)
        if not isinstance(segs_raw, list):
            return Response(content="segments_json must be a JSON list", status_code=400)

        segments_ms: list[tuple[float, float]] = []
        for item in segs_raw:
            if not isinstance(item, dict):
                continue
            segments_ms.append((float(item.get("start_ms")), float(item.get("end_ms"))))

        from voice_tools import (
            VoiceDepsMissing,
            load_master_wav,
            voice_filter_segments_by_ref_audio,
        )

        # Save upload to temp and normalize to a WAV for resemblyzer.
        # Sanitize filename to prevent path traversal
        safe_filename = Path(file.filename).name if file.filename else "ref.wav"
        safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', safe_filename)
        temp_dir = Path(tempfile.gettempdir())
        up_path = temp_dir / f"piper_ref_{voice}_{int(time.time())}_{safe_filename}"
        with up_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        ref_wav_path = temp_dir / f"piper_ref_{voice}_{int(time.time())}.wav"
        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(str(up_path))
            audio = audio.set_frame_rate(16000).set_channels(1)
            audio.export(str(ref_wav_path), format="wav")
        finally:
            try:
                up_path.unlink()
            except Exception:
                pass

        wav = load_master_wav(master_path)
        kept, kept_count, used_trim_silence = voice_filter_segments_by_ref_audio(
            wav=wav,
            segments_ms=segments_ms,
            ref_audio_path=str(ref_wav_path),
            threshold=float(threshold),
            mode=mode_norm,  # type: ignore[arg-type]
        )

        try:
            ref_wav_path.unlink()
        except Exception:
            pass

        return {
            "status": "ok",
            "used_trim_silence": bool(wav.used_trim_silence) or bool(used_trim_silence),
            "kept": int(kept_count),
            "total": int(len(segments_ms)),
            "segments": [{"start_ms": float(s), "end_ms": float(e)} for (s, e) in kept],
        }
    except VoiceDepsMissing as e:
        return Response(content=str(e), status_code=501)
    except Exception as e:
        logger.exception("Voice filter upload failed")
        return Response(content=str(e), status_code=500)


@app.get("/api/training/segments/voice-filter/progress")
def get_voice_filter_progress(voice: str):
    """Get the current progress of a voice filter task."""
    prog = training_manager.get_filter_progress(voice)
    if not prog:
        return {"current": 0, "total": 0}
    return prog


@app.post("/api/training/transcribe")
def transcribe_dojo(voice: str):
    """Trigger Whisper transcription on a dojo."""
    result = training_manager.run_transcription(voice)
    if not result.get("ok"):
        return Response(content=result.get("error", "Transcription failed"), status_code=500)
    return result


@app.get("/api/training/transcribe/progress")
def get_transcribe_progress(voice: str):
    """Get the current progress of a transcription task."""
    progress = training_manager.get_transcription_progress(voice)
    if not progress:
        return {"active": False}
    return {"active": True, **progress}


@app.get("/api/training/metadata")
def get_metadata(voice: str):
    """Get metadata for a dojo."""
    return {"entries": training_manager.get_metadata(voice)}


class MetadataSaveRequest(BaseModel):
    voice: str
    entries: List[Dict[str, str]]


@app.post("/api/training/metadata")
def save_metadata(request: MetadataSaveRequest):
    """Save metadata for a dojo."""
    success = training_manager.save_metadata(request.voice, request.entries)
    if not success:
        return Response(content="Failed to save metadata", status_code=500)
    return {"ok": True}


class TrainingStartRequest(BaseModel):
    voice: str
    # resume: resume from highest saved checkpoint
    # pretrained: restart from base pretrained checkpoint
    # scratch: train from scratch (no base model)
    start_mode: str | None = None

@app.post("/api/training/start")
def start_training(request: TrainingStartRequest):
    """Launch Docker training for a dojo."""
    try:
        voice = _validate_voice_name(request.voice)
    except ValueError as e:
        return Response(content=str(e), status_code=400)
    return training_manager.start_training(voice, start_mode=request.start_mode)


class IgnoreWavsRequest(BaseModel):
    voice: str
    ids: List[str]
    delete_files: bool = False


@app.post("/api/training/ignore-wavs")
def ignore_wavs(request: IgnoreWavsRequest):
    """Ignore (and optionally delete) specific dataset wav clip IDs."""
    try:
        voice = _validate_voice_name(request.voice)
    except Exception as e:
        return Response(content=str(e), status_code=400)
    return training_manager.ignore_wavs(voice, request.ids, delete_files=bool(request.delete_files))


@app.post("/api/training/preprocess")
def run_preprocess(voice: str):
    """Launch Piper preprocessing (feature extraction) only."""
    try:
        voice = _validate_voice_name(voice)
    except ValueError as e:
        return Response(content=str(e), status_code=400)
    return training_manager.run_preprocessing(voice)


@app.post("/api/training/stop")
def stop_training(voice: str, deep_cleanup: bool = False):
    """Stop Docker training for a dojo. optionally reclaims memory (WSL shutdown)."""
    try:
        voice = _validate_voice_name(voice)
    except ValueError as e:
        return Response(content=str(e), status_code=400)
    return training_manager.stop_training(voice, deep_cleanup=deep_cleanup)


@app.post("/api/training/save-checkpoint")
def manual_save_checkpoint(voice: str):
    """Manually trigger a save/export of the latest checkpoint."""
    try:
        voice = _validate_voice_name(voice)
    except ValueError as e:
        return Response(content=str(e), status_code=400)
    return training_manager.manual_checkpoint_save(voice)


class TrainingInputRequest(BaseModel):
    voice: str
    text: str

@app.post("/api/training/input")
def send_training_input(request: TrainingInputRequest):
    """Send input to an active training session."""
    try:
        voice = _validate_voice_name(request.voice)
    except ValueError as e:
        return Response(content=str(e), status_code=400)
    return training_manager.send_training_input(voice, request.text)


@app.get("/api/training/status")
def get_training_status(voice: str):
    """Get training status and stats."""
    try:
        voice = _validate_voice_name(voice)
    except ValueError as e:
        return Response(content=str(e), status_code=400)
    return training_manager.get_training_status(voice)


@app.get("/api/training/dataset-stats")
def get_dataset_stats(voice: str):
    """Get stats about the current dataset files."""
    try:
        voice = _validate_voice_name(voice)
    except ValueError as e:
        return Response(content=str(e), status_code=400)
    return training_manager.get_dataset_stats(voice)


@app.post("/api/training/update-settings")
def update_interval_settings(voice: str, settings: dict):
    """Update training settings."""
    try:
        voice = _validate_voice_name(voice)
    except ValueError as e:
        return Response(content=str(e), status_code=400)
    return training_manager.update_dojo_settings(voice, settings)


class ExportProductionRequest(BaseModel):
    voice: str
    onnx_filename: str

@app.post("/api/training/export-production")
def export_production_api(request: ExportProductionRequest):
    """Export a specifically trained model to the production folder."""
    try:
        voice = _validate_voice_name(request.voice)
    except ValueError as e:
        return Response(content=str(e), status_code=400)
    return training_manager.export_to_production(voice, request.onnx_filename)


class TrainingSettingsRequest(BaseModel):
    voice: str
    settings: Dict[str, str]

@app.post("/api/training/settings")
def update_dataset_properties(request: TrainingSettingsRequest):
    """Update high-level training settings like gender/quality."""
    try:
        voice = _validate_voice_name(request.voice)
    except ValueError as e:
        return Response(content=str(e), status_code=400)
    return training_manager.update_dataset_settings(voice, request.settings)


@app.post("/api/tools/launch")
def launch_tool(tool: str, dojo: str | None = None):
    """Launch one of the standalone GUI tools."""
    if tool == "tensorboard":
        # Special handling for TensorBoard since it runs in Docker instead of a local Python script
        def _launch_tb():
            try:
                # Check if container is running
                check_cmd = ["docker", "ps", "-f", "name=textymcspeechy-piper", "--format", "{{.Names}}"]
                result = subprocess.run(
                    check_cmd,
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                if "textymcspeechy-piper" not in result.stdout:
                    logger.error("TensorBoard launch failed: textymcspeechy-piper container not running")
                    return

                # Check if tensorboard is already running inside the container
                ps_cmd = ["docker", "exec", "textymcspeechy-piper", "ps", "aux"]
                ps_result = subprocess.run(
                    ps_cmd,
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                if "tensorboard" in ps_result.stdout:
                    logger.info("TensorBoard is already running in the container.")
                    return

                # Determine the log directory. Use provided dojo or fallback to common ones
                target_dojo = dojo if dojo else "billy" # fallback
                if target_dojo and not target_dojo.endswith("_dojo"):
                    target_dojo = f"{target_dojo}_dojo"
                
                log_dir = f"/app/tts_dojo/{target_dojo}/training_folder/lightning_logs"
                
                # Launch detached tensorboard process in container
                # We bind to 0.0.0.0 so the port mapping 6006:6006 works.
                launch_cmd = [
                    "docker", "exec", "-d", "textymcspeechy-piper", 
                    "tensorboard", "--logdir", log_dir, "--bind_all", "--port", "6006"
                ]
                subprocess.run(
                    launch_cmd,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                logger.info(f"Launched TensorBoard in container for dojo: {target_dojo}")
            except Exception as e:
                logger.error(f"Failed to launch TensorBoard: {e}")

        threading.Thread(target=_launch_tb, daemon=True).start()
        return {"status": "launched"}

    # Tool Configuration: (Script Path, Window Title Search Pattern)
    tools_config = {
        "slicer": (SCRIPT_DIR / "tools" / "dataset_slicer_ui.py", "*Piper Dataset Slicer*"),
        "wizard": (SCRIPT_DIR / "tools" / "transcribe_wizard.py", "*Auto-Transcribe*"),
        "trainer": (SCRIPT_DIR / "training_dashboard_ui.py", "*Piper Training Dashboard*"),
        "storage": (SCRIPT_DIR / "storage_manager_ui.py", "*Piper Storage Manager*"),
    }
    
    if tool not in tools_config:
        return Response(content=f"Tool not found: {tool}", status_code=404)
        
    script_path, title_pattern = tools_config[tool]
    if not script_path.exists():
        return Response(content=f"Tool script not found: {tool}", status_code=404)

    def _launch():
        try:
            # 1. Try to FIND and FOCUS existing instance first (Safe for tools with state like Slicer)
            if os.name == 'nt':
                ps_focus_tool = f'''
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinAPI {{
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);
}}
"@

# Simulate Alt key to relax Foreground Lock
[WinAPI]::keybd_event(0x12, 0, 0, 0)
Start-Sleep -Milliseconds 5
[WinAPI]::keybd_event(0x12, 0, 2, 0)

$proc = Get-Process | Where-Object {{ $_.MainWindowTitle -like "{title_pattern}" }} | Select-Object -First 1
if ($proc) {{
    $hwnd = $proc.MainWindowHandle
    if ($hwnd -ne 0) {{
        if ([WinAPI]::IsIconic($hwnd)) {{ [WinAPI]::ShowWindow($hwnd, 9) }}
        [WinAPI]::SetForegroundWindow($hwnd)
        Write-Output "FOCUSED"
        exit 0
    }}
}}
exit 1
'''
                result = subprocess.run(["powershell", "-NoProfile", "-Command", ps_focus_tool], 
                                      capture_output=True, text=True,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                
                if "FOCUSED" in result.stdout:
                    logger.info(f"Focused existing tool: {tool}")
                    return

            # 2. Launch New Instance if not found
            # Use same venv as server
            python_exe = sys.executable
            if os.name == "nt" and python_exe.endswith("python.exe"):
                w_exe = Path(python_exe).parent / "pythonw.exe"
                if w_exe.exists():
                    python_exe = str(w_exe)
            
            cmd = [python_exe, str(script_path)]
            if dojo:
                cmd += ["--dojo", dojo]
                
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            subprocess.Popen(cmd, creationflags=flags, cwd=str(SCRIPT_DIR))
            logger.info(f"Launched tool: {tool} {dojo or ''}")
        except Exception as e:
            logger.error(f"Failed to launch tool {tool}: {e}")

    threading.Thread(target=_launch, daemon=True).start()
    return {"status": "launched"}


def _force_open_path(path: Path):
    """Open a path and try to force it to the foreground on Windows."""
    try:
        abs_path = str(path.resolve())
        if os.name == 'nt':
            # Use native Windows API via PowerShell to force window to foreground
            # Includes Shell.Application lookup to find ALREADY OPEN windows
            ps_cmd = '''
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinAPI {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, int dwExtraInfo);
}
"@

$targetPath = "''' + abs_path.replace('"', '`"') + '''"
$hwnd = 0

# Strategy 1: Check if the folder is ALREADY open using Shell.Application (robust)
try {
    $shell = New-Object -ComObject Shell.Application
    # Loop through all open explorer windows
    foreach ($win in $shell.Windows()) {
        # Check if it has a LocationURL (IE/Filesystem)
        if ($win.LocationURL) {
            # Convert URL file:///C:/... to regular path
            try {
                $uri = New-Object System.Uri($win.LocationURL)
                $winPath = $uri.LocalPath
                # Compare paths (case-insensitive)
                if ($winPath -eq $targetPath) {
                    $hwnd = $win.HWND
                    break
                }
            } catch {}
        }
    }
} catch {}

# Hack: Simulate Alt key press to relax Foreground Lock (ASFW) before any focus attempts
[WinAPI]::keybd_event(0x12, 0, 0, 0) # Alt Down
Start-Sleep -Milliseconds 5
[WinAPI]::keybd_event(0x12, 0, 2, 0) # Alt Up

if ($hwnd -eq 0) {
    # Strategy 2: If not found, launch a new instance
    $proc = Start-Process explorer.exe -ArgumentList $targetPath -PassThru
    Start-Sleep -Milliseconds 600
    
    # Try to get handle from new process
    $hwnd = $proc.MainWindowHandle
    if ($hwnd -eq 0) {
        # Fallback: Find by window title (Folder Name)
        $name = Split-Path $targetPath -Leaf
        $hwnd = [WinAPI]::FindWindow($null, $name)
    }
}

# Focus logic (runs for both existing and new windows)
if ($hwnd -ne 0) {
    if ([WinAPI]::IsIconic($hwnd)) {
        [WinAPI]::ShowWindow($hwnd, 9)  # SW_RESTORE
    }
    [WinAPI]::SetForegroundWindow($hwnd)
}
'''
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps_cmd], 
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, abs_path])
    except Exception as e:
        logger.error(f"Failed to force open path {path}: {e}")


@app.post("/api/tools/open-folder")
def open_folder(folder_type: str, dojo: str | None = None):
    """Open a specific folder in the OS file explorer."""
    # Validate dojo name to prevent path traversal
    if dojo:
        try:
            dojo = _validate_voice_name(dojo)
        except ValueError as e:
            return Response(content=f"Invalid dojo name: {e}", status_code=400)
    
    path = None
    if folder_type == "voices":
        path = SCRIPT_DIR.parent / "voices"
    elif folder_type == "dojo" and dojo:
        path = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo" / f"{dojo}_dojo"
    elif folder_type == "dataset" and dojo:
        path = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo" / f"{dojo}_dojo" / "dataset"
    elif folder_type == "docs":
        path = SCRIPT_DIR.parent / "voices" / "HOW_TO_ADD_VOICES.md"
    
    if path and path.exists():
        _force_open_path(path)
        return {"status": "opened"}
            
    return Response(content="Path not found", status_code=404)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Prevent 404 errors for missing favicon in browser console."""
    return Response(content=b"", status_code=204)


@app.get("/api/config", tags=["Configuration"])
def get_server_config():
    """Return the current server configuration."""
    return load_config()


@app.get("/api/storage/info", tags=["System"])
def get_storage_info():
    """Gathers detailed storage usage information for the web dashboard."""
    dojo_root = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo"
    pretrained_root = dojo_root / "PRETRAINED_CHECKPOINTS"
    voices_root = SCRIPT_DIR.parent / "voices"
    
    totals = {"dojos": 0, "models": 0, "voices": 0, "docker": 0}
    
    # Dojos
    dojos = []
    if dojo_root.exists():
        for d in dojo_root.iterdir():
            if d.is_dir() and d.name.endswith("_dojo"):
                size = get_size_bytes(d)
                totals["dojos"] += size
                
                # Scan subparts
                subparts = []
                
                # 1. Training & Reference Audio (Folders)
                for sub_dir, label in [("dataset", "Training Audio"), ("target_voice_dataset", "Reference Audio")]:
                    p = d / sub_dir
                    if p.exists():
                        subparts.append({"id": sub_dir, "name": label, "size": format_bytes(get_size_bytes(p)), "type": "folder"})

                # 2. Checkpoints (Files)
                # Latest
                ckpt_dir = d / "voice_checkpoints"
                if ckpt_dir.exists():
                    ckpts = sorted(list(ckpt_dir.glob("*.ckpt")), key=lambda x: x.stat().st_mtime, reverse=True)
                    for f in ckpts:
                        subparts.append({
                            "id": f"voice_checkpoints/{f.name}", 
                            "name": f"Latest: {f.name}", 
                            "size": format_bytes(get_size_bytes(f)), 
                            "type": "checkpoint"
                        })
                # Archived
                arch_dir = d / "archived_checkpoints"
                if arch_dir.exists():
                    archs = sorted(list(arch_dir.glob("*.ckpt")), key=lambda x: x.stat().st_mtime, reverse=True)
                    for f in archs:
                        subparts.append({
                            "id": f"archived_checkpoints/{f.name}", 
                            "name": f"Archive: {f.name}", 
                            "size": format_bytes(get_size_bytes(f)), 
                            "type": "checkpoint"
                        })

                # 3. Exported Voices (Files)
                voice_dir = d / "tts_voices"
                if voice_dir.exists():
                    for f in voice_dir.rglob("*.onnx"):
                        subparts.append({
                            "id": str(f.relative_to(d)).replace("\\", "/"),
                            "name": f"Voice: {f.name}",
                            "size": format_bytes(get_size_bytes(f)),
                            "type": "voice",
                            "full_path": str(f.resolve())
                        })

                # 4. Other Big Folders
                for sub_dir, label in [("training_folder", "Working Training Data")]:
                    p = d / sub_dir
                    if p.exists():
                        subparts.append({"id": sub_dir, "name": label, "size": format_bytes(get_size_bytes(p)), "type": "folder"})
                
                dojos.append({
                    "name": d.name, 
                    "size": format_bytes(size), 
                    "path": str(d),
                    "subparts": subparts
                })
                
    # Pretrained Models
    models = []
    if pretrained_root.exists():
        for sub in ["default", "languages"]:
            path = pretrained_root / sub
            if not path.exists(): continue
            for f in path.glob("*"):
                if f.name == ".SAMPLING_RATE" or f.name.startswith("."): continue
                size = get_size_bytes(f)
                totals["models"] += size
                
                # Add descriptive names for core training bases
                display_name = f.name
                model_format = f.suffix.upper().replace(".", "") or "CKPT"
                
                if f.name == "F_voice": 
                    display_name = "Female Base Model (High Res)"
                    model_format = "CKPT"
                elif f.name == "M_voice": 
                    display_name = "Male Base Model (High Res)"
                    model_format = "CKPT"
                elif f.name == ".ESPEAK_LANGUAGE": 
                    display_name = "eSpeak-NG Language Data"
                    model_format = "DATA"
                
                models.append({
                    "name": f.name, 
                    "display_name": display_name,
                    "format": model_format,
                    "type": sub, 
                    "size": size
                })
                
    # Production Voices
    default_voices = []
    custom_voices = []
    if voices_root.exists():
        for item in voices_root.iterdir():
            if item.name == "HOW_TO_ADD_VOICES.md": continue
            
            # Special handling for the 'custom' folder to list its contents individually
            if item.is_dir() and item.name.lower() == "custom":
                for subitem in item.iterdir():
                    if subitem.name == "HOW_TO_ADD_VOICES.md": continue
                    # We only care about directories (voice packages) or .onnx files
                    if subitem.is_dir() or subitem.suffix.lower() == ".onnx":
                        size = get_size_bytes(subitem)
                        totals["voices"] += size
                        custom_voices.append({"name": subitem.name, "size": size, "is_dir": subitem.is_dir(), "is_custom": True})
                continue

            # Regular voices
            size = get_size_bytes(item)
            totals["voices"] += size
            default_voices.append({"name": item.name, "size": size, "is_dir": item.is_dir(), "is_custom": False})

    # Docker Check
    docker_installed = False
    docker_size = "0"
    try:
        # Check for the piper training image
        img_check = subprocess.run(
            ["docker", "images", "--format", "{{.Size}}", "domesticatedviking/textymcspeechy-piper:latest"],
            capture_output=True, text=True, timeout=10
        )
        if img_check.stdout.strip():
            docker_installed = True
            docker_size = img_check.stdout.strip()
            # Approximate conversion for the totals display
            if "GB" in docker_size:
                totals["docker"] = int(float(docker_size.replace("GB", "")) * (1024**3))
            elif "MB" in docker_size:
                totals["docker"] = int(float(docker_size.replace("MB", "")) * (1024**2))
    except Exception:
        pass

    return {
        "status": "success",
        "dojos": dojos,
        "models": [{"name": m["name"], "display_name": m.get("display_name"), "format": m.get("format"), "size": format_bytes(m["size"])} for m in models],
        "default_voices": [{"name": v["name"], "size": format_bytes(v["size"]), "format": "ONNX" if not v["is_dir"] else "FOLDER"} for v in default_voices],
        "custom_voices": [{"name": v["name"], "size": format_bytes(v["size"]), "format": "ONNX" if not v["is_dir"] else "FOLDER"} for v in custom_voices],
        "docker_image_size": docker_size if docker_installed else None,
        "total_managed_size": format_bytes(sum(totals.values()))
    }


@app.post("/api/tools/prune-docker")
def prune_docker_action():
    """Removes the 17GB Piper VITS training image."""
    try:
        subprocess.run(["docker", "rmi", "domesticatedviking/textymcspeechy-piper:latest"], 
                      capture_output=True, text=True, timeout=30)
        return {"status": "success", "message": "Docker image pruned."}
    except Exception as e:
        return {"status": "error", "message": f"Failed to prune: {str(e)}"}


@app.delete("/api/storage/delete")
def delete_storage_item_final(type: str, name: str, subpath: str = None):
    """Deletes an item from disk."""
    # Invisible security: Validate type parameter
    allowed_types = ["media", "dojo", "checkpoint", "voice", "model"]
    if type not in allowed_types:
        return Response(content="Invalid type parameter", status_code=400)
    
    # Validate name to prevent path traversal
    if name and (".." in name or "\\" in name or "/" in name or name.startswith(".")):
        return Response(content="Invalid name parameter", status_code=400)
    
    path = None
    if type == "media":
        # Special case: Purge all logs and history
        try:
            # Clear central events log
            history_file = SCRIPT_DIR.parent / "logs" / "events.jsonl"
            if history_file.exists():
                history_file.unlink()
            
            # Reset current server log (cannot delete while open by logger)
            if Path(log_file).exists():
                with open(log_file, "w") as f:
                    f.truncate(0)
            
            return {"status": "success", "message": "Purged session logs and history."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to purge logs: {str(e)}"}

    if type == "dojo":
        # Delegate full dojo deletion to training_manager which handles process cleanup
        if not subpath:
            voice_name = name.replace("_dojo", "")
            res = training_manager.delete_dojo(voice_name)
            if res.get("ok"):
                return {"status": "success", "message": f"Deleted Dojo {voice_name}"}
            else:
                return {"status": "error", "message": res.get("error", "Failed to delete dojo")}

        path = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo" / name
        if subpath:
            path = path / subpath
    elif type == "model":
        root = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo" / "PRETRAINED_CHECKPOINTS"
        for sub in ["default", "languages"]:
            p = root / sub / name
            if p.exists():
                path = p
                break
    elif type == "voice":
        # First try direct path in voices root
        path = SCRIPT_DIR.parent / "voices" / name
        if not path.exists():
            # If not found, try looking inside the custom/ folder
            path = SCRIPT_DIR.parent / "voices" / "custom" / name
        
        # Security: ensure it's still inside voices root using is_relative_to()
        root = (SCRIPT_DIR.parent / "voices").resolve()
        try:
            if path.exists() and not path.resolve().is_relative_to(root):
                path = None
        except ValueError:
            path = None

    if not path or not path.exists():
        return {"status": "error", "message": "Item not found"}
    
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        
        if type == "voice":
            invalidate_voice_cache()
            
        return {"status": "success", "message": f"Deleted {name}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/config")
async def update_server_config(new_cfg: dict):
    """Update the server configuration file."""
    config_path = SCRIPT_DIR / "config.json"
    try:
        # If the UI sets a new default voice, ensure any env override doesn't pin the model.
        if isinstance(new_cfg, dict) and "voice_model" in new_cfg:
            os.environ.pop(PIPER_MODEL_ENV, None)

        current = load_config()
        current.update(new_cfg)
        # Use async file I/O to avoid blocking
        json_str = json.dumps(current, indent=4)
        await asyncio.to_thread(
            config_path.write_text, json_str, encoding="utf-8"
        )
        return {"ok": True}
    except Exception as e:
        return Response(content=str(e), status_code=500)


@app.post("/api/system/restart")
def restart_server():
    """Immediately terminates the server process. Assumes a manager will restart it."""
    logger.info("Restart requested via API.")
    def _shutdown():
        time.sleep(1)
        os._exit(0)
    threading.Thread(target=_shutdown).start()
    return {"status": "restarting"}


@app.post("/api/tools/download-models")
def download_starter_models():
    """Downloads the starter voice models in the background."""
    def _download():
        voices_root = SCRIPT_DIR.parent
        # Pre-compute items list to avoid repeated dict access
        models_to_download = list(STARTER_MODELS.items())
        for name, info in models_to_download:
            onnx_path = voices_root / info["rel_path"]
            json_path = onnx_path.with_suffix(onnx_path.suffix + ".json")
            onnx_path.parent.mkdir(parents=True, exist_ok=True)
            
            if not onnx_path.exists():
                logger.info(f"Downloading model: {name}...")
                try:
                    urllib.request.urlretrieve(info["onnx_url"], onnx_path)
                    logger.info(f"  Saved {name}")
                except Exception as e:
                    logger.error(f"Failed to download {name}: {e}")
            
            if not json_path.exists():
                try:
                    urllib.request.urlretrieve(info["json_url"], json_path)
                    logger.info(f"  Saved config for {name}")
                except Exception as e:
                    logger.error(f"Failed to download config for {name}: {e}")
        invalidate_voice_cache()

    threading.Thread(target=_download).start()
    return {"status": "download_started"}


@app.post("/api/tools/download-piper")
def download_piper_tool():
    """Triggers the Piper binary download process."""
    try:
        from download_piper import download_and_extract_piper
        threading.Thread(target=download_and_extract_piper, args=(SCRIPT_DIR,)).start()
        return {"status": "download_started"}
    except Exception as e:
        return Response(content=str(e), status_code=500)


@app.get("/dojo_data/{path:path}")
async def serve_dojo_file(path: str):
    """Explicitly serve files from the dojo directory to ensure playback works."""
    file_path = (DOJO_ROOT / path).resolve()
    # Security: Ensure the resolved path is still inside DOJO_ROOT using is_relative_to()
    try:
        if not file_path.is_relative_to(DOJO_ROOT.resolve()):
            raise HTTPException(status_code=403, detail="Access denied")
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
        
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    
    # Log the failure for debugging
    logger.warning(f"Audio file not found: {file_path}")
    raise HTTPException(status_code=404, detail="File not found")


@app.get("/api/gpu-stats", tags=["System"])
async def get_gpu_stats():
    """
    Get real-time GPU temperature and utilization metrics.
    
    Returns GPU utilization, memory usage, and temperature using nvidia-smi.
    Useful for monitoring hardware during training.
    """
    try:
        # Query nvidia-smi
        # util.gpu: GPU utilization (%)
        # memory.used: VRAM used (MiB)
        # memory.total: VRAM total (MiB)
        # temperature.gpu: Core temperature (C)
        # We use a timeout to prevent hanging if the driver is unresponsive
        
        # Windows: Suppress console window popup
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=False,
            startupinfo=startupinfo
        )
        
        if result.returncode != 0:
            return {"available": False, "error": "nvidia-smi failed"}

        output = result.stdout.strip()
        if not output:
             return {"available": False, "error": "No GPU data returned"}
        
        # Take the first line (GPU 0)
        first_line = output.split('\n')[0]
        parts = [x.strip() for x in first_line.split(',')]
        
        if len(parts) < 4:
            return {"available": False, "error": "Invalid GPU data format"}

        return {
            "available": True,
            "utilization_gpu": int(parts[0]),
            "memory_used_mb": int(parts[1]),
            "memory_total_mb": int(parts[2]),
            "temperature_c": int(parts[3])
        }

    except FileNotFoundError:
        return {"available": False, "error": "nvidia-smi not found"}
    except Exception as e:
        logger.error(f"GPU stats query failed: {e}")
        return {"available": False, "error": str(e)}


def _startup_shortcut_path() -> Path:
    """Return the path to the startup shortcut/link for the current OS."""
    if os.name != "nt":
        return SCRIPT_DIR / "autostart_dummy"
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return SCRIPT_DIR / "PiperTTS Mockingbird.lnk"
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "PiperTTS Mockingbird.lnk"


@app.get("/api/startup-status")
async def get_startup_status():
    """Check if the server is set to launch on Windows startup."""
    if os.name != "nt":
        return {"success": True, "enabled": False}
    
    # Read preference from config for parity with Python UI
    cfg = load_config()
    # Default to True for new installs, matching piper_manager_ui.py
    enabled = cfg.get("launch_on_startup", True)
    
    return {"success": True, "enabled": enabled}


@app.post("/api/set-startup")
async def set_startup(request: Request):
    """Enable or disable server launch on Windows startup."""
    try:
        data = await request.json()
        enabled = data.get("enabled", False)
        
        # Update config.json to maintain parity with Python UI
        cfg = load_config()
        cfg["launch_on_startup"] = enabled
        config_path = SCRIPT_DIR / "config.json"
        try:
            config_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write config.json: {e}")
            
        if os.name != 'nt':
            return {"success": True, "message": "Setting saved (Windows-only feature)"}

        shortcut_path = _startup_shortcut_path()
        if enabled:
            if not shortcut_path.exists():
                launcher_vbs = SCRIPT_DIR.parent / "launchers" / "Open Piper Server.vbs"
                if launcher_vbs.exists():
                    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
                    # WindowStyle = 7 means "Minimized"
                    ps_cmd = (
                        f"$WshShell = New-Object -ComObject WScript.Shell; "
                        f"$Shortcut = $WshShell.CreateShortcut('{str(shortcut_path)}'); "
                        f"$Shortcut.TargetPath = '{str(launcher_vbs)}'; "
                        f"$Shortcut.WorkingDirectory = '{str(SCRIPT_DIR.parent)}'; "
                        f"$Shortcut.WindowStyle = 7; "
                        f"$Shortcut.Save()"
                    )
                    subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], 
                                 check=False, capture_output=True, creationflags=0x08000000)
                    logger.info(f"Created startup shortcut: {shortcut_path}")
        else:
            if shortcut_path.exists():
                shortcut_path.unlink()
                logger.info(f"Removed startup shortcut: {shortcut_path}")
        
        return {"success": True, "message": "Startup preference updated"}
    except Exception as e:
        logger.error(f"Failed to set startup: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/desktop-shortcut-status")
async def get_desktop_shortcut_status():
    """Check if the desktop shortcut exists."""
    try:
        if os.name == 'nt':
            userprofile = os.environ.get('USERPROFILE')
            if not userprofile:
                return {"success": True, "exists": False}
            desktop = Path(userprofile) / "Desktop"
            shortcut_path = desktop / "PiperTTS Mockingbird.lnk"
        elif sys.platform == "darwin":
            desktop = Path.home() / "Desktop"
            shortcut_path = desktop / "PiperTTS Mockingbird.command"
        else:
            desktop = Path.home() / "Desktop"
            shortcut_path = desktop / "pipertts-mockingbird.desktop"
        
        exists = shortcut_path.exists() if desktop.exists() else False
        return {"success": True, "exists": exists}
    except Exception as e:
        logger.error(f"Error checking desktop shortcut status: {e}")
        return {"success": True, "exists": False}


@app.post("/api/create-desktop-shortcut")
async def create_desktop_shortcut():
    """Create a desktop shortcut to the PiperTTS Mockingbird Dashboard."""
    try:
        # Update config.json to maintain parity with Python UI
        cfg = load_config()
        cfg["desktop_shortcut"] = True
        config_path = SCRIPT_DIR / "config.json"
        try:
            config_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write config.json: {e}")

        if os.name == 'nt':
            # Windows: Create .lnk shortcut
            userprofile = os.environ.get('USERPROFILE')
            if not userprofile:
                return {"success": False, "error": "USERPROFILE environment variable not found"}
                
            desktop = Path(userprofile) / "Desktop"
            if not desktop.exists():
                return {"success": False, "error": "Desktop directory not found"}
            shortcut_path = desktop / "PiperTTS Mockingbird.lnk"
            
            launcher_vbs = SCRIPT_DIR.parent / "Open PiperTTS Mockingbird (Windows).vbs"
            if not launcher_vbs.exists():
                return {"success": False, "error": "Launcher VBS not found"}
                
            # Try to use assets/mockingbird.ico if available
            icon_path = SCRIPT_DIR.parent / "assets" / "mockingbird.ico"
            icon_location = f"{str(icon_path)}, 0" if icon_path.exists() else "shell32.dll, 44"
            
            ps_cmd = (
                f"$WshShell = New-Object -ComObject WScript.Shell; "
                f"$Shortcut = $WshShell.CreateShortcut('{str(shortcut_path)}'); "
                f"$Shortcut.TargetPath = '{str(launcher_vbs)}'; "
                f"$Shortcut.WorkingDirectory = '{str(SCRIPT_DIR.parent)}'; "
                f"$Shortcut.IconLocation = '{icon_location}'; "
                f"$Shortcut.Description = 'PiperTTS Mockingbird Manager'; "
                f"$Shortcut.Save()"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], 
                         check=False, capture_output=True, creationflags=0x08000000)
            logger.info(f"Created Windows desktop shortcut: {shortcut_path}")
            return {"success": True, "message": "Desktop shortcut created"}
            
        elif sys.platform == "darwin":
            # macOS: Create .command script
            home = Path.home()
            desktop = home / "Desktop"
            if not desktop.exists():
                return {"success": False, "error": "Desktop directory not found"}
            shortcut_path = desktop / "PiperTTS Mockingbird.command"
            
            python_exe = sys.executable
            manager_script = SCRIPT_DIR / "piper_manager_ui.py"
            
            script_content = f"""#!/bin/bash
cd "{SCRIPT_DIR.parent}"
"{python_exe}" "{manager_script}"
"""
            
            shortcut_path.write_text(script_content, encoding="utf-8")
            # Make executable
            os.chmod(shortcut_path, 0o755)
            logger.info(f"Created macOS desktop shortcut: {shortcut_path}")
            return {"success": True, "message": "Desktop shortcut created"}
            
        else:
            # Linux: Create .desktop file
            home = Path.home()
            desktop = home / "Desktop"
            if not desktop.exists():
                return {"success": False, "error": "Desktop directory not found"}
            shortcut_path = desktop / "pipertts-mockingbird.desktop"
            
            python_exe = sys.executable
            manager_script = SCRIPT_DIR / "piper_manager_ui.py"
            
            # Prefer .png for Linux, fallback to .ico
            icon_png = SCRIPT_DIR.parent / "assets" / "mockingbird.png"
            icon_ico = SCRIPT_DIR.parent / "assets" / "mockingbird.ico"
            icon_str = ""
            if icon_png.exists():
                icon_str = str(icon_png)
            elif icon_ico.exists():
                icon_str = str(icon_ico)
            
            desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=PiperTTS Mockingbird
Comment=Text-to-Speech Manager
Exec=sh -c 'cd "{SCRIPT_DIR.parent}" && "{python_exe}" "{manager_script}"'
Path={SCRIPT_DIR.parent}
Icon={icon_str}
Terminal=false
Categories=AudioVideo;Audio;
"""
            
            shortcut_path.write_text(desktop_content, encoding="utf-8")
            # Make executable
            os.chmod(shortcut_path, 0o755)
            logger.info(f"Created Linux desktop shortcut: {shortcut_path}")
            return {"success": True, "message": "Desktop shortcut created"}
            
    except Exception as e:
        logger.error(f"Failed to create desktop shortcut: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/remove-desktop-shortcut")
async def remove_desktop_shortcut():
    """Remove the desktop shortcut."""
    try:
        # Update config.json to maintain parity with Python UI
        cfg = load_config()
        cfg["desktop_shortcut"] = False
        config_path = SCRIPT_DIR / "config.json"
        try:
            config_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write config.json: {e}")

        if os.name == 'nt':
            # Windows: Remove .lnk file
            userprofile = os.environ.get('USERPROFILE')
            if not userprofile:
                return {"success": True}
                
            shortcut_path = Path(userprofile) / "Desktop" / "PiperTTS Mockingbird.lnk"
            if shortcut_path.exists():
                shortcut_path.unlink()
                logger.info(f"Removed Windows desktop shortcut: {shortcut_path}")
                
        elif sys.platform == "darwin":
            # macOS: Remove .command file
            home = Path.home()
            shortcut_path = home / "Desktop" / "PiperTTS Mockingbird.command"
            if shortcut_path.exists():
                shortcut_path.unlink()
                logger.info(f"Removed macOS desktop shortcut: {shortcut_path}")
                
        else:
            # Linux: Remove .desktop file
            home = Path.home()
            shortcut_path = home / "Desktop" / "pipertts-mockingbird.desktop"
            if shortcut_path.exists():
                shortcut_path.unlink()
                logger.info(f"Removed Linux desktop shortcut: {shortcut_path}")
            
        return {"success": True, "message": "Desktop shortcut removed"}
    except Exception as e:
        logger.error(f"Failed to remove desktop shortcut: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/run-diagnostic")
async def run_diagnostic():
    """Run system health checks."""
    checks = []
    
    # Check Piper Executable
    try:
        exe = resolve_piper_exe()
        if exe:
            exe_path = Path(exe)
            if exe_path.exists() or shutil.which(exe):
                checks.append({"name": "Piper Engine", "passed": True, "message": f"Found at {exe}"})
            else:
                checks.append({"name": "Piper Engine", "passed": False, "message": "Piper executable configured but not found on disk"})
        else:
            checks.append({"name": "Piper Engine", "passed": False, "message": "Piper executable could not be resolved"})
    except Exception as e:
        logger.error(f"Diagnostic Error (Piper): {e}")
        checks.append({"name": "Piper Engine", "passed": False, "message": str(e)})

    # Check Voices Folder
    try:
        voices_dir = SCRIPT_DIR.parent / "voices"
        if voices_dir.exists():
            onnx_files = list(voices_dir.rglob("*.onnx"))
            if onnx_files:
                checks.append({"name": "Voice Models", "passed": True, "message": f"Found {len(onnx_files)} voice(s)"})
            else:
                checks.append({"name": "Voice Models", "passed": False, "message": "No .onnx models found in voices/"})
        else:
            checks.append({"name": "Voice Models", "passed": False, "message": "Voices directory missing"})
    except Exception as e:
        logger.error(f"Diagnostic Error (Voices): {e}")
        checks.append({"name": "Voice Models", "passed": False, "message": str(e)})

    # Check GPU
    try:
        # Use a timeout of 5s for the GPU check call
        gpu = await asyncio.wait_for(get_gpu_stats(), timeout=5.0)
        if gpu.get("available"):
            checks.append({"name": "GPU Acceleration", "passed": True, "message": f"NVIDIA GPU Active ({gpu.get('utilization_gpu')}% load)"})
        else:
            checks.append({"name": "GPU Acceleration", "passed": True, "message": "Running on CPU (No NVIDIA GPU detected)"})
    except asyncio.TimeoutError:
        checks.append({"name": "GPU Acceleration", "passed": True, "message": "GPU check timed out; assuming CPU mode"})
    except Exception as e:
        logger.error(f"Diagnostic Error (GPU): {e}")
        checks.append({"name": "GPU Acceleration", "passed": True, "message": f"GPU check error: {str(e)} (defaulting to CPU)"})

    # Check Config
    try:
        config_path = SCRIPT_DIR / "config.json"
        if config_path.exists():
            try:
                json.loads(config_path.read_text(encoding="utf-8"))
                checks.append({"name": "Configuration", "passed": True, "message": "config.json is valid"})
            except Exception:
                checks.append({"name": "Configuration", "passed": False, "message": "config.json is corrupted"})
        else:
            checks.append({"name": "Configuration", "passed": True, "message": "Using default settings (no config.json)"})
    except Exception as e:
        checks.append({"name": "Configuration", "passed": False, "message": str(e)})

    # Check Startup Shortcut cache/consistency
    try:
        if os.name == 'nt':
            shortcut_path = _startup_shortcut_path()
            cfg = load_config()
            should_be_enabled = cfg.get("launch_on_startup", False)
            is_enabled = shortcut_path.exists()
            if should_be_enabled == is_enabled:
                checks.append({"name": "Startup Sync", "passed": True, "message": "Settings match system state"})
            else:
                checks.append({"name": "Startup Sync", "passed": False, "message": f"Config mismatch: Config={should_be_enabled}, Disk={is_enabled}"})
    except Exception as e:
        logger.error(f"Diagnostic Error (Startup): {e}")
        # Not a critical failure for the whole system
        checks.append({"name": "Startup Sync", "passed": True, "message": f"Could not check startup state: {e}"})

    return {"success": True, "checks": checks}


def _ensure_guides_generated():
    """Mirror logic from Python UI to ensure HTML guides are generated from Markdown source."""
    # 1. Voice Guide
    try:
        guide_md = SCRIPT_DIR.parent / "voices" / "HOW_TO_ADD_VOICES.md"
        template = SCRIPT_DIR / "voice_guide_template.html"
        output = SCRIPT_DIR.parent / "Voice_Guide.html"
        
        if guide_md.exists() and template.exists():
            # Simply check if output exists, or if MD is newer
            if not output.exists() or guide_md.stat().st_mtime > output.stat().st_mtime:
                # Basic generation logic (placeholder for actual markdown conversion if template requires injection)
                # For now we assume if it exists, it was generated recently enough or can be opened.
                # The Python UI does the actual injection.
                pass
    except Exception as e:
        logger.error(f"Guide generation check failed: {e}")


@app.post("/api/open-logs-folder")
async def open_logs_folder():
    """Open the logs folder in File Explorer."""
    try:
        logs_dir = SCRIPT_DIR.parent / "logs"
        if not logs_dir.exists():
            logs_dir.mkdir(parents=True, exist_ok=True)
        
        _force_open_path(logs_dir)
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to open logs folder: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/open-python-dashboard")
async def open_python_dashboard():
    """Open the Python Manager Dashboard UI."""
    try:
        # 1. Force Close existing instances first (as requested by user)
        # This ensures the new window appears in the foreground by restarting it.
        if os.name == 'nt':
            ps_kill = '''
$titles = @("PiperTTS Mockingbird • Manager Dashboard", "PiperTTS Mockingbird")
Get-Process | Where-Object { 
    $p = $_
    $titles | Where-Object { $p.MainWindowTitle -like "*$_*" }
} | Stop-Process -Force -ErrorAction SilentlyContinue
'''
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_kill], 
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            
            # Brief pause to ensure cleanup
            await asyncio.sleep(0.5)

        # 2. Launch new instance
        # Check root directory for launchers
        root = SCRIPT_DIR.parent
        # Prioritize the PiperTTS Mockingbird branding to match the UI
        launcher_vbs = root / "Open PiperTTS Mockingbird (Windows).vbs"
        
        if launcher_vbs.exists() and os.name == 'nt':
            logger.info(f"Opening Python Dashboard via {launcher_vbs}")
            os.startfile(str(launcher_vbs.resolve()))
            return {"success": True}
        
        # Fallback to direct script execution if VBS is missing
        ui_script = SCRIPT_DIR / "piper_manager_ui.py"


        if ui_script.exists():
            python_exe = sys.executable
            # Try to use pythonw for windowless launch on Windows
            if os.name == "nt":
                w_exe = Path(python_exe).parent / "pythonw.exe"
                if w_exe.exists():
                    python_exe = str(w_exe)
            
            logger.info(f"Opening Python Dashboard via fallback script: {ui_script}")
            subprocess.Popen([python_exe, str(ui_script)], 
                           cwd=str(SCRIPT_DIR), 
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == 'nt' else 0)
            return {"success": True}
            
        return {"success": False, "error": "Manager UI launcher or script not found"}
    except Exception as e:
        logger.error(f"Failed to open Python dashboard: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/open-webui-guide")
async def open_webui_guide():
    """Open the WebUI User Manual HTML."""
    try:
        guide_path = SCRIPT_DIR.parent / "WebUI_User_Manual.html"
        if not guide_path.exists():
            # Fallback to MD if HTML is missing
            guide_path = SCRIPT_DIR.parent / "WEBUI_USER_MANUAL.md"
            
        if guide_path.exists():
            _force_open_path(guide_path)
            return {"success": True}
        return {"success": False, "error": "User Manual (HTML or MD) not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/open-add-voices-guide")
async def open_add_voices_guide():
    """Open the Add Voices Guide HTML."""
    try:
        guide_path = SCRIPT_DIR.parent / "Voice_Guide.html"
        if not guide_path.exists():
            # Fallback to source MD
            guide_path = SCRIPT_DIR.parent / "voices" / "HOW_TO_ADD_VOICES.md"
            
        if guide_path.exists():
            _force_open_path(guide_path)
            return {"success": True}
        return {"success": False, "error": "Voice Guide not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- Web Dashboard ---
WEB_DIR = SCRIPT_DIR / "web"

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the dashboard index page at the root URL."""
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return "<h1>Piper TTS Server</h1><p>Dashboard not found in src/web/index.html</p>"

# ==================== Home Assistant & Wyoming Integration ====================

# Initialize HA exporter
VOICES_DIR = SCRIPT_DIR.parent / "voices"
HA_EXPORT_DIR = SCRIPT_DIR.parent / "exports" / "home_assistant"
ha_exporter = HomeAssistantExporter(VOICES_DIR, HA_EXPORT_DIR)

# Wyoming server instance (started/stopped via API)
wyoming_server: Optional[WyomingPiperServer] = None
wyoming_task: Optional[asyncio.Task] = None
wyoming_lock = asyncio.Lock()


@app.get("/api/ha/list_voices")
async def api_ha_list_voices():
    """Get list of voices ready for Home Assistant export."""
    try:
        voices = ha_exporter.list_exportable_voices()
        return {"success": True, "voices": voices}
    except Exception as e:
        logger.error(f"HA list voices error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/ha/export/{voice_name}")
async def api_ha_export_voice(voice_name: str):
    """
    Simulate export for Home Assistant. 
    In the new lean model, we don't save to disk; we just verify the voice exists.
    """
    try:
        if not re.match(r'^[a-zA-Z0-9_-]{1,64}$', voice_name):
            return {"success": False, "error": "Invalid voice name format"}
        
        # Check if voice exists (reusing the discovery logic)
        voices = ha_exporter.list_exportable_voices()
        if any(v["name"] == voice_name for v in voices):
            return {
                "success": True,
                "zip_name": f"{voice_name}_home_assistant.zip",
                "info": "Voice ready for streaming download"
            }
        return {"success": False, "error": "Voice files not found"}
            
    except Exception as e:
        logger.error(f"HA export check error for {voice_name}: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/ha/download/{voice_name}")
async def api_ha_download_export(voice_name: str):
    """Generate and stream the HA voice package on-the-fly."""
    try:
        if not re.match(r'^[a-zA-Z0-9_-]{1,64}$', voice_name):
            raise HTTPException(status_code=400, detail="Invalid voice name format")
        
        result = ha_exporter.create_voice_zip_buffer(voice_name)
        if not result:
            raise HTTPException(status_code=404, detail="Voice not found or export failed")
            
        buffer, filename = result
        
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-cache"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"HA download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/integrations/open/{name}")
async def api_open_integration_folder(name: str):
    """Open an integration folder in the file explorer."""
    try:
        allowed = ["google_docs_addon", "mockingbird_extension"]
        if name not in allowed:
            return {"success": False, "error": "Invalid integration name"}
            
        folder_path = SCRIPT_DIR.parent / "integrations" / name
        if not folder_path.exists():
            return {"success": False, "error": f"Folder {name} not found"}
            
        if sys.platform == "win32":
            _force_open_path(folder_path)
        elif sys.platform == "darwin":  # macOS
            subprocess.Popen(["open", str(folder_path)])
        else:  # linux
            subprocess.Popen(["xdg-open", str(folder_path)])
            
        return {"success": True}
    except Exception as e:
        logger.error(f"Error opening folder {name}: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/wyoming/start")
async def api_wyoming_start(host: str = "127.0.0.1", port: int = 10200):
    """Start the Wyoming protocol server."""
    global wyoming_server, wyoming_task
    
    async with wyoming_lock:
        try:
            # Validate host parameter
            valid_hosts = ["127.0.0.1", "localhost", "0.0.0.0"]
            if host not in valid_hosts:
                return {"success": False, "error": f"Invalid host. Use 127.0.0.1 (localhost only) or 0.0.0.0 (network access)"}
            
            # Validate port range
            if not (1024 <= port <= 65535):
                return {"success": False, "error": "Port must be between 1024 and 65535"}
            
            if wyoming_server and wyoming_server.is_running():
                return {"success": False, "error": "Wyoming server already running"}
            
            # Clean up any previous task
            if wyoming_task and not wyoming_task.done():
                wyoming_task.cancel()
                try:
                    await wyoming_task
                except asyncio.CancelledError:
                    pass
            
            # Find Piper executable
            piper_exe = SCRIPT_DIR / "piper" / "piper.exe"
            if not piper_exe.exists():
                piper_exe = SCRIPT_DIR / "piper" / "piper"  # Linux/Mac
            
            if not piper_exe.exists():
                return {"success": False, "error": "Piper executable not found"}
            
            # Create Wyoming server
            wyoming_server = WyomingPiperServer(
                voices_dir=VOICES_DIR,
                piper_exe=piper_exe,
                host=host,
                port=port
            )
            
            # Start in background task
            wyoming_task = asyncio.create_task(wyoming_server.start())
            wyoming_server._server_task = wyoming_task
            
            # Give it a moment to start
            await asyncio.sleep(0.1)
            
            logger.info(f"Wyoming server starting on {host}:{port}")
            return {
                "success": True,
                "host": host,
                "port": port,
                "message": "Wyoming server started",
                "warning": "Server accessible from entire network! Use 127.0.0.1 for localhost only." if host == "0.0.0.0" else None
            }
            
        except Exception as e:
            logger.error(f"Wyoming start error: {e}", exc_info=True)
            # Cleanup on error
            if wyoming_task:
                wyoming_task.cancel()
            wyoming_server = None
            wyoming_task = None
            return {"success": False, "error": str(e)}


@app.post("/api/wyoming/stop")
async def api_wyoming_stop():
    """Stop the Wyoming protocol server."""
    global wyoming_server, wyoming_task
    
    async with wyoming_lock:
        try:
            if not wyoming_server or not wyoming_server.is_running():
                return {"success": False, "error": "Wyoming server not running"}
            
            await wyoming_server.stop()
            
            if wyoming_task and not wyoming_task.done():
                wyoming_task.cancel()
                try:
                    await asyncio.wait_for(wyoming_task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            wyoming_server = None
            wyoming_task = None
            
            logger.info("Wyoming server stopped")
            return {"success": True, "message": "Wyoming server stopped"}
            
        except Exception as e:
            logger.error(f"Wyoming stop error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


@app.get("/api/wyoming/status")
async def api_wyoming_status():
    """Get Wyoming server status."""
    try:
        is_running = wyoming_server and wyoming_server.is_running()
        
        status = {
            "running": is_running,
            "voices_count": len(wyoming_server.handler.voices) if is_running else 0
        }
        
        if is_running:
            status["host"] = wyoming_server.host
            status["port"] = wyoming_server.port
            
            # Detect local network IP for display
            if wyoming_server.host == "0.0.0.0":
                try:
                    import socket
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(("8.8.8.8", 80))
                    local_ip = s.getsockname()[0]
                    s.close()
                    status["local_ip"] = local_ip
                except Exception:
                    status["local_ip"] = None
            else:
                status["local_ip"] = wyoming_server.host
        
        return {"success": True, "status": status}
        
    except Exception as e:
        logger.error(f"Wyoming status error: {e}")
        return {"success": False, "error": str(e)}


def _wyoming_startup_shortcut_path() -> Path:
    """Return the path to the Wyoming startup shortcut."""
    if os.name != "nt":
        return SCRIPT_DIR / "wyoming_autostart_dummy"
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return SCRIPT_DIR / "PiperTTS Wyoming.lnk"
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "PiperTTS Wyoming.lnk"


@app.get("/api/wyoming/startup")
async def get_wyoming_startup_status():
    """Check if Wyoming server is set to launch on Windows startup."""
    if os.name != "nt":
        return {"success": True, "enabled": False}
    
    cfg = load_config()
    enabled = cfg.get("wyoming_launch_on_startup", False)
    
    return {"success": True, "enabled": enabled}


@app.post("/api/wyoming/startup")
async def set_wyoming_startup(request: Request):
    """Enable or disable Wyoming server launch on Windows startup."""
    try:
        data = await request.json()
        enabled = data.get("enabled", False)
        
        # Update config.json
        cfg = load_config()
        cfg["wyoming_launch_on_startup"] = enabled
        config_path = SCRIPT_DIR / "config.json"
        try:
            config_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write config.json: {e}")
            
        if os.name != 'nt':
            return {"success": True, "message": "Setting saved (Windows-only feature)"}

        shortcut_path = _wyoming_startup_shortcut_path()
        if enabled:
            if not shortcut_path.exists():
                # Create a VBS launcher for Wyoming server
                wyoming_vbs_path = SCRIPT_DIR.parent / "launchers" / "Open Wyoming Server.vbs"
                
                # If it doesn't exist, create it
                if not wyoming_vbs_path.exists():
                    wyoming_vbs_path.parent.mkdir(parents=True, exist_ok=True)
                    vbs_content = f'''Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Get the script directory
scriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
pythonScript = objFSO.BuildPath(scriptDir, "..\\src\\wyoming_server.py")
pythonExe = "pythonw.exe"

' Change to the src directory
srcDir = objFSO.BuildPath(scriptDir, "..\\src")
objShell.CurrentDirectory = srcDir

' Run hidden
objShell.Run pythonExe & " " & Chr(34) & pythonScript & Chr(34), 0, False
'''
                    wyoming_vbs_path.write_text(vbs_content, encoding="utf-8")
                    logger.info(f"Created Wyoming launcher VBS: {wyoming_vbs_path}")
                
                if wyoming_vbs_path.exists():
                    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
                    ps_cmd = (
                        f"$WshShell = New-Object -ComObject WScript.Shell; "
                        f"$Shortcut = $WshShell.CreateShortcut('{str(shortcut_path)}'); "
                        f"$Shortcut.TargetPath = '{str(wyoming_vbs_path)}'; "
                        f"$Shortcut.WorkingDirectory = '{str(SCRIPT_DIR.parent)}'; "
                        f"$Shortcut.WindowStyle = 7; "
                        f"$Shortcut.Save()"
                    )
                    subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], 
                                 check=False, capture_output=True, creationflags=0x08000000)
                    logger.info(f"Created Wyoming startup shortcut: {shortcut_path}")
        else:
            if shortcut_path.exists():
                shortcut_path.unlink()
                logger.info(f"Removed Wyoming startup shortcut: {shortcut_path}")
        
        return {"success": True, "message": "Wyoming startup preference updated"}
    except Exception as e:
        logger.error(f"Failed to set Wyoming startup: {e}")
        return {"success": False, "error": str(e)}


if WEB_DIR.exists():
    # Mount Dojo data so we can play audio clips in the browser
    # Mapping tts_dojo -> /dojo_data/
    DOJO_PATH = SCRIPT_DIR.parent / "training" / "make piper voice models" / "tts_dojo"
    logger.info(f"Mounting DOJO_PATH: {DOJO_PATH}")
    if DOJO_PATH.exists():
        logger.info("DOJO_PATH found, mounting to /dojo_data")
        app.mount("/dojo_data", StaticFiles(directory=str(DOJO_PATH)), name="dojo_data")
    else:
        logger.warning(f"DOJO_PATH NOT FOUND: {DOJO_PATH}")

    # Mount everything else (css, js) at the root
    app.mount("/", StaticFiles(directory=str(WEB_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    
    # ⚠️  SECURITY NOTICE:
    # This server binds to 127.0.0.1 by default for your protection.
    # If you change this to "0.0.0.0" to allow network access:
    # 1. This API has NO AUTHENTICATION - anyone on your network can control it.
    # 2. It does not use HTTPS - your text/audio travels in the clear.
    # 3. ONLY do this on a trusted home network. NEVER expose this to the internet.
    # 
    # Note: Adding these features is possible but this tool was designed for local use 
    # so we just didn't focus on it, but if you want to add that stuff please feel 
    # free to do so... this code is MIT license :)
    
    logger.info("Starting uvicorn server...")
    try:
        uvicorn.run(app, host="127.0.0.1", port=5002)
    except Exception as e:
        logger.critical(f"Uvicorn server crashed: {e}")
        raise
