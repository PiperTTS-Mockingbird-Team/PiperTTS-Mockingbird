"""
Simple test: Can Qwen3 1.7B generate accurate in-text citations on the first pass?
Tests ONLY the single-pass approach with 10 runs.
"""
import re
import ollama
from datetime import datetime

MODEL = "qwen3:1.7b"
REPS = 10

# ---------------------------------------------------------------------------
# Test data
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
        "body":  "Trump's paternal grandparents emigrated from Kallstadt, Germany, while his mother was born in Scotland.",
    },
]

# ---------------------------------------------------------------------------
# Format sources
# ---------------------------------------------------------------------------
def format_sources(results):
    parts = []
    for i, r in enumerate(results):
        n = i + 1
        title = r.get("title", "Source").strip()
        body = r.get("body", "").strip()[:1200]
        parts.append(f"[{n}] {title}\n{body}")
    return "\n\n".join(parts)

# ---------------------------------------------------------------------------
# Test single-pass citations
# ---------------------------------------------------------------------------
def test_single_pass_citation():
    """Ask model to generate answer WITH citations in one pass."""
    current_date = datetime.now().strftime("%A, %B %d, %Y")
    sources = format_sources(RAW_SOURCES)
    
    prompt = (
        f"Today's date: {current_date}\n\n"
        f"Answer the question below in 2-4 clear sentences using the search results.\n"
        f"After any fact from a source, add its citation number in square brackets [N].\n"
        f"For example: \"Paris is the capital of France [1].\" or \"The tower was built in 1889 [2].\"\n\n"
        f"Search results:\n{sources}\n\n"
        f"Question: {QUERY}\n"
        f"Answer:"
    )
    
    response = ollama.generate(model=MODEL, prompt=prompt)
    return response['response'].strip()

# ---------------------------------------------------------------------------
# Score the answer
# ---------------------------------------------------------------------------
def analyze_answer(answer):
    """
    Check:
    1. Are there any citations? [N]
    2. Are citations accurate? (match the facts they support)
    3. Is prose quality good? (expected keywords present)
    """
    # 1. Check for citations
    citations = re.findall(r'\[(\d+)\]', answer)
    has_citations = len(citations) > 0
    num_citations = len(citations)
    
    # 2. Citation accuracy
    accuracy_checks = []
    
    # Birth location/date should cite [1]
    birth_matches = list(re.finditer(r'(Queens|New York|1946|June)[^.!?]*\[(\d+)\]', answer, re.IGNORECASE))
    if birth_matches:
        for match in birth_matches:
            cited = int(match.group(2))
            is_correct = (cited == 1)
            accuracy_checks.append({
                "fact": "birth_info",
                "cited": cited,
                "correct": is_correct,
                "text": match.group(0)
            })
    
    # Political info should cite [2]
    political_matches = list(re.finditer(r'(Republican|45th|President)[^.!?]*\[(\d+)\]', answer, re.IGNORECASE))
    if political_matches:
        for match in political_matches:
            cited = int(match.group(2))
            is_correct = (cited == 2)
            accuracy_checks.append({
                "fact": "political_info",
                "cited": cited,
                "correct": is_correct,
                "text": match.group(0)
            })
    
    correct_citations = sum(1 for c in accuracy_checks if c['correct'])
    total_citations_checked = len(accuracy_checks)
    
    accuracy_rate = correct_citations / total_citations_checked if total_citations_checked > 0 else 0.0
    
    # 3. Prose quality
    expected_keywords = ['trump', 'born', 'president', 'republican']
    keywords_found = [kw for kw in expected_keywords if kw in answer.lower()]
    prose_quality = len(keywords_found) >= 3
    
    # Overall pass
    passed = (has_citations and accuracy_rate >= 0.5 and prose_quality)
    
    return {
        "has_citations": has_citations,
        "num_citations": num_citations,
        "accuracy_checks": accuracy_checks,
        "correct_citations": correct_citations,
        "accuracy_rate": round(accuracy_rate, 2),
        "prose_quality": prose_quality,
        "keywords_found": keywords_found,
        "pass": passed,
        "answer": answer,
    }

