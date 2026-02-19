"""
Citation prompt benchmark — tests multiple second-pass strategies against
qwen2.5:1.5b and scores each one for:
  - citation_rate   : fraction of [?] placeholders replaced with [N]
  - no_literal_N    : [N] was not left as literal "[N]"
  - prose_preserved : key words from original answer still present (rough drift check)
  - no_junk         : no trailing Sources / URL block appended
Runs each variant REPS times and reports averages.
"""
import re
import ollama

MODEL = "qwen2.5:1.5b"
REPS  = 10  # runs per variant

# ---------------------------------------------------------------------------
# Realistic inputs — a first-pass answer + tagged sources like the app produces
# ---------------------------------------------------------------------------
FIRST_PASS = (
    "Donald Trump was born on June 14, 1946, at Jamaica Hospital in Queens, New York. "
    "He served as the 45th President of the United States and is a member of the Republican Party. "
    "His family originally emigrated from Scotland, and he attended the Wharton School of Finance."
)

RAW_SOURCES = [
    {
        "title": "Where was Donald Trump born – Britannica",
        "href":  "https://www.britannica.com/biography/Donald-Trump",
        "body":  "Donald Trump was born on June 14, 1946, in Queens, New York City.",
    },
    {
        "title": "President Donald J. Trump – White House",
        "href":  "https://www.whitehouse.gov/administration/donald-j-trump/",
        "body":  "Donald Trump served as the 45th President of the United States. He is a Republican.",
    },
    {
        "title": "Donald Trump – Wikipedia",
        "href":  "https://en.wikipedia.org/wiki/Donald_Trump",
        "body":  "Trump's paternal grandparents emigrated from Kallstadt, Germany, while his mother was born in Scotland. He attended the Wharton School.",
    },
]

# ---------------------------------------------------------------------------
# Source formatters (mirror ddgsearch.py helpers)
# ---------------------------------------------------------------------------
_MAX_CHARS = 1200

def _format_sources_plain(results):
    """Plain numbered block, no sentence tags — for single-pass prompts."""
    parts = []
    for i, r in enumerate(results):
        n = i + 1
        title = (r.get("title") or "Source").strip()
        body  = (r.get("body")  or "").strip()[:_MAX_CHARS]
        parts.append(f"[{n}] {title}\n{body}")
    return "\n\n".join(parts)

def _format_sources_tagged(results):
    """Each sentence ends with [N] — used for the fill-in-blanks pass."""
    parts = []
    for i, r in enumerate(results):
        n   = i + 1
        tag = f"[{n}]"
        title   = (r.get("title") or "Source").strip()
        body    = (r.get("body")  or "").strip()[:_MAX_CHARS]
        sents   = re.split(r"(?<=[.!?])\s+", body)
        tagged  = []
        for s in sents:
            s = s.strip()
            if not s: continue
            if s[-1] in ".!?":
                tagged.append(s[:-1] + f" {tag}" + s[-1])
            else:
                tagged.append(s + f" {tag}")
        parts.append(f"{tag} {title}\n{' '.join(tagged)}")
    return "\n\n".join(parts)

def _add_placeholders(answer):
    """Insert [?] at end of every sentence."""
    paragraphs = re.split(r"\n\n+", answer.strip())
    out = []
    for para in paragraphs:
        sents = re.split(r"(?<=[.!?])\s+", para.strip())
        tagged = []
        for s in sents:
            s = s.strip()
            if not s: continue
            tagged.append((s[:-1] + " [?]" + s[-1]) if s[-1] in ".!?" else s + " [?]")
        out.append(" ".join(tagged))
    return "\n\n".join(out)

# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------
def score(original, rewritten):
    """Return a dict of pass/fail metrics."""
    # 1. Were all [?] replaced?  Count [?] still remaining
    placeholder_remain = rewritten.count("[?]")
    placeholder_total  = _add_placeholders(original).count("[?]")
    citation_rate = 1.0 if placeholder_total == 0 else \
                    (placeholder_total - placeholder_remain) / placeholder_total

    # 2. Does it have at least one real [1]/[2]/[3] marker?
    has_real_cite = bool(re.search(r'\[\d+\]', rewritten))

    # 3. Literal "[N]" not resolved?
    has_literal_N = "[N]" in rewritten

    # 4. Prose drift — check that ≥70% of significant words from original are present
    orig_words = set(w.lower() for w in re.findall(r"[a-z']+", original) if len(w) > 3)
    rew_words  = set(w.lower() for w in re.findall(r"[a-z']+", rewritten))
    overlap    = len(orig_words & rew_words) / max(len(orig_words), 1)
    prose_ok   = overlap >= 0.70

    # 5. No junk appended (Sources: / URL block)
    no_junk = not bool(re.search(r"(Sources:|https?://|\[\d\]\s+http)", rewritten))

    return {
        "citation_rate": round(citation_rate, 2),
        "has_real_cite": has_real_cite,
        "no_literal_N":  not has_literal_N,
        "prose_ok":      prose_ok,
        "no_junk":       no_junk,
        "pass": (citation_rate == 1.0 and has_real_cite
                 and not has_literal_N and prose_ok and no_junk),
    }

