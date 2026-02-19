"""
Test if Qwen3 1.7B can generate accurate in-text citations on the first pass.
This test compares:
  1. Single-pass approach (ask for citations directly)
  2. Current two-pass approach (prose first, then add citations)

Metrics:
  - has_citations: Does the answer contain [N] citation markers?
  - citation_accuracy: Are citations placed correctly (matched to supporting sources)?
  - prose_quality: Is the answer coherent and complete?
  - pass: All three metrics succeed

Runs REPS times for each approach and reports averages.
"""
import re
import ollama
from datetime import datetime

MODEL = "qwen3:1.7b"
REPS = 10  # runs per test

# ---------------------------------------------------------------------------
# Test data: realistic search results for "Where was Donald Trump born?"
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

# Expected facts that should be cited:
# - Born June 14, 1946 → [1]
# - Born in Queens, New York City → [1]
# - 45th President → [2]
# - Republican → [2]

# ---------------------------------------------------------------------------
# Source formatters
# ---------------------------------------------------------------------------
_MAX_CHARS = 1200

def _format_sources_plain(results):
    """Plain numbered block without sentence tags."""
    parts = []
    for i, r in enumerate(results):
        n = i + 1
        title = (r.get("title") or "Source").strip()
        body  = (r.get("body")  or "").strip()[:_MAX_CHARS]
        parts.append(f"[{n}] {title}\n{body}")
    return "\n\n".join(parts)

def _format_sources_tagged(results):
    """Each sentence ends with [N] — used for two-pass fill-in-blanks."""
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
# Single-pass approach: ask for citations directly
# ---------------------------------------------------------------------------
def test_single_pass_with_citations():
    """Ask the model to generate an answer WITH in-text citations in a single pass."""
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
        response = ollama.generate(
            model=MODEL,
            prompt=prompt
        )
        answer = response['response'].strip()
        return answer
    except Exception as e:
        print(f"Single-pass error: {e}")
        return ""

# ---------------------------------------------------------------------------
# Two-pass approach: current production method
# ---------------------------------------------------------------------------
def test_two_pass_with_rewrite():
    """Generate clean prose first, then add citations in a second pass."""
    current_date = datetime.now().strftime("%A, %B %d, %Y")
    sources_plain = _format_sources_plain(RAW_SOURCES)
    
    # First pass: clean prose only
    first_prompt = (
        f"Today's date: {current_date}\n\n"
        f"Answer the question below in 2-4 clear sentences using the search results.\n"
        f"Write flowing prose only — do not include any citation numbers or references.\n\n"
        f"Search results:\n{sources_plain}\n\n"
        f"Question: {QUERY}\n"
        f"Answer:"
    )
    
    try:
        first_response = ollama.generate(
            model=MODEL,
            prompt=first_prompt
        )
        first_pass = first_response['response'].strip()
        
        # Second pass: add citations
        sources_tagged = _format_sources_tagged(RAW_SOURCES)
        answer_with_q = _add_placeholders(first_pass)
        
        system_msg = (
            "You insert citation numbers into an answer. "
            "Your ONLY job is to swap each [?] for the correct [N]. "
            "Do NOT change, rephrase, add, or remove any other words. "
            "Output ONLY the completed answer — no lists, no explanations, no URLs."
        )
        user_msg = (
            "Each source sentence ends with its number. Replace every [?] with the matching [N].\n"
            "Keep every word EXACTLY as written. Output only the final answer.\n\n"
            "=== EXAMPLE ===\n"
            "Sources:\n"
            "[1] Bananas are yellow [1].\n"
            "[2] Apples grow in cool climates [2].\n"
            "Answer with [?]: Bananas are yellow [?]. Apples grow in cool climates [?].\n"
            "Completed answer: Bananas are yellow [1]. Apples grow in cool climates [2].\n\n"
            "=== NOW DO THIS ===\n"
            f"Sources:\n{sources_tagged}\n\n"
            f"Answer with [?]: {answer_with_q}\n"
            "Completed answer:"
        )
        
        messages = [
            {'role': 'system', 'content': system_msg},
            {'role': 'user',   'content': user_msg},
        ]
        
        result = ollama.chat(model=MODEL, messages=messages)
        rewritten = result['message']['content'].strip()
        
        # Clean up marker if model echoed it
        marker = 'Completed answer:'
        marker_pos = rewritten.lower().find(marker.lower())
        if marker_pos != -1:
            after = rewritten[marker_pos + len(marker):].strip()
            if after:
                rewritten = after
        
        # Strip trailing junk
        for stop_phrase in ('Sources:', '\n\n[1] ', '\n\n[2] '):
            idx = rewritten.find(stop_phrase)
            if idx != -1:
                rewritten = rewritten[:idx].strip()
        
        # If rewrite failed, fall back to first pass
        if not rewritten or '[?]' in rewritten:
            return first_pass
        
        return rewritten
        
    except Exception as e:
        print(f"Two-pass error: {e}")
        return ""

