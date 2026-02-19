import ollama
from datetime import datetime
from ddgsearch import (
    _build_search_prompt, _format_sources_for_prompt,
    _build_citation_rewrite_prompt, _rewrite_with_citations
)

MODEL = "qwen2.5:1.5b"

RAW_RESULTS = [
    {"title": "How are In-N-Out fries made", "href": "https://example.com/1", "body": "In-N-Out fries are hand-washed, peeled, and cut in-house from whole potatoes, then fried once fresh."},
    {"title": "McDonald's Reveals Exactly How Your Beloved Fries Are Made", "href": "https://example.com/2", "body": "McDonald's fries are cut and peeled fresh daily before being dipped into an Ingredient Bath to season them."},
    {"title": "How Many Ingredients Are In In-N-Out's Infamous Fries", "href": "https://example.com/3", "body": "In-N-Out fries contain only two ingredients: potatoes and sunflower oil. No pre-seasoning is added before frying."},
    {"title": "how mcdonald's fries are made", "href": "https://example.com/4", "body": "McDonald's fries use a blend of oils and are partially fried at the factory before being frozen and shipped."},
    {"title": "How Does In-N-Out Cook Its Fries", "href": "https://example.com/5", "body": "In-N-Out cooks its fries by throwing them directly into the fryer once cut, with no pre-frying or freezing."},
]

QUERY = "Look up the difference between how In-N-Out fries are made vs how McDonald's fries are made"
DATE = datetime.now().strftime("%A, %B %d, %Y")

search_context = _format_sources_for_prompt(RAW_RESULTS)
prompt1 = _build_search_prompt(QUERY, search_context, DATE)

print("=== PASS 1: Clean prose ===")
r1 = ollama.chat(model=MODEL, messages=[{"role": "user", "content": prompt1}])
first_pass = r1["message"]["content"].strip()
print(first_pass)

print("\n=== PASS 2: Citation rewrite ===")
rewritten = _rewrite_with_citations(first_pass, RAW_RESULTS, MODEL)
print(rewritten)

