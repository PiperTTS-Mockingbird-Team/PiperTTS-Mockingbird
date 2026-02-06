from piper_server import get_storage_info, format_bytes, get_size_bytes
import os
from pathlib import Path

# Mock SCRIPT_DIR if needed, but it's already in piper_server
try:
    info = get_storage_info()
    print("Storage Info Success")
    print(info)
    from piper_server import get_logs
    logs = get_logs()
    print("Logs Success")
except Exception as e:
    import traceback
    traceback.print_exc()