# ---------------------------------------------------------------------------
# Scoring: check citation presence and accuracy
# ---------------------------------------------------------------------------
def score_answer(answer):
    """
    Score an answer for:
    1. has_citations: At least one [N] marker present
    2. citation_accuracy: Citations match the facts they support
    3. prose_quality: Answer is coherent (has expected keywords)
    """
    # Metric 1: Are there any citations?
    citations = re.findall(r'\[(\d+)\]', answer)
    has_citations = len(citations) > 0
    
    # Metric 2: Citation accuracy
    # Check if citations are placed near the facts they support
    accuracy_score = 0
    accuracy_checks = 0
    
    # Check birth location/date facts (should cite [1])
    if re.search(r'\b(Queens|New York|1946|June)\b', answer, re.IGNORECASE):
        accuracy_checks += 1
        # Find citation near these facts
        for match in re.finditer(r'(Queens|New York|1946|June)[^.!?]*\[(\d+)\]', answer, re.IGNORECASE):
            cited_num = int(match.group(2))
            if cited_num == 1:  # Source [1] has birth info
                accuracy_score += 1
                break
    
    # Check political affiliation facts (should cite [2])
    if re.search(r'\b(Republican|45th President|President)\b', answer, re.IGNORECASE):
        accuracy_checks += 1
        # Find citation near these facts
        for match in re.finditer(r'(Republican|45th|President)[^.!?]*\[(\d+)\]', answer, re.IGNORECASE):
            cited_num = int(match.group(2))
            if cited_num == 2:  # Source [2] has political info
                accuracy_score += 1
                break
    
    citation_accuracy = accuracy_score / accuracy_checks if accuracy_checks > 0 else 0.0
    
    # Metric 3: Prose quality (expected keywords present)
    expected_keywords = ['trump', 'born', 'president', 'republican']
    answer_lower = answer.lower()
    keywords_found = sum(1 for kw in expected_keywords if kw in answer_lower)
    prose_quality = keywords_found >= 3  # At least 3 out of 4
    
    # Overall pass: all metrics succeed
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
    print(f"Testing {MODEL} with {REPS} runs per approach\n")
    print("=" * 80)
    print(f"Query: {QUERY}\n")
    
    # Test single-pass approach
    print("\n📝 SINGLE-PASS APPROACH (ask for citations directly)")
    print("-" * 80)
    single_results = []
    for i in range(REPS):
        answer = test_single_pass_with_citations()
        score = score_answer(answer)
        single_results.append(score)
        status = "✓ PASS" if score['pass'] else "✗ FAIL"
        print(f"  Run {i+1:>2}: {status}  citations={score['has_citations']}  "
              f"accuracy={score['citation_accuracy']:.2f}  prose={score['prose_quality']}")
        if i == 0:  # Show first example
            print(f"      Example: {answer[:150]}...")
    
    # Test two-pass approach
    print("\n\n📝 TWO-PASS APPROACH (current production method)")
    print("-" * 80)
    two_pass_results = []
    for i in range(REPS):
        answer = test_two_pass_with_rewrite()
        score = score_answer(answer)
        two_pass_results.append(score)
        status = "✓ PASS" if score['pass'] else "✗ FAIL"
        print(f"  Run {i+1:>2}: {status}  citations={score['has_citations']}  "
              f"accuracy={score['citation_accuracy']:.2f}  prose={score['prose_quality']}")
        if i == 0:  # Show first example
            print(f"      Example: {answer[:150]}...")
    
    # Calculate averages
    print("\n\n" + "=" * 80)
    print("RESULTS SUMMARY")
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
    
    print(f"\nSingle-pass approach:")
    print(f"  Pass rate:          {single_avg['pass_rate']:>6.1%}")
    print(f"  Has citations:      {single_avg['citation_rate']:>6.1%}")
    print(f"  Avg accuracy:       {single_avg['avg_accuracy']:>6.2f}")
    print(f"  Prose quality:      {single_avg['prose_rate']:>6.1%}")
    
    print(f"\nTwo-pass approach:")
    print(f"  Pass rate:          {two_pass_avg['pass_rate']:>6.1%}")
    print(f"  Has citations:      {two_pass_avg['citation_rate']:>6.1%}")
    print(f"  Avg accuracy:       {two_pass_avg['avg_accuracy']:>6.2f}")
    print(f"  Prose quality:      {two_pass_avg['prose_rate']:>6.1%}")
    
    # Recommendation
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    
    if single_avg['pass_rate'] >= 0.8 and single_avg['avg_accuracy'] >= 0.7:
        print("✓ Single-pass citations work well with Qwen3 1.7B!")
        print("  You can eliminate the second citation rewrite pass.")
        print(f"  Success rate: {single_avg['pass_rate']:.1%} | Accuracy: {single_avg['avg_accuracy']:.2f}")
    elif single_avg['pass_rate'] >= 0.5:
        print("⚠ Single-pass citations work moderately well.")
        print(f"  Success rate: {single_avg['pass_rate']:.1%} | Accuracy: {single_avg['avg_accuracy']:.2f}")
        print("  Consider keeping the two-pass approach for higher accuracy.")
    else:
        print("✗ Single-pass citations are unreliable.")
        print(f"  Success rate: {single_avg['pass_rate']:.1%} | Accuracy: {single_avg['avg_accuracy']:.2f}")
        print("  Recommend keeping the current two-pass approach.")
    
    # Show some example outputs
    print("\n\n" + "=" * 80)
    print("EXAMPLE OUTPUTS")
    print("=" * 80)
    
    print("\nSingle-pass (first run):")
    print(f"  {single_results[0]['answer']}")
    
    print("\nTwo-pass (first run):")
    print(f"  {two_pass_results[0]['answer']}")

if __name__ == "__main__":
    run_benchmark()
