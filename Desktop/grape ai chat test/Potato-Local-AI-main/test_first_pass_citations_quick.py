"""
Quick test if Qwen3 1.7B can generate accurate in-text citations on the first pass.
Tests: Single-pass (ask for citations directly) vs Two-pass (current method)
Runs 5 times each for faster results.
"""
import re
import ollama
from datetime import datetime

MODEL = "qwen3:1.7b"
REPS = 5  # runs per test

# ---------------------------------------------------------------------------
# Test data: realistic search results
# ---------------------------------------------------------------------------
QUERY = "Where was Donald Trump born and what is his political affiliation?"

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
# Source formatters
# ---------------------------------------------------------------------------
def _format_sources_plain(results):
    """Plain numbered block without sentence tags."""
    parts = []
    for i, r in enumerate(results):
        n = i + 1
        title = (r.get("title") or "Source").strip()
        body  = (r.get("body")  or "").strip()[:1200]
        parts.append(f"[{n}] {title}\n{body}")
    return "\n\n".join(parts)

def _format_sources_tagged(results):
    """Each sentence ends with [N] — used for two-pass fill-in-blanks."""
    parts = []
    for i, r in enumerate(results):
        n   = i + 1
        tag = f"[{n}]"
        title   = (r.get("title") or "Source").strip()
        body    = (r.get("body")  or "").strip()[:1200]
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
    sents = re.split(r"(?<=[.!?])\s+", answer.strip())
    tagged = []
    for s in sents:
        s = s.strip()
        if not s: continue
        tagged.append((s[:-1] + " [?]" + s[-1]) if s[-1] in ".!?" else s + " [?]")
    return " ".join(tagged)

# ---------------------------------------------------------------------------
# Single-pass approach
# ---------------------------------------------------------------------------
def test_single_pass():
    """Ask for citations directly in one pass."""
    current_date = datetime.now().strftime("%A, %B %d, %Y")
    sources = _format_sources_plain(RAW_SOURCES)
    
    prompt = (
        f"Today's date: {current_date}\n\n"
        f"Answer the question below in 2-4 clear sentences using the search results.\n"
        f"After any fact from a source, add its citation number in square brackets [N].\n"
        f"For example: \"Paris is the capital of France [1].\" or \"The tower was built in 1889 [2].\"\n\n"
        f"Search results:\n{sources}\n\n"
        f"Question: {QUERY}\n"
        f"Answer:"
    )
    
    try:
        response = ollama.generate(model=MODEL, prompt=prompt)
        return response['response'].strip()
    except Exception as e:
        print(f"Error: {e}")
        return ""

# ---------------------------------------------------------------------------
# Two-pass approach
# ---------------------------------------------------------------------------
def test_two_pass():
    """Generate prose first, then add citations."""
    current_date = datetime.now().strftime("%A, %B %d, %Y")
    sources_plain = _format_sources_plain(RAW_SOURCES)
    
    # First pass: clean prose
    first_prompt = (
        f"Today's date: {current_date}\n\n"
        f"Answer the question below in 2-4 clear sentences using the search results.\n"
        f"Write flowing prose only — do not include any citation numbers or references.\n\n"
        f"Search results:\n{sources_plain}\n\n"
        f"Question: {QUERY}\n"
        f"Answer:"
    )
    
    try:
        first_response = ollama.generate(model=MODEL, prompt=first_prompt)
        first_pass = first_response['response'].strip()
        
        # Second pass: add citations
        sources_tagged = _format_sources_tagged(RAW_SOURCES)
        answer_with_q = _add_placeholders(first_pass)
        
        messages = [
            {'role': 'system', 'content': (
                "You insert citation numbers into an answer. "
                "Your ONLY job is to swap each [?] for the correct [N]. "
                "Do NOT change, rephrase, add, or remove any other words. "
                "Output ONLY the completed answer — no lists, no explanations, no URLs."
            )},
            {'role': 'user', 'content': (
                "Each source sentence ends with its number. Replace every [?] with the matching [N].\n"
                "Keep every word EXACTLY as written. Output only the final answer.\n\n"
                "=== EXAMPLE ===\n"
                "Sources:\n[1] Bananas are yellow [1].\n[2] Apples grow in cool climates [2].\n"
                "Answer with [?]: Bananas are yellow [?]. Apples grow in cool climates [?].\n"
                "Completed answer: Bananas are yellow [1]. Apples grow in cool climates [2].\n\n"
                "=== NOW DO THIS ===\n"
                f"Sources:\n{sources_tagged}\n\n"
                f"Answer with [?]: {answer_with_q}\n"
                "Completed answer:"
            )},
        ]
        
        result = ollama.chat(model=MODEL, messages=messages)
        rewritten = result['message']['content'].strip()
        
        # Clean up
        marker = 'completed answer:'
        if marker in rewritten.lower():
            idx = rewritten.lower().find(marker)
            rewritten = rewritten[idx + len(marker):].strip()
        
        for stop in ('Sources:', '\n\n[1] ', '\n\n[2] '):
            idx = rewritten.find(stop)
            if idx != -1:
                rewritten = rewritten[:idx].strip()
        
        if not rewritten or '[?]' in rewritten:
            return first_pass
        
        return rewritten
        
    except Exception as e:
        print(f"Error: {e}")
        return ""

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def score_answer(answer):
    """Score for citations presence and accuracy."""
    citations = re.findall(r'\[(\d+)\]', answer)
    has_citations = len(citations) > 0
    
    # Citation accuracy: check if citations match facts
    accuracy_score = 0
    accuracy_checks = 0
    
    # Birth info should cite [1]
    if re.search(r'\b(Queens|New York|1946|June)\b', answer, re.IGNORECASE):
        accuracy_checks += 1
        for match in re.finditer(r'(Queens|New York|1946|June)[^.!?]*\[(\d+)\]', answer, re.IGNORECASE):
            if int(match.group(2)) == 1:
                accuracy_score += 1
                break
    
    # Political info should cite [2]
    if re.search(r'\b(Republican|45th|President)\b', answer, re.IGNORECASE):
        accuracy_checks += 1
        for match in re.finditer(r'(Republican|45th|President)[^.!?]*\[(\d+)\]', answer, re.IGNORECASE):
            if int(match.group(2)) == 2:
                accuracy_score += 1
                break
    
    citation_accuracy = accuracy_score / accuracy_checks if accuracy_checks > 0 else 0.0
    
    # Prose quality
    expected_keywords = ['trump', 'born', 'president', 'republican']
    keywords_found = sum(1 for kw in expected_keywords if kw in answer.lower())
    prose_quality = keywords_found >= 3
    
    passed = (has_citations and citation_accuracy >= 0.5 and prose_quality)
    
    return {
        "has_citations": has_citations,
        "citation_accuracy": round(citation_accuracy, 2),
        "prose_quality": prose_quality,
        "pass": passed,
        "answer": answer,
    }

