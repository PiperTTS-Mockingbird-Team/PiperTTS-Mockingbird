"""
Potato-Local-AI Resource Usage Tracker
Tests RAM/CPU usage across four phases:
  1. Idle       - Ollama loaded, nothing happening
  2. Search     - Web search pipeline only (no AI gen)
  3. Generation - AI generating a response (no search)
  4. Full       - Complete pipeline: search + AI + markdown render

Requires: psutil  (pip install psutil)
Ollama must be running with qwen3:1.7b pulled.
"""

import sys
import time
import threading
import textwrap

try:
    import psutil
except ImportError:
    print("psutil not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

import requests
import ollama
from ddgsearch import get_combined_response_stream
from markdown_render import register_heading_hr_tags, apply_headings

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL         = "qwen3:1.7b"
OLLAMA_URL    = "http://localhost:11434"
SAMPLE_HZ     = 4          # samples per second during monitoring
IDLE_DURATION = 5          # seconds to observe idle state
SEPARATOR     = "─" * 68

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_ollama_pid():
    """Return the PID of the running ollama process, or None."""
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if "ollama" in proc.info["name"].lower():
                return proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def sample_resources(stop_event, samples: list):
    """
    Background thread: every 1/SAMPLE_HZ seconds record
    (python_ram_mb, ollama_ram_mb, system_ram_pct, python_cpu, ollama_cpu).
    """
    py_proc = psutil.Process()
    # prime CPU counters
    py_proc.cpu_percent(interval=None)

    ollama_pid = get_ollama_pid()
    ol_proc = None
    if ollama_pid:
        try:
            ol_proc = psutil.Process(ollama_pid)
            ol_proc.cpu_percent(interval=None)
        except psutil.NoSuchProcess:
            ol_proc = None

    interval = 1.0 / SAMPLE_HZ

    while not stop_event.is_set():
        try:
            py_ram  = py_proc.memory_info().rss / 1_048_576
            py_cpu  = py_proc.cpu_percent(interval=None)
            sys_ram = psutil.virtual_memory().percent

            ol_ram, ol_cpu = 0.0, 0.0
            if ol_proc:
                try:
                    ol_ram = ol_proc.memory_info().rss / 1_048_576
                    ol_cpu = ol_proc.cpu_percent(interval=None)
                except psutil.NoSuchProcess:
                    ol_proc = None

            samples.append((py_ram, ol_ram, sys_ram, py_cpu, ol_cpu))
        except Exception:
            pass
        time.sleep(interval)


def measure(label: str, fn):
    """
    Run fn() while sampling resources.
    Returns (result, stats_dict).
    """
    samples = []
    stop   = threading.Event()
    t      = threading.Thread(target=sample_resources, args=(stop, samples), daemon=True)
    t.start()

    start = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - start

    stop.set()
    t.join(timeout=2)

    if not samples:
        stats = {"duration": elapsed}
    else:
        py_rams  = [s[0] for s in samples]
        ol_rams  = [s[1] for s in samples]
        sys_pcts = [s[2] for s in samples]
        py_cpus  = [s[3] for s in samples]
        ol_cpus  = [s[4] for s in samples]

        stats = {
            "duration":       elapsed,
            "py_ram_avg":     sum(py_rams)  / len(py_rams),
            "py_ram_peak":    max(py_rams),
            "ol_ram_avg":     sum(ol_rams)  / len(ol_rams),
            "ol_ram_peak":    max(ol_rams),
            "sys_ram_peak":   max(sys_pcts),
            "py_cpu_peak":    max(py_cpus),
            "ol_cpu_peak":    max(ol_cpus),
        }

    return result, stats


def print_stats(stats: dict, extra: str = ""):
    dur = stats["duration"]
    print(f"  Duration        : {dur:.2f}s")
    if "py_ram_peak" in stats:
        print(f"  Python  RAM     : avg {stats['py_ram_avg']:.1f} MB  |  peak {stats['py_ram_peak']:.1f} MB")
        print(f"  Ollama  RAM     : avg {stats['ol_ram_avg']:.1f} MB  |  peak {stats['ol_ram_peak']:.1f} MB")
        print(f"  System  RAM     : peak {stats['sys_ram_peak']:.1f}%")
        print(f"  Python  CPU     : peak {stats['py_cpu_peak']:.1f}%")
        print(f"  Ollama  CPU     : peak {stats['ol_cpu_peak']:.1f}%")
    if extra:
        print(f"  {extra}")


def print_header(label: str):
    print(f"\n{SEPARATOR}")
    print(f"  PHASE: {label}")
    print(SEPARATOR)


# ---------------------------------------------------------------------------
# Phase functions
# ---------------------------------------------------------------------------

def phase_idle():
    """Just wait — shows baseline with Ollama loaded."""
    # Warm Ollama by sending a tiny ping so the model is resident
    try:
        ollama.chat(model=MODEL, messages=[{"role": "user", "content": "hi"}],
                    options={"num_predict": 1})
    except Exception:
        pass
    time.sleep(IDLE_DURATION)


def phase_search():
    """Web search pipeline only — no AI generation."""
    from multi_search import search_internet
    query = "how to improve Python performance tips"
    results = search_internet(query, max_results=6)
    return results


def phase_generation():
    """AI generation with a medium-length answer — no web search."""
    prompt = (
        "Explain in detail how Python's garbage collector works, "
        "including reference counting and the cyclic GC. "
        "Give a practical example of a reference cycle."
    )
    full_response = ""
    token_count   = 0
    stream = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        options={"num_predict": 300}
    )
    for chunk in stream:
        content = chunk.get("message", {}).get("content", "")
        full_response += content
        token_count   += 1
    return full_response, token_count


