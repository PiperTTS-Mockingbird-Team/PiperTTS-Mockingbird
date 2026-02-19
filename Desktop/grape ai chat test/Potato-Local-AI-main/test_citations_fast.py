"""
FAST TEST: Can Qwen3 1.7B generate in-text citations on first pass?
Runs 3 times for quick validation.
"""
import re
import ollama
from datetime import datetime

MODEL = "qwen3:1.7b"

# Test data
QUERY = "Where was Donald Trump born and what is his political affiliation?"

RAW_SOURCES = [
    {"title": "Where was Donald Trump born – Britannica", 
     "href": "https://www.britannica.com/biography/Donald-Trump",
     "body": "Donald Trump was born on June 14, 1946, in Queens, New York City."},
    {"title": "President Donald J. Trump – White House",
     "href": "https://www.whitehouse.gov/administration/donald-j-trump/",
     "body": "Donald Trump served as the 45th President of the United States. He is a Republican."},
    {"title": "Donald Trump – Wikipedia",
     "href": "https://en.wikipedia.org/wiki/Donald_Trump",
     "body": "Trump's paternal grandparents emigrated from Kallstadt, Germany."},
]

def format_sources(results):
    parts = []
    for i, r in enumerate(results):
        parts.append(f"[{i+1}] {r['title']}\n{r['body']}")
    return "\n\n".join(parts)

def test_with_citations():
    """Ask for citations directly in first pass."""
    current_date = datetime.now().strftime("%A, %B %d, %Y")
    sources = format_sources(RAW_SOURCES)
    
    prompt = (
        f"Today's date: {current_date}\n\n"
        f"Answer the question below in 2-4 clear sentences using the search results.\n"
        f"After any fact from a source, add its citation number in square brackets [N].\n"
        f"Example: \"Paris is the capital of France [1].\"\n\n"
        f"Search results:\n{sources}\n\n"
        f"Question: {QUERY}\n"
        f"Answer:"
    )
    
    response = ollama.generate(model=MODEL, prompt=prompt)
    return response['response'].strip()

def analyze(answer):
    citations = re.findall(r'\[(\d+)\]', answer)
    has_cites = len(citations) > 0
    
    # Check accuracy
    correct = 0
    total = 0
    
    # Birth info should cite [1]
    if re.search(r'(Queens|New York|1946|June)[^.!?]*\[(\d+)\]', answer, re.I):
        total += 1
        if re.search(r'(Queens|New York|1946|June)[^.!?]*\[1\]', answer, re.I):
            correct += 1
    
    # Political info should cite [2]
    if re.search(r'(Republican|45th|President)[^.!?]*\[(\d+)\]', answer, re.I):
        total += 1
        if re.search(r'(Republican|45th|President)[^.!?]*\[2\]', answer, re.I):
            correct += 1
    
    accuracy = correct / total if total > 0 else 0.0
    
    return {
        "has_citations": has_cites,
        "num_citations": len(citations),
        "accuracy": accuracy,
        "answer": answer
    }

# Run test
print(f"Testing {MODEL} - Single-pass in-text citations")
print("=" * 70)
print(f"Question: {QUERY}\n")

results = []
for i in range(3):
    print(f"Run {i+1}/3... ", end="", flush=True)
    answer = test_with_citations()
    score = analyze(answer)
    results.append(score)
    print(f"Citations: {score['num_citations']} | Accuracy: {score['accuracy']:.0%}")
    print(f"  {answer}\n")

# Summary
print("=" * 70)
print("SUMMARY")
print("=" * 70)
avg_accuracy = sum(r['accuracy'] for r in results) / len(results)
all_have_cites = all(r['has_citations'] for r in results)

print(f"All runs had citations:  {all_have_cites}")
print(f"Average accuracy:        {avg_accuracy:.0%}")

if all_have_cites and avg_accuracy >= 0.7:
    print("\n[RESULT] Single-pass citations work WELL with Qwen3 1.7B!")
    print("You can consider eliminating the second citation pass.")
elif all_have_cites and avg_accuracy >= 0.5:
    print("\n[RESULT] Single-pass citations work MODERATELY well.")
    print("Test more to decide if you want to switch.")
else:
    print("\n[RESULT] Single-pass citations need improvement.")
    print("Keep the current two-pass approach.")
