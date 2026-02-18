import os
import sys
import time
import subprocess
import requests
import psutil
from pathlib import Path

# Configuration
SERVER_PORT = 5002
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"
SCRIPT_DIR = Path(__file__).resolve().parent
SERVER_SCRIPT = SCRIPT_DIR / "src" / "piper_server.py"
# Use a more explicit name that the server can find
MODEL_NAME = "Cori" 

def find_existing_server_pid():
    """Look for a process listening on port 5002."""
    for conn in psutil.net_connections():
        if conn.laddr.port == SERVER_PORT and conn.status == "LISTEN":
            return conn.pid
    return None

def get_process_stats(pid):
    """Get memory and CPU usage for a specific PID and all its children."""
    try:
        main_proc = psutil.Process(pid)
        pids = [pid] + [p.pid for p in main_proc.children(recursive=True)]
        
        total_mem = 0
        total_cpu = 0
        
        for p in pids:
            try:
                proc = psutil.Process(p)
                total_mem += proc.memory_info().rss / (1024 * 1024)
                total_cpu += proc.cpu_percent(interval=0.1)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return total_mem, total_cpu
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0, 0

def run_tests():
    print("--- Piper TTS Resource Usage Tracker ---")
    
    # Check if a server is already running
    existing_pid = find_existing_server_pid()
    server_proc = None
    
    if existing_pid:
        print(f"Found existing server running (PID: {existing_pid}). Monitoring that.")
        target_pid = existing_pid
    else:
        # Start the server if not running
        print(f"\n[1/4] Starting server: {SERVER_SCRIPT}...")
        python_exe = sys.executable
        server_proc = subprocess.Popen(
            [python_exe, str(SERVER_SCRIPT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(SCRIPT_DIR / "src")
        )
        target_pid = server_proc.pid
        
        # Wait for server to be ready
        print("Waiting for server to start...")
        ready = False
        for _ in range(30):
            try:
                if requests.get(f"{SERVER_URL}/health", timeout=1).status_code == 200:
                    ready = True
                    break
            except:
                time.sleep(1)
        if not ready:
            print("Error: Server failed to start.")
            server_proc.terminate()
            return

    print("Server is UP and READY.")
    
    # 1. Idle (Waiting)
    time.sleep(2)
    mem_idle, cpu_idle = get_process_stats(target_pid)
    print(f"\nSTATE: IDLE (Server running, no model loaded)")
    print(f"  RAM Usage: {mem_idle:.2f} MB")
    print(f"  CPU Usage: {cpu_idle:.1f}%")

    # 2. Idle (Loaded)
    print(f"\n[2/4] Loading model '{MODEL_NAME}'...")
    payload = {"text": "Load model.", "voice_model": MODEL_NAME}
    requests.post(f"{SERVER_URL}/api/tts", json=payload, timeout=20)
    
    time.sleep(2)
    mem_loaded, cpu_loaded = get_process_stats(target_pid)
    print(f"STATE: IDLE & LOADED (Piper process waiting in RAM)")
    print(f"  RAM Usage: {mem_loaded:.2f} MB")
    print(f"  CPU Usage: {cpu_loaded:.1f}%")
    print(f"  Model RAM Impact: ~{mem_loaded - mem_idle:.2f} MB")

    # 3. Active Synthesis
    print(f"\n[3/4] Actively synthesizing (Long text)...")
    long_text = "The quick brown fox jumps over the lazy dog. Local AI running on potatoes is a noble goal. " * 3
    payload["text"] = long_text
    
    import threading
    req_done = threading.Event()
    def run_req():
        try:
            requests.post(f"{SERVER_URL}/api/tts", json=payload, timeout=30)
        except:
            pass
        finally:
            req_done.set()
    
    t = threading.Thread(target=run_req)
    t.start()
    
    peak_mem = mem_loaded
    peak_cpu = 0
    # Monitor for up to 10 seconds or until request finishes
    start_time = time.time()
    while not req_done.is_set() and time.time() - start_time < 10:
        m, c = get_process_stats(target_pid)
        peak_mem = max(peak_mem, m)
        peak_cpu = max(peak_cpu, c)
        time.sleep(0.1)
    t.join(timeout=1)

    print(f"STATE: ACTIVELY SAYING SOMETHING")
    print(f"  Peak RAM: {peak_mem:.2f} MB")
    print(f"  Peak CPU: {peak_cpu:.1f}%")

    if server_proc:
        print("\n[4/4] Cleaning up started server...")
        server_proc.terminate()
    else:
        print("\n[4/4] Finished monitoring existing server.")

    print("\n--- Final Results for Potato Planning ---")
    print(f"RAM BASELINE:  {mem_idle:.2f} MB")
    print(f"RAM LOADED:    {mem_loaded:.2f} MB")
    print(f"RAM PEAK:      {peak_mem:.2f} MB")
    print(f"CPU MAX SPIKE: {peak_cpu:.1f}%")

if __name__ == "__main__":
    try:
        run_tests()
    except KeyboardInterrupt:
        print("\nTest cancelled.")
    except Exception as e:
        print(f"An error occurred: {e}")