# ---------------------------------------------------------------------------
# Run test
# ---------------------------------------------------------------------------
def run_test():
    print(f"Testing Qwen3 1.7B - Single-pass in-text citations")
    print(f"Question: {QUERY}")
    print("=" * 80)
    print(f"\nRunning {REPS} tests...\n")
    
    results = []
    for i in range(REPS):
        print(f"Run {i+1}/{REPS}...", end=" ", flush=True)
        answer = test_single_pass_citation()
        analysis = analyze_answer(answer)
        results.append(analysis)
        
        status = "PASS" if analysis['pass'] else "FAIL"
        print(f"{status}  |  {analysis['num_citations']} cites  |  {analysis['correct_citations']}/{len(analysis['accuracy_checks'])} correct  |  acc={analysis['accuracy_rate']:.2f}")
    
    # Summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    pass_count = sum(1 for r in results if r['pass'])
    has_cites_count = sum(1 for r in results if r['has_citations'])
    prose_count = sum(1 for r in results if r['prose_quality'])
    
    avg_num_citations = sum(r['num_citations'] for r in results) / len(results)
    avg_accuracy = sum(r['accuracy_rate'] for r in results) / len(results)
    
    print(f"\nPass rate:              {pass_count}/{REPS} = {pass_count/REPS:.1%}")
    print(f"Has citations:          {has_cites_count}/{REPS} = {has_cites_count/REPS:.1%}")
    print(f"Prose quality:          {prose_count}/{REPS} = {prose_count/REPS:.1%}")
    print(f"Avg citations per run:  {avg_num_citations:.1f}")
    print(f"Avg accuracy:           {avg_accuracy:.2f}")
    
    # Show detailed citation accuracy
    print("\nCitation accuracy breakdown:")
    all_checks = [c for r in results for c in r['accuracy_checks']]
    if all_checks:
        correct = sum(1 for c in all_checks if c['correct'])
        total = len(all_checks)
        print(f"  Total citation placements: {total}")
        print(f"  Correct placements:        {correct}")
        print(f"  Accuracy:                  {correct/total:.1%}")
    
    # Recommendation
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    
    if pass_count/REPS >= 0.8 and avg_accuracy >= 0.7:
        print("\n[EXCELLENT] Qwen3 1.7B generates accurate citations on the first pass.")
        print("   You can ELIMINATE the second citation rewrite pass.")
        print(f"   - Success rate: {pass_count/REPS:.0%}")
        print(f"   - Citation accuracy: {avg_accuracy:.0%}")
        print("   - This will make your app faster and simpler!")
    elif pass_count/REPS >= 0.6:
        print("\n[MODERATE] Single-pass citations work reasonably well.")
        print(f"   - Success rate: {pass_count/REPS:.0%}")
        print(f"   - Citation accuracy: {avg_accuracy:.0%}")
        print("   You could switch to single-pass, but test with your actual use cases.")
    else:
        print("\n[NOT RELIABLE] Single-pass citations need improvement.")
        print(f"   - Success rate: {pass_count/REPS:.0%}")
        print(f"   - Citation accuracy: {avg_accuracy:.0%}")
        print("   Keep the current two-pass approach for now.")
    
    # Show a few examples
    print("\n" + "=" * 80)
    print("EXAMPLE OUTPUTS")
    print("=" * 80)
    
    # Show first 3 examples
    for i in range(min(3, len(results))):
        print(f"\nExample {i+1}:")
        print(f"  {results[i]['answer']}")
        if results[i]['accuracy_checks']:
            print(f"  Citations: ", end="")
            for check in results[i]['accuracy_checks']:
                symbol = "+" if check['correct'] else "-"
                print(f"{symbol}[{check['cited']}] ", end="")
            print()

if __name__ == "__main__":
    run_test()