# ---------------------------------------------------------------------------
# Build the variants we want to test
# ---------------------------------------------------------------------------
PLAIN_SOURCES  = _format_sources_plain(RAW_SOURCES)
TAGGED_SOURCES = _format_sources_tagged(RAW_SOURCES)
ANSWER_WITH_Q  = _add_placeholders(FIRST_PASS)

def make_variants():
    variants = {}

    # ── Current production approach (fill-in-blanks, system+user, tagged sources) ──
    variants["PROD (fill-blanks sys+user)"] = [
        {"role": "system", "content": (
            "You insert citation numbers into an answer. "
            "Your ONLY job is to swap each [?] for the correct [N]. "
            "Do NOT change, rephrase, add, or remove any other words. "
            "Output ONLY the completed answer — no lists, no explanations, no URLs."
        )},
        {"role": "user", "content": (
            "Each source sentence below ends with its number in brackets.\n"
            "Replace every [?] with the [N] of the source that supports that fact.\n"
            "Keep every other word EXACTLY as written — do not rephrase anything.\n\n"
            "--- EXAMPLE ---\n"
            "Sources:\n"
            "[1] Bananas are yellow [1]. They grow in tropical climates [1].\n"
            "[2] Apples prefer cooler weather [2]. They can be red or green [2].\n\n"
            f"Answer with [?]: Bananas are tropical fruits [?]. Apples like cool weather [?].\n"
            "Completed answer: Bananas are tropical fruits [1]. Apples like cool weather [2].\n"
            "--- END EXAMPLE ---\n\n"
            f"Sources:\n{TAGGED_SOURCES}\n\n"
            f"Answer with [?]: {ANSWER_WITH_Q}\n"
            "Completed answer:"
        )},
    ]

    # ── V2: same but two-shot example (more pattern drilling) ──
    variants["V2 (two-shot fill-blanks)"] = [
        {"role": "system", "content": (
            "You insert citation numbers into an answer. "
            "Your ONLY job is to swap each [?] for the correct [N]. "
            "Do NOT change, rephrase, add, or remove any other words. "
            "Output ONLY the completed answer — no lists, no explanations, no URLs."
        )},
        {"role": "user", "content": (
            "Each source sentence ends with its number. Replace every [?] with the matching [N].\n"
            "Keep every word EXACTLY as written. Output only the final answer.\n\n"
            "=== EXAMPLE 1 ===\n"
            "Sources:\n"
            "[1] Bananas are yellow [1].\n"
            "[2] Apples grow in cool climates [2].\n"
            "Answer with [?]: Bananas are yellow [?]. Apples grow in cool climates [?].\n"
            "Completed answer: Bananas are yellow [1]. Apples grow in cool climates [2].\n\n"
            "=== EXAMPLE 2 ===\n"
            "Sources:\n"
            "[1] Paris is the capital of France [1].\n"
            "[2] The Eiffel Tower was built in 1889 [2].\n"
            "Answer with [?]: Paris is France's capital [?]. The Eiffel Tower dates to 1889 [?].\n"
            "Completed answer: Paris is France's capital [1]. The Eiffel Tower dates to 1889 [2].\n\n"
            "=== NOW DO THIS ===\n"
            f"Sources:\n{TAGGED_SOURCES}\n\n"
            f"Answer with [?]: {ANSWER_WITH_Q}\n"
            "Completed answer:"
        )},
    ]

    # ── V3: direct single-pass rewrite (no placeholders) — ask model to add cites itself ──
    variants["V3 (single-pass, cite inline)"] = [
        {"role": "system", "content": (
            "You add inline citations to answers from numbered search results. "
            "After each fact add its source number like [1]. "
            "Keep the answer text IDENTICAL otherwise. No URLs, no References section."
        )},
        {"role": "user", "content": (
            f"Sources:\n{PLAIN_SOURCES}\n\n"
            f"Answer (add [N] citations inline, change nothing else):\n{FIRST_PASS}\n\n"
            "Cited answer:"
        )},
    ]

    # ── V4: ultra-minimal fill-blanks, no example, just raw instruction ──
    variants["V4 (minimal, no example)"] = [
        {"role": "system", "content": (
            "Replace each [?] with the matching source number [N]. "
            "Output ONLY the answer text. Change nothing else."
        )},
        {"role": "user", "content": (
            f"Sources:\n{TAGGED_SOURCES}\n\n"
            f"Answer: {ANSWER_WITH_Q}\n"
            "Completed:"
        )},
    ]

    # ── V5: use the assistant role to prime the output token ──
    variants["V5 (assistant-primed)"] = [
        {"role": "system", "content": (
            "You insert citation numbers into an answer. "
            "Your ONLY job is to swap each [?] for the correct [N]. "
            "Do NOT change, rephrase, add, or remove any other words."
        )},
        {"role": "user", "content": (
            "Each source sentence ends with [N]. Replace every [?] with the matching [N].\n"
            "Keep every word EXACTLY as written.\n\n"
            "--- EXAMPLE ---\n"
            "Sources:\n"
            "[1] Sky is blue [1]. It reflects light [1].\n"
            "[2] Grass is green [2]. It photosynthesises [2].\n"
            "Answer with [?]: The sky appears blue [?]. Grass stays green [?].\n"
            "Completed answer: The sky appears blue [1]. Grass stays green [2].\n"
            "--- END EXAMPLE ---\n\n"
            f"Sources:\n{TAGGED_SOURCES}\n\n"
            f"Answer with [?]: {ANSWER_WITH_Q}"
        )},
        {"role": "assistant", "content": "Completed answer:"},
    ]

    return variants

