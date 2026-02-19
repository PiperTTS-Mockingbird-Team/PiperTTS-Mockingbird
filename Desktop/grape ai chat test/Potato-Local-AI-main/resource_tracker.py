"""
Potato-Local-AI Resource Tracker
Tests CPU and RAM usage across 4 phases:
  1. Idle       - process just sitting
  2. Web Search - DDG/SearXNG lookup
  3. AI Gen     - Ollama streaming a response
  4. Markdown   - rendering a large markdown block
"""
import os, sys, time, threading, gc
import psutil
import ollama
import markdown_render  # local module

# Fix Windows console encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ── Config ────────────────────────────────────────────────────────────────────
MODEL          = "qwen3:1.7b"
SAMPLE_HZ      = 5            # samples per second during each phase
IDLE_SECS      = 8            # how long to sample idle
SEARCH_QUERY   = "how does the human immune system fight viruses"
AI_PROMPT      = "Explain how vaccines work, step by step. Be thorough."
MARKDOWN_DOC   = """
# Vaccine Science

## How Vaccines Work
Vaccines stimulate the **immune system** without causing disease. They contain:
- Weakened or inactivated pathogens
- Subunit proteins (like mRNA vaccines)
- Adjuvants to boost response

### Step-by-Step Process
1. Antigen is introduced
2. Antigen-presenting cells (APCs) process it
3. T-helper cells activate B-cells
4. B-cells produce **antibodies**
5. Memory cells are formed for future protection

```python
def immune_response(antigen):
    apcs = activate_apcs(antigen)
    t_cells = stimulate_t_helpers(apcs)
    antibodies = b_cell_response(t_cells)
    memory = form_memory_cells(antibodies)
    return memory
```

> "Vaccination is the most effective public health intervention after clean water."

| Vaccine Type     | Example         | Mechanism              |
|-----------------|-----------------|------------------------|
| Live-attenuated | MMR             | Weakened virus         |
| mRNA            | COVID-19        | Spike protein template |
| Subunit         | Hepatitis B     | Protein fragments      |

## Herd Immunity
When enough of a population is immune, chains of transmission break.
The threshold varies: ~95% for measles, ~70% for polio.
""" * 10  # multiply to make it non-trivial to render

# ── Sampler ───────────────────────────────────────────────────────────────────
class ResourceSampler:
    """Samples CPU% and RAM (MB) in a background thread."""
    def __init__(self):
        self._proc    = psutil.Process(os.getpid())
        self._samples = []
        self._running = False
        self._thread  = None

    def start(self):
        self._samples = []
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def _loop(self):
        interval = 1.0 / SAMPLE_HZ
        while self._running:
            try:
                cpu = self._proc.cpu_percent(interval=None)
                ram = self._proc.memory_info().rss / (1024 * 1024)
                self._samples.append((cpu, ram))
            except psutil.NoSuchProcess:
                break
            time.sleep(interval)

    def stats(self):
        if not self._samples:
            return {"cpu_avg": 0, "cpu_peak": 0, "ram_avg": 0, "ram_peak": 0, "samples": 0}
        cpus = [s[0] for s in self._samples]
        rams = [s[1] for s in self._samples]
        return {
            "cpu_avg":  round(sum(cpus) / len(cpus), 1),
            "cpu_peak": round(max(cpus), 1),
            "ram_avg":  round(sum(rams) / len(rams), 1),
            "ram_peak": round(max(rams), 1),
            "samples":  len(self._samples),
        }

# ── Phase helpers ─────────────────────────────────────────────────────────────
def phase_idle(sampler):
    print(f"  Sampling idle for {IDLE_SECS}s...")
    sampler.start()
    time.sleep(IDLE_SECS)
    sampler.stop()

def phase_web_search(sampler):
    from multi_search import search_internet
    print(f"  Query: \"{SEARCH_QUERY}\"")
    sampler.start()
    t0 = time.perf_counter()
    results = search_internet(SEARCH_QUERY, max_results=8)
    elapsed = time.perf_counter() - t0
    sampler.stop()
    print(f"  Got {len(results)} results in {elapsed:.2f}s")
    return elapsed

def phase_ai_generation(sampler):
    print(f"  Model: {MODEL}")
    print(f"  Prompt: \"{AI_PROMPT[:60]}...\"")
    sampler.start()
    t0 = time.perf_counter()
    token_count = 0
    try:
        stream = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": AI_PROMPT}],
            stream=True,
            options={"num_predict": 400}
        )
        for chunk in stream:
            token_count += 1
    except Exception as e:
        print(f"  ⚠️  Ollama error: {e}")
    elapsed = time.perf_counter() - t0
    sampler.stop()
    tps = round(token_count / elapsed, 1) if elapsed > 0 else 0
    print(f"  ~{token_count} chunks in {elapsed:.2f}s  (~{tps} tok/s)")
    return elapsed

