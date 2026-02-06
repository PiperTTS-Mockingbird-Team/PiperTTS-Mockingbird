from __future__ import annotations

import json
import os
import re
import shutil
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

def validate_voice_name(name: str, strict: bool = True) -> str:
    """
    Validates a voice name to prevent path traversal.
    Allows most characters except path separators and null bytes.
    Max length: 128 characters.
    
    Args:
        name: The name to validate
        strict: If False, allows existing names that don't match pattern (backward compatibility)
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Name is required")
    
    if len(name) > 128:
        raise ValueError("Name too long (max 128 characters)")
    
    # Just prevent path traversal and dangerous characters
    if ".." in name or "/" in name or "\\" in name or name.startswith(".") or "\0" in name:
        raise ValueError("Invalid name. Cannot contain path separators, null bytes, or start with dot.")
    
    return name

def validate_nickname(nickname: str) -> str:
    """
    Validates a nickname (display name) - less strict than voice names.
    Allows most characters except control characters and null bytes.
    Max length: 128 characters.
    """
    nickname = (nickname or "").strip()
    if not nickname:
        raise ValueError("Nickname is required")
    
    if len(nickname) > 128:
        raise ValueError("Nickname too long (max 128 characters)")
    
    # Block control characters and null bytes
    if any(ord(c) < 32 for c in nickname) or "\0" in nickname:
        raise ValueError("Nickname contains invalid control characters")
    
    return nickname

def safe_config_save(file_path: Path, config_data: dict) -> bool:
    """
    Saves a configuration dictionary to a JSON file safely.
    1. Creates a backup of the existing file (.bak).
    2. Writes to a temporary file first.
    3. Flushes and syncs to disk.
    4. Renames the temporary file to the target file name.
    """
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    bak_path = file_path.with_suffix(file_path.suffix + ".bak")
    
    try:
        # Step 1: Create backup if the file exists
        if file_path.exists():
            try:
                shutil.copy2(file_path, bak_path)
            except Exception as e:
                logger.warning(f"Could not create config backup: {e}")

        # Step 2: Write to temporary file
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        
        # Step 3: Atomic rename (mostly atomic on Windows if target doesn't exist, 
        # but replace works if it does). os.replace is atomic on most platforms.
        if os.path.exists(file_path):
            os.replace(temp_path, file_path)
        else:
            os.rename(temp_path, file_path)
            
        return True
    except Exception as e:
        logger.error(f"Failed to save config safely to {file_path}: {e}")
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        return False

def safe_config_load(file_path: Path) -> dict:
    """
    Loads a configuration dictionary from a JSON file.
    If the primary file is corrupted or missing, attempts to load from the backup.
    """
    bak_path = file_path.with_suffix(file_path.suffix + ".bak")
    
    # Try primary file
    if file_path.exists():
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to load primary config {file_path}: {e}")
            
    # Try backup file
    if bak_path.exists():
        try:
            config = json.loads(bak_path.read_text(encoding="utf-8"))
            logger.info(f"Successfully recovered config from backup: {bak_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load backup config {bak_path}: {e}")
            
    return {}
