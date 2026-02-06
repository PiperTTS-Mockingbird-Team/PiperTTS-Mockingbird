"""
Home Assistant Voice Export Module
Licensed under the MIT License.
Copyright (c) 2026 PiperTTS Mockingbird Developers

Handles packaging trained Piper voices for easy import into Home Assistant.
"""

import logging
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Optional
import json

logger = logging.getLogger(__name__)

class HomeAssistantExporter:
    """
    Manages the export of trained Piper voice models into a format
    compatible with Home Assistant's Piper integration.
    """
    
    def __init__(self, voices_dir: Path, export_dir: Path):
        """
        Initialize the exporter.
        
        Args:
            voices_dir: Directory containing voice model files (.onnx and .onnx.json)
            export_dir: Directory where HA-ready packages will be saved
        """
        self.voices_dir = voices_dir
        self.export_dir = export_dir
        self.export_dir.mkdir(exist_ok=True, parents=True)
        
    def list_exportable_voices(self) -> List[Dict[str, any]]:
        """
        Scan the voices directory and return a list of voices ready for export.
        
        Returns:
            List of dicts with voice metadata (name, quality, size, etc.)
        """
        voices = []
        
        # Look for .onnx files recursively in voices directory
        for onnx_file in self.voices_dir.rglob("*.onnx"):
            json_file = onnx_file.with_suffix(".onnx.json")
            
            if not json_file.exists():
                logger.warning(f"Found {onnx_file.name} but missing {json_file.name}")
                continue
            
            # Parse metadata
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                voice_info = {
                    "name": onnx_file.stem,
                    "onnx_file": str(onnx_file),
                    "json_file": str(json_file),
                    "size_mb": round(onnx_file.stat().st_size / (1024 * 1024), 2),
                    "language": metadata.get("language", {}).get("code", "unknown"),
                    "quality": metadata.get("audio", {}).get("quality", "unknown"),
                    "num_speakers": metadata.get("num_speakers", 1),
                    "sample_rate": metadata.get("audio", {}).get("sample_rate", 22050)
                }
                
                voices.append(voice_info)
                
            except Exception as e:
                logger.error(f"Error reading metadata for {onnx_file.name}: {e}")
        
        return sorted(voices, key=lambda x: x["name"])
    
    def create_voice_zip_buffer(self, voice_name: str, include_readme: bool = True) -> Optional[tuple]:
        """
        Package a voice for Home Assistant into an in-memory buffer.
        Returns (buffer, filename) or None.
        """
        import io
        
        # Validate voice_name
        if not voice_name or '/' in voice_name or '\\' in voice_name or '..' in voice_name:
            return None
        
        onnx_file = self.voices_dir / f"{voice_name}.onnx"
        json_file = self.voices_dir / f"{voice_name}.onnx.json"
        
        # Recursively find if not in root
        if not onnx_file.exists():
            matches = list(self.voices_dir.rglob(f"{voice_name}.onnx"))
            if matches:
                onnx_file = matches[0]
                json_file = onnx_file.with_suffix(".onnx.json")
        
        if not onnx_file.exists() or not json_file.exists():
            return None
            
        buffer = io.BytesIO()
        try:
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(onnx_file, arcname=f"{voice_name}.onnx")
                zf.write(json_file, arcname=f"{voice_name}.onnx.json")
                if include_readme:
                    zf.writestr("README.txt", self._generate_readme(voice_name, json_file))
            
            buffer.seek(0)
            return buffer, f"{voice_name}_home_assistant.zip"
        except Exception as e:
            logger.error(f"Memory export failed for {voice_name}: {e}")
            return None

    def export_voice(self, voice_name: str, include_readme: bool = True) -> Optional[Path]:
        """
        Package a voice for Home Assistant.
        
        Args:
            voice_name: Name of the voice (stem of .onnx file)
            include_readme: Whether to include installation instructions
            
        Returns:
            Path to the created zip file, or None if export failed
        """
        # Validate voice_name to prevent path traversal
        if not voice_name or '/' in voice_name or '\\' in voice_name or '..' in voice_name:
            logger.error(f"Invalid voice name: {voice_name}")
            return None
        
        onnx_file = self.voices_dir / f"{voice_name}.onnx"
        json_file = self.voices_dir / f"{voice_name}.onnx.json"
        
        # If not found in root, search recursively
        if not onnx_file.exists():
            matches = list(self.voices_dir.rglob(f"{voice_name}.onnx"))
            if matches:
                onnx_file = matches[0]
                json_file = onnx_file.with_suffix(".onnx.json")
        
        if not onnx_file.exists() or not json_file.exists():
            logger.error(f"Voice '{voice_name}' not found or incomplete at {onnx_file}")
            return None
        
        # Create zip package
        zip_path = self.export_dir / f"{voice_name}_home_assistant.zip"
        
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Add the voice files
                zf.write(onnx_file, arcname=f"{voice_name}.onnx")
                zf.write(json_file, arcname=f"{voice_name}.onnx.json")
                
                # Optionally add installation instructions
                if include_readme:
                    readme_content = self._generate_readme(voice_name, json_file)
                    zf.writestr("README.txt", readme_content)
            
            logger.info(f"Exported {voice_name} to {zip_path}")
            return zip_path
            
        except Exception as e:
            logger.error(f"Failed to export {voice_name}: {e}")
            return None
    
    def _generate_readme(self, voice_name: str, json_file: Path) -> str:
        """Generate installation instructions for Home Assistant."""
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            language = metadata.get("language", {}).get("code", "en-us")
            quality = metadata.get("audio", {}).get("quality", "medium")
            
        except Exception:
            language = "en-us"
            quality = "medium"
        
        return f"""
========================================
Home Assistant Voice Installation
========================================

Voice Name: {voice_name}
Language: {language}
Quality: {quality}

INSTALLATION STEPS:
-------------------

1. Extract this ZIP file to get the .onnx and .onnx.json files

2. Copy both files to your Home Assistant Piper voices directory:
   
   Location varies by installation type:
   - Docker: /data/piper/voices/
   - Home Assistant OS: /config/piper/voices/
   - Supervised: /usr/share/hassio/homeassistant/piper/voices/
   
3. In Home Assistant, go to:
   Settings → Voice Assistants → Piper → Add Language

4. Your custom voice "{voice_name}" should appear in the dropdown

5. Select it and click "Add"

TROUBLESHOOTING:
----------------

- If the voice doesn't appear, restart Home Assistant
- Make sure both .onnx and .onnx.json files are in the same directory
- Check Home Assistant logs for any Piper-related errors

For more help, see:
https://www.home-assistant.io/integrations/piper/

Generated by PiperTTS Mockingbird
"""