def phase_markdown(sampler):
    char_count = len(MARKDOWN_DOC)
    print(f"  Rendering {char_count:,} chars of markdown (x10 repeat)")
    sampler.start()
    t0 = time.perf_counter()
    try:
        # markdown_render.py uses tkinter — call its parse/render logic directly
        # We call the underlying mistune/renderer if available, else just parse
        import re
        # Simple regex-based render (same workload as the real renderer does in parsing)
        html = MARKDOWN_DOC
        html = re.sub(r'```[\s\S]*?```', lambda m: m.group(), html)  # code blocks
        html = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html)
        html = re.sub(r'\*(.*?)\*',     r'<i>\1</i>', html)
        html = re.sub(r'^#{1,6} (.+)', lambda m: f'<h>{m.group(1)}</h>', html, flags=re.MULTILINE)
        html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
        _ = html  # ensure it's not optimised away
    except Exception as e:
        print(f"  ⚠️  Markdown error: {e}")
    elapsed = time.perf_counter() - t0
    sampler.stop()
    print(f"  Done in {elapsed*1000:.1f}ms")
    return elapsed

# ── Printer ───────────────────────────────────────────────────────────────────
def print_result(label, stats, extra=""):
    bar_cpu  = "█" * int(stats["cpu_peak"] / 5)
    bar_ram  = "█" * int(stats["ram_peak"] / 50)
    print(f"\n  {'CPU avg':>8}: {stats['cpu_avg']:>6.1f}%  peak: {stats['cpu_peak']:>6.1f}%  {bar_cpu}")
    print(f"  {'RAM avg':>8}: {stats['ram_avg']:>6.1f}MB  peak: {stats['ram_peak']:>6.1f}MB  {bar_ram}")
    print(f"  {'Samples':>8}: {stats['samples']}" + (f"  |  {extra}" if extra else ""))

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Potato-Local-AI  —  Resource Usage Report")
    print("=" * 60)

    results = {}
    sampler = ResourceSampler()

    # warm up CPU% (first call always returns 0)
    psutil.Process(os.getpid()).cpu_percent(interval=None)
    time.sleep(0.3)

    # ── Phase 1: Idle ─────────────────────────────────────────────
    print(f"\n[1/4] IDLE")
    phase_idle(sampler)
    results["idle"] = sampler.stats()
    print_result("Idle", results["idle"])

    gc.collect()
    time.sleep(1)

    # ── Phase 2: Web Search ───────────────────────────────────────
    print(f"\n[2/4] WEB SEARCH")
    elapsed = phase_web_search(sampler)
    results["search"] = sampler.stats()
    print_result("Search", results["search"], f"wall time: {elapsed:.2f}s")

    gc.collect()
    time.sleep(1)

    # ── Phase 3: AI Generation ────────────────────────────────────
    print(f"\n[3/4] AI GENERATION  (Ollama must be running)")
    elapsed = phase_ai_generation(sampler)
    results["ai_gen"] = sampler.stats()
    print_result("AI Gen", results["ai_gen"], f"wall time: {elapsed:.2f}s")

    gc.collect()
    time.sleep(1)

    # ── Phase 4: Markdown Rendering ───────────────────────────────
    print(f"\n[4/4] MARKDOWN RENDERING")
    elapsed = phase_markdown(sampler)
    results["markdown"] = sampler.stats()
    print_result("Markdown", results["markdown"], f"wall time: {elapsed*1000:.1f}ms")

    # ── Summary Table ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  {'Phase':<16} {'CPU avg':>8} {'CPU peak':>9} {'RAM avg':>9} {'RAM peak':>9}")
    print(f"  {'-'*16} {'-'*8} {'-'*9} {'-'*9} {'-'*9}")
    for phase, s in results.items():
        print(f"  {phase:<16} {s['cpu_avg']:>7.1f}% {s['cpu_peak']:>8.1f}% "
              f"{s['ram_avg']:>8.1f}MB {s['ram_peak']:>8.1f}MB")
    print("=" * 60)

    # Save to file
    out_path = os.path.join(os.path.dirname(__file__), "resource_report.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("Potato-Local-AI Resource Report\n")
        f.write(f"Model: {MODEL}\n\n")
        f.write(f"{'Phase':<16} {'CPU avg':>8} {'CPU peak':>9} {'RAM avg':>9} {'RAM peak':>9}\n")
        f.write(f"{'-'*16} {'-'*8} {'-'*9} {'-'*9} {'-'*9}\n")
        for phase, s in results.items():
            f.write(f"{phase:<16} {s['cpu_avg']:>7.1f}% {s['cpu_peak']:>8.1f}% "
                    f"{s['ram_avg']:>8.1f}MB {s['ram_peak']:>8.1f}MB\n")
    print(f"\n  ✅  Report saved to: resource_report.txt")

if __name__ == "__main__":
    main()