# ---------------------------------------------------------------------------
# Run benchmark
# ---------------------------------------------------------------------------
def run_benchmark():
    print(f"Testing {MODEL} with {REPS} runs per approach")
    print(f"Query: {QUERY}\n")
    print("=" * 80)
    
    # Test single-pass
    print("\n📝 SINGLE-PASS (ask for citations directly)")
    print("-" * 80)
    single_results = []
    for i in range(REPS):
        print(f"  Run {i+1}/{REPS}...", end=" ", flush=True)
        answer = test_single_pass()
        score = score_answer(answer)
        single_results.append(score)
        status = "✓ PASS" if score['pass'] else "✗ FAIL"
        print(f"{status}  cites={score['has_citations']}  acc={score['citation_accuracy']:.2f}  prose={score['prose_quality']}")
    
    # Test two-pass
    print("\n📝 TWO-PASS (current production method)")
    print("-" * 80)
    two_pass_results = []
    for i in range(REPS):
        print(f"  Run {i+1}/{REPS}...", end=" ", flush=True)
        answer = test_two_pass()
        score = score_answer(answer)
        two_pass_results.append(score)
        status = "✓ PASS" if score['pass'] else "✗ FAIL"
        print(f"{status}  cites={score['has_citations']}  acc={score['citation_accuracy']:.2f}  prose={score['prose_quality']}")
    
    # Calculate averages
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    
    def calc_avg(results):
        return {
            "pass_rate": sum(1 for r in results if r['pass']) / len(results),
            "citation_rate": sum(1 for r in results if r['has_citations']) / len(results),
            "avg_accuracy": sum(r['citation_accuracy'] for r in results) / len(results),
            "prose_rate": sum(1 for r in results if r['prose_quality']) / len(results),
        }
    
    single_avg = calc_avg(single_results)
    two_pass_avg = calc_avg(two_pass_results)
    
    print(f"\n{'Metric':<25} {'Single-Pass':<15} {'Two-Pass':<15}")
    print("-" * 55)
    print(f"{'Pass rate':<25} {single_avg['pass_rate']:>6.1%}         {two_pass_avg['pass_rate']:>6.1%}")
    print(f"{'Has citations':<25} {single_avg['citation_rate']:>6.1%}         {two_pass_avg['citation_rate']:>6.1%}")
    print(f"{'Avg accuracy':<25} {single_avg['avg_accuracy']:>6.2f}         {two_pass_avg['avg_accuracy']:>6.2f}")
    print(f"{'Prose quality':<25} {single_avg['prose_rate']:>6.1%}         {two_pass_avg['prose_rate']:>6.1%}")
    
    # Recommendation
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    
    if single_avg['pass_rate'] >= 0.8 and single_avg['avg_accuracy'] >= 0.7:
        print("✅ Single-pass citations work GREAT with Qwen3 1.7B!")
        print("   You can eliminate the second citation rewrite pass.")
        print(f"   Success: {single_avg['pass_rate']:.0%} | Accuracy: {single_avg['avg_accuracy']:.2f}")
    elif single_avg['pass_rate'] >= 0.6:
        print("⚠️  Single-pass citations work reasonably well.")
        print(f"   Success: {single_avg['pass_rate']:.0%} | Accuracy: {single_avg['avg_accuracy']:.2f}")
        if two_pass_avg['pass_rate'] > single_avg['pass_rate']:
            print("   Two-pass is still more reliable. Consider keeping it.")
        else:
            print("   Consider switching to single-pass for speed.")
    else:
        print("❌ Single-pass citations are unreliable.")
        print(f"   Success: {single_avg['pass_rate']:.0%} | Accuracy: {single_avg['avg_accuracy']:.2f}")
        print("   Keep the current two-pass approach.")
    
    # Show examples
    print("\n" + "=" * 80)
    print("EXAMPLE OUTPUTS")
    print("=" * 80)
    print("\nSingle-pass example:")
    print(f"  {single_results[0]['answer']}\n")
    print("Two-pass example:")
    print(f"  {two_pass_results[0]['answer']}")

if __name__ == "__main__":
    run_benchmark()
