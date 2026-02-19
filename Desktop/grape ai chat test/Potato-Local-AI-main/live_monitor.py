"""
Potato-Local-AI  —  Live Resource Monitor
==========================================
Launches gui_app.py in a subprocess, then continuously prints a live
dashboard showing CPU% and RAM for:
  • gui_app.py  (our process + children)
  • ollama.exe  (the model inference process)
  • TOTAL       (both combined)

Use Ctrl+C to stop. A summary is printed and saved to resource_report_live.txt.
"""
import os, sys, time, subprocess, signal, atexit
import psutil

# ── Config ────────────────────────────────────────────────────────────────────
PYTHON_EXE   = sys.executable
APP_SCRIPT   = os.path.join(os.path.dirname(__file__), "gui_app.py")
SAMPLE_HZ    = 2          # samples per second
HISTORY_SECS = 3600       # keep up to 1 hour of samples

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_tree_stats(root_pid):
    """Return (cpu%, ram_MB) summed across a process tree."""
    try:
        root = psutil.Process(root_pid)
        procs = [root] + root.children(recursive=True)
    except psutil.NoSuchProcess:
        return 0.0, 0.0
    cpu, ram = 0.0, 0.0
    for p in procs:
        try:
            cpu += p.cpu_percent(interval=None)
            ram += p.memory_info().rss / (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return cpu, ram

def find_ollama_pids():
    """Find all ollama.exe processes."""
    pids = []
    for p in psutil.process_iter(['pid', 'name']):
        try:
            if 'ollama' in p.info['name'].lower():
                pids.append(p.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return pids

def get_ollama_stats():
    """Return (cpu%, ram_MB) summed across all ollama processes."""
    cpu, ram = 0.0, 0.0
    for pid in find_ollama_pids():
        c, r = get_tree_stats(pid)
        cpu += c
        ram += r
    return cpu, ram

def bar(val, scale, width=20):
    filled = min(int(val / scale * width), width)
    return "█" * filled + "░" * (width - filled)

def clear_line():
    sys.stdout.write("\r\033[K")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("  Potato-Local-AI  —  Live Resource Monitor")
    print("=" * 65)
    print(f"  Launching: {APP_SCRIPT}")
    print("  Interact with the app, then press Ctrl+C here to get the report.\n")

    # Warm up cpu_percent baseline
    for p in psutil.process_iter():
        try: p.cpu_percent(interval=None)
        except: pass
    time.sleep(0.5)

    # Launch the GUI app
    app_proc = subprocess.Popen(
        [PYTHON_EXE, APP_SCRIPT],
        cwd=os.path.dirname(APP_SCRIPT)
    )
    app_pid = app_proc.pid
    print(f"  ✅  gui_app.py started  (PID {app_pid})\n")

    # Wait a moment for process to settle
    time.sleep(1.5)

    # Warm up cpu_percent for the new process tree
    get_tree_stats(app_pid)
    get_ollama_stats()
    time.sleep(0.5)

    history = []   # list of (app_cpu, app_ram, ollama_cpu, ollama_ram)
    interval = 1.0 / SAMPLE_HZ

    print(f"  {'Process':<14} {'CPU%':>6}  {'RAM (MB)':>10}   Chart (CPU / 100%)")
    print(f"  {'-'*14} {'-'*6}  {'-'*10}   {'-'*40}")

    def cleanup(signum=None, frame=None):
        """Kill the app and print summary."""
        print("\n\n  Stopping app...")
        try:
            app_proc.terminate()
            app_proc.wait(timeout=5)
        except Exception:
            pass

        if not history:
            print("  No samples collected.")
            sys.exit(0)

        app_cpus  = [h[0] for h in history]
        app_rams  = [h[1] for h in history]
        oll_cpus  = [h[2] for h in history]
        oll_rams  = [h[3] for h in history]
        tot_cpus  = [h[0]+h[2] for h in history]
        tot_rams  = [h[1]+h[3] for h in history]

        lines = []
        lines.append("\n" + "=" * 65)
        lines.append("  SUMMARY  ({} samples  ≈  {:.0f}s runtime)".format(
            len(history), len(history) / SAMPLE_HZ))
        lines.append("=" * 65)
        lines.append(f"  {'Process':<16} {'CPU avg':>8} {'CPU peak':>9} {'RAM avg':>9} {'RAM peak':>9}")
        lines.append(f"  {'-'*16} {'-'*8} {'-'*9} {'-'*9} {'-'*9}")

        def row(name, cpus, rams):
            return (f"  {name:<16} {sum(cpus)/len(cpus):>7.1f}% {max(cpus):>8.1f}% "
                    f"{sum(rams)/len(rams):>8.1f}MB {max(rams):>8.1f}MB")

        lines.append(row("gui_app.py",   app_cpus, app_rams))
        lines.append(row("ollama",       oll_cpus, oll_rams))
        lines.append(row("TOTAL",        tot_cpus, tot_rams))
        lines.append("=" * 65)

        report = "\n".join(lines)
        print(report)

        out = os.path.join(os.path.dirname(__file__), "resource_report_live.txt")
        with open(out, "w", encoding="utf-8") as f:
            f.write(report.strip() + "\n")
        print(f"\n  ✅  Saved to resource_report_live.txt\n")
        sys.exit(0)

    signal.signal(signal.SIGINT,  cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    atexit.register(cleanup)

    tick = 0
    while app_proc.poll() is None:          # run until app closes
        app_cpu,  app_ram  = get_tree_stats(app_pid)
        oll_cpu,  oll_ram  = get_ollama_stats()
        tot_cpu = app_cpu + oll_cpu
        tot_ram = app_ram + oll_ram

        history.append((app_cpu, app_ram, oll_cpu, oll_ram))
        if len(history) > HISTORY_SECS * SAMPLE_HZ:
            history.pop(0)

        # Overwrite 3 lines each tick
        if tick > 0:
            sys.stdout.write("\033[3A")   # move up 3 lines

        print(f"\r  {'gui_app.py':<14} {app_cpu:>5.1f}%  {app_ram:>8.1f} MB   {bar(app_cpu, 100)}")
        print(f"\r  {'ollama':<14} {oll_cpu:>5.1f}%  {oll_ram:>8.1f} MB   {bar(oll_cpu, 100)}")
        print(f"\r  {'TOTAL':<14} {tot_cpu:>5.1f}%  {tot_ram:>8.1f} MB   {bar(tot_cpu, 100)}")
        sys.stdout.flush()

        tick += 1
        time.sleep(interval)

    print("\n\n  App closed. Generating report...")
    cleanup()

if __name__ == "__main__":
    main()