def phase_full_pipeline():
    """Full pipeline: query optimisation → search → AI answer → markdown."""
    query = "best practices for securing a home WiFi network"
    collected = []

    def _stream_cb(chunk):
        collected.append(chunk)

    # get_combined_response_stream handles: query split → search → AI → citations
    for chunk in get_combined_response_stream(query):
        if isinstance(chunk, str):
            collected.append(chunk)
        elif isinstance(chunk, dict):
            collected.append(str(chunk))

    raw_md = "".join(collected)

    # Simulate markdown rendering (tag registration + heading pass)
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        text_widget = tk.Text(root)
        register_heading_hr_tags(text_widget)
        apply_headings(text_widget, raw_md)
        root.destroy()
    except Exception:
        pass  # headless / no display — skip render step, still measured search+gen

    return raw_md


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

def check_ollama():
    print("Checking Ollama...")
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        matches = [m for m in models if MODEL.split(":")[0] in m]
        if not matches:
            print(f"  WARNING: {MODEL} not found in pulled models: {models}")
            print("  Run: ollama pull qwen3:1.7b")
            return False
        print(f"  Ollama OK — model found: {matches[0]}")
        return True
    except Exception as e:
        print(f"  ERROR: Cannot reach Ollama at {OLLAMA_URL}  ({e})")
        print("  Make sure Ollama is running first.")
        return False


def system_snapshot():
    vm  = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=1)
    print(f"\nSystem Baseline")
    print(f"  Total RAM       : {vm.total / 1_073_741_824:.1f} GB")
    print(f"  Available RAM   : {vm.available / 1_073_741_824:.1f} GB")
    print(f"  RAM used        : {vm.percent:.1f}%")
    print(f"  CPU (1s avg)    : {cpu:.1f}%")
    ollama_pid = get_ollama_pid()
    if ollama_pid:
        try:
            ol = psutil.Process(ollama_pid)
            print(f"  Ollama PID      : {ollama_pid}  ({ol.memory_info().rss / 1_048_576:.0f} MB resident)")
        except psutil.NoSuchProcess:
            pass
    else:
        print("  Ollama process  : NOT FOUND (Ollama may not be running)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 68)
    print("  POTATO-LOCAL-AI  —  Resource Usage Test")
    print("=" * 68)

    if not check_ollama():
        sys.exit(1)

    system_snapshot()

    results_summary = []

    # ── Phase 1: Idle ──────────────────────────────────────────────────────
    print_header(f"1 / 4  IDLE  ({IDLE_DURATION}s observation, model warm)")
    _, stats = measure("Idle", phase_idle)
    print_stats(stats)
    results_summary.append(("Idle", stats))

    # ── Phase 2: Search only ───────────────────────────────────────────────
    print_header("2 / 4  WEB SEARCH  (no AI generation)")
    search_results, stats = measure("Search", phase_search)
    n_results = len(search_results) if search_results else 0
    print_stats(stats, extra=f"Results returned  : {n_results}")
    results_summary.append(("Search only", stats))

    # ── Phase 3: AI generation only ────────────────────────────────────────
    print_header("3 / 4  AI GENERATION  (no search, ~300 tokens)")
    (response, tok_count), stats = measure("Generation", phase_generation)
    tok_per_sec = tok_count / stats["duration"] if stats["duration"] > 0 else 0
    preview = textwrap.shorten(response.strip(), width=120, placeholder="…")
    print_stats(stats, extra=f"Tokens streamed   : {tok_count}  ({tok_per_sec:.1f} tok/s)")
    print(f"\n  Response preview:\n  {preview}")
    results_summary.append(("AI generation", stats))

    # ── Phase 4: Full pipeline ─────────────────────────────────────────────
    print_header("4 / 4  FULL PIPELINE  (search + AI + markdown)")
    full_output, stats = measure("Full pipeline", phase_full_pipeline)
    preview_full = textwrap.shorten("".join(str(full_output)).strip(), width=120, placeholder="…")
    print_stats(stats)
    print(f"\n  Output preview:\n  {preview_full}")
    results_summary.append(("Full pipeline", stats))

    # ── Summary table ──────────────────────────────────────────────────────
    print(f"\n{'=' * 68}")
    print("  SUMMARY")
    print(f"{'=' * 68}")
    col = 18
    print(f"  {'Phase':<{col}} {'Duration':>9}  {'PyRAM pk':>9}  {'OlRAM pk':>9}  {'SysRAM pk':>10}  {'OlCPU pk':>9}")
    print(f"  {'-' * (col + 52)}")
    for label, s in results_summary:
        dur      = f"{s['duration']:.1f}s"
        py_pk    = f"{s.get('py_ram_peak', 0):.0f} MB"
        ol_pk    = f"{s.get('ol_ram_peak', 0):.0f} MB"
        sys_pk   = f"{s.get('sys_ram_peak', 0):.1f}%"
        ol_cpu   = f"{s.get('ol_cpu_peak', 0):.0f}%"
        print(f"  {label:<{col}} {dur:>9}  {py_pk:>9}  {ol_pk:>9}  {sys_pk:>10}  {ol_cpu:>9}")

    print(f"\n  Done. All phases complete.\n")


if __name__ == "__main__":
    main()
