import sys
sys.path.insert(0, 'src')

try:
    from training_manager import training_manager
    result = training_manager.start_training("billy", start_mode="resume")
    print(f"Success: {result}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
