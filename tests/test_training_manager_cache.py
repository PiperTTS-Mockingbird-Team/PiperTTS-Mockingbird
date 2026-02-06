"""Test caching optimizations in training_manager.py"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def mock_dojo_structure(tmp_path):
    """Create a minimal dojo structure for testing"""
    dojo_path = tmp_path / "test_voice_dojo"
    dataset_path = dojo_path / "dataset"
    dataset_path.mkdir(parents=True)
    
    # Create minimal metadata.csv
    metadata_path = dataset_path / "metadata.csv"
    metadata_path.write_text("1|test sample one\n2|test sample two\n", encoding="utf-8")
    
    return dojo_path


def test_get_metadata_caching(mock_dojo_structure, monkeypatch):
    """Test that get_metadata uses cache on repeated calls"""
    from src.training_manager import TrainingManager
    
    # Mock DOJO_ROOT to point to our temp structure
    monkeypatch.setattr('src.training_manager.DOJO_ROOT', mock_dojo_structure.parent)
    
    manager = TrainingManager()
    
    # First call - cache miss, should parse file
    result1 = manager.get_metadata("test_voice")
    assert len(result1) == 2
    assert result1[0]["id"] == "1"
    assert result1[1]["id"] == "2"
    
    # Second call - cache hit, should return cached data
    result2 = manager.get_metadata("test_voice")
    assert result2 == result1
    
    # Verify cache was populated
    assert "test_voice" in manager._metadata_cache


def test_get_metadata_cache_invalidation_on_modification(mock_dojo_structure, monkeypatch):
    """Test that cache is invalidated when file is modified"""
    from src.training_manager import TrainingManager
    
    monkeypatch.setattr('src.training_manager.DOJO_ROOT', mock_dojo_structure.parent)
    
    manager = TrainingManager()
    metadata_path = mock_dojo_structure / "dataset" / "metadata.csv"
    
    # First call
    result1 = manager.get_metadata("test_voice")
    assert len(result1) == 2
    
    # Modify file
    time.sleep(0.01)  # Ensure mtime changes
    metadata_path.write_text("1|updated\n2|also updated\n3|new entry\n", encoding="utf-8")
    
    # Second call should detect change and re-parse
    result2 = manager.get_metadata("test_voice")
    assert len(result2) == 3
    assert result2[0]["text"] == "updated"


def test_save_metadata_invalidates_cache(mock_dojo_structure, monkeypatch):
    """Test that save_metadata clears related caches"""
    from src.training_manager import TrainingManager
    
    monkeypatch.setattr('src.training_manager.DOJO_ROOT', mock_dojo_structure.parent)
    
    manager = TrainingManager()
    
    # Populate caches
    manager.get_metadata("test_voice")
    manager._wav_stats_cache["test_voice"] = {"count": 10, "total_ms": 5000, "mtime": 123}
    
    assert "test_voice" in manager._metadata_cache
    assert "test_voice" in manager._wav_stats_cache
    
    # Save metadata should clear caches
    new_entries = [{"id": "1", "text": "new text"}]
    manager.save_metadata("test_voice", new_entries)
    
    assert "test_voice" not in manager._metadata_cache
    assert "test_voice" not in manager._wav_stats_cache


def test_get_dataset_stats_uses_wav_cache(mock_dojo_structure, monkeypatch):
    """Test that get_dataset_stats caches wav file scan results"""
    from src.training_manager import TrainingManager
    
    monkeypatch.setattr('src.training_manager.DOJO_ROOT', mock_dojo_structure.parent)
    
    manager = TrainingManager()
    
    # First call - cache miss
    with patch('wave.open') as mock_wave:
        mock_wav = Mock()
        mock_wav.getnframes.return_value = 22050
        mock_wav.getframerate.return_value = 22050
        mock_wave.return_value.__enter__.return_value = mock_wav
        
        # Create a dummy wav file
        wav_path = mock_dojo_structure / "dataset" / "wav"
        wav_path.mkdir(parents=True)
        (wav_path / "test.wav").touch()
        
        result1 = manager.get_dataset_stats("test_voice")
        assert mock_wave.call_count == 1  # File was scanned
    
    # Second call - cache hit
    with patch('wave.open') as mock_wave:
        result2 = manager.get_dataset_stats("test_voice")
        assert mock_wave.call_count == 0  # File was NOT scanned
        assert result1["count"] == result2["count"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
