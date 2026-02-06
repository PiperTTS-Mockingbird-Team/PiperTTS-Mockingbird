import sys
from pathlib import Path
import os
import json

# Add src to path
sys.path.append(str(Path("src").resolve()))

from piper_server import resolve_model_path, manager, resolve_piper_exe

def test_tts():
    # Try to find a model inbilly_dojo
    dojo_onnx_dir = Path("make piper voice models/tts_dojo/billy_dojo/tts_voices")
    onnx_files = list(dojo_onnx_dir.glob("*.onnx"))
    if not onnx_files:
        print("No ONNX files found in billy_dojo/tts_voices")
        return

    model_path = str(onnx_files[0].resolve())
    print(f"Testing with model: {model_path}")
    
    try:
        resolved = resolve_model_path(model_path)
        print(f"Resolved path: {resolved}")
        
        piper_exe = resolve_piper_exe()
        print(f"Piper exe: {piper_exe}")
        
        # Determine config path
        config_path = resolved.with_suffix(resolved.suffix + ".json")
        if not config_path.exists():
            config_path = resolved.with_suffix(".json")
            
        print(f"Config path exists: {config_path.exists()} ({config_path})")

        # Try to start process
        process = manager.get_process(resolved, config_path, "", piper_exe, str(Path(piper_exe).parent))
        process.ensure_started()
        print("Process started successfully.")
        
        audio = process.synthesize("Hello test.")
        print(f"Synthesis successful, audio length: {len(audio)}")
        
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_tts()
