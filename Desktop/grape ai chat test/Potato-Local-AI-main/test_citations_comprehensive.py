"""
Comprehensive test: Single-pass citations across different question types
Tests Qwen3 1.7B's ability to generate accurate citations for various queries.
"""
import re
import ollama
from datetime import datetime

MODEL = "qwen3:1.7b"

# Different test scenarios
TEST_CASES = [
    {
        "name": "Factual (Person)",
        "query": "Where was Donald Trump born and when?",
        "sources": [
            {"title": "Britannica - Donald Trump", 
             "body": "Donald Trump was born on June 14, 1946, in Queens, New York City."},
            {"title": "Biography.com", 
             "body": "Trump grew up in the New York City borough of Queens."},
        ],
        "expected_citations": [1]  # Should cite source 1 for birth details
    },
    {
        "name": "Scientific Fact",
        "query": "How fast does light travel?",
        "sources": [
            {"title": "Physics Encyclopedia", 
             "body": "The speed of light in a vacuum is approximately 299,792,458 meters per second."},
            {"title": "NASA Science", 
             "body": "Light travels at a constant speed of about 186,282 miles per second in empty space."},
        ],
        "expected_citations": [1, 2]  # Could cite either source
    },
    {
        "name": "Historical Event",
        "query": "When did World War 2 end?",
        "sources": [
            {"title": "History.com - WW2", 
             "body": "World War II ended in Europe on May 8, 1945, known as V-E Day."},
            {"title": "Britannica - WW2", 
             "body": "The war in the Pacific ended on September 2, 1945, when Japan formally surrendered."},
        ],
        "expected_citations": [1, 2]  # Should cite specific sources
    },
    {
        "name": "Current Event",
        "query": "What is the current US President?",
        "sources": [
            {"title": "White House Official", 
             "body": "Joe Biden is serving as the 46th President of the United States."},
            {"title": "Government Portal", 
             "body": "President Biden took office on January 20, 2021."},
        ],
        "expected_citations": [1]  # Should cite source 1
    },
]

def format_sources(sources):
    """Format sources with [N] numbering."""
    parts = []
    for i, source in enumerate(sources):
        n = i + 1
        title = source.get('title', 'Source')
        body = source.get('body', '')
        parts.append(f"[{n}] {title}\n{body}")
    return "\n\n".join(parts)

def test_single_pass(query, sources):
    """Test single-pass citation generation."""
    current_date = datetime.now().strftime("%A, %B %d, %Y")
    sources_text = format_sources(sources)
    
    prompt = (
        f"Today's date: {current_date}\n\n"
        f"Answer the question below in 2-4 clear sentences using the search results.\n"
        f"After any fact from a source, add its citation number in square brackets [N].\n"
        f"For example: \"Paris is the capital of France [1].\"\n\n"
        f"Search results:\n{sources_text}\n\n"
        f"Question: {query}\n"
        f"Answer:"
    )
    
    try:
        response = ollama.generate(model=MODEL, prompt=prompt)
        return response['response'].strip()
    except Exception as e:
        return f"ERROR: {e}"

def analyze_citations(answer, expected_citations):
    """Check if answer has citations and if they match expected sources."""
    # Find all citations
    citations = re.findall(r'\[(\d+)\]', answer)
    has_citations = len(citations) > 0
    
    # Check if any expected citations are present
    citations_int = [int(c) for c in citations]
    has_expected = any(c in citations_int for c in expected_citations)
    
    return {
        "has_citations": has_citations,
        "num_citations": len(citations),
        "citations": citations_int,
        "has_expected": has_expected,
        "pass": has_citations and has_expected
    }

def run_tests():
    """Run all test cases."""
    print(f"Comprehensive Citation Test - {MODEL}")
    print("=" * 80)
    print(f"Testing {len(TEST_CASES)} different question types\n")
    
    results = []
    
    for i, test_case in enumerate(TEST_CASES):
        print(f"\n[Test {i+1}/{len(TEST_CASES)}] {test_case['name']}")
        print("-" * 80)
        print(f"Query: {test_case['query']}")
        
        answer = test_single_pass(test_case['query'], test_case['sources'])
        analysis = analyze_citations(answer, test_case['expected_citations'])
        
        results.append({
            "test_name": test_case['name'],
            "analysis": analysis,
            "answer": answer
        })
        
        status = "PASS" if analysis['pass'] else "FAIL"
        print(f"Result: {status}")
        print(f"Citations found: {analysis['citations']}")
        print(f"Expected any of: {test_case['expected_citations']}")
        print(f"Answer: {answer}")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    pass_count = sum(1 for r in results if r['analysis']['pass'])
    total = len(results)
    
    print(f"\nTests passed:        {pass_count}/{total} ({pass_count/total:.0%})")
    print(f"All had citations:   {all(r['analysis']['has_citations'] for r in results)}")
    
    avg_citations = sum(r['analysis']['num_citations'] for r in results) / len(results)
    print(f"Avg citations/query: {avg_citations:.1f}")
    
    print("\n" + "=" * 80)
    print("CONCLUSION")
    print("=" * 80)
    
    if pass_count == total:
        print("\n[EXCELLENT] Single-pass citations work across all question types!")
        print("Qwen3 1.7B reliably generates accurate citations for:")
        for r in results:
            print(f"  - {r['test_name']}")
        print("\nRecommendation: Switch to single-pass citation generation.")
    elif pass_count >= total * 0.75:
        print(f"\n[GOOD] Single-pass citations work for most question types ({pass_count}/{total})")
        print("Recommendation: Consider switching, but test with your specific use cases.")
    else:
        print(f"\n[NEEDS WORK] Single-pass citations are inconsistent ({pass_count}/{total})")
        print("Recommendation: Keep the two-pass approach or investigate failures.")

if __name__ == "__main__":
    run_tests()