# ---------------------------------------------------------------------------
# Run benchmark
# ---------------------------------------------------------------------------
def run():
    all_variants = make_variants()
    # Only benchmark the top two candidates
    variants = {k: v for k, v in all_variants.items() if k.startswith("V2") or k.startswith("V5")}
    print(f"\nMODEL: {MODEL}   REPS: {REPS}\n")
    print("FIRST-PASS ANSWER:")
    print(FIRST_PASS)
    print()
    print("ANSWER WITH PLACEHOLDERS:")
    print(ANSWER_WITH_Q)
    print()

    summary = {}

    for name, messages in variants.items():
        print("=" * 70)
        print(f"VARIANT: {name}")
        print("=" * 70)
        passes = 0
        totals = {"citation_rate": 0, "has_real_cite": 0,
                  "no_literal_N": 0, "prose_ok": 0, "no_junk": 0}
        for run_i in range(REPS):
            try:
                r = ollama.chat(model=MODEL, messages=messages)
                out = r["message"]["content"].strip()
                # Strip "Completed answer:" prefix if model echoes it
                for prefix in ("Completed answer:", "Completed:"):
                    if out.lower().startswith(prefix.lower()):
                        out = out[len(prefix):].strip()
                        break
                s = score(FIRST_PASS, out)
                status = "✓ PASS" if s["pass"] else "✗ FAIL"
                print(f"  Run {run_i+1}: {status}  cite={s['citation_rate']}  "
                      f"real={s['has_real_cite']}  noN={s['no_literal_N']}  "
                      f"prose={s['prose_ok']}  clean={s['no_junk']}")
                print(f"    OUTPUT: {out[:200]}")
                if s["pass"]: passes += 1
                for k in totals: totals[k] += int(s[k]) if isinstance(s[k], bool) else s[k]
            except Exception as e:
                print(f"  Run {run_i+1}: ERROR — {e}")
        avg = {k: round(v / REPS, 2) for k, v in totals.items()}
        avg["pass_rate"] = f"{passes}/{REPS}"
        summary[name] = avg
        print(f"  AVERAGE: {avg}\n")

    print("\n" + "=" * 70)
    print("SUMMARY TABLE")
    print("=" * 70)
    print(f"  {'Variant':<35} {'Pass':>6} {'Cite':>6} {'Real':>6} {'noN':>6} {'Prose':>6} {'Clean':>6}")
    print(f"  {'-'*70}")
    for name, avg in summary.items():
        print(f"  {name:<35} {avg['pass_rate']:>6} {avg['citation_rate']:>6} "
              f"{avg['has_real_cite']:>6} {avg['no_literal_N']:>6} "
              f"{avg['prose_ok']:>6} {avg['no_junk']:>6}")
    print()

if __name__ == "__main__":
    run()
