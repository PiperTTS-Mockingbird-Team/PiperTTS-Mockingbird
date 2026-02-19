"""
Iterative citation prompt test — runs multiple strategies and shows output for each.
Model: qwen2.5:1.5b  (the actual app model)
"""
import ollama

MODEL = "qwen2.5:1.5b"

SOURCES = [
    {
        "title": "Donald Trump News – NBC News",
        "href":  "https://www.nbcnews.com/politics/donald-trump",
        "body":  "President Donald Trump signed a new executive order targeting federal spending. Democrats criticized the decision as reckless."
    },
    {
        "title": "Donald Trump latest – AP News",
        "href":  "https://apnews.com/hub/donald-trump",
        "body":  "Trump met with European leaders at the G7 summit. Talks focused on trade tariffs and NATO commitments."
    },
    {
        "title": "Trump breaking news – The Guardian",
        "href":  "https://www.theguardian.com/us-news/trump",
        "body":  "A federal judge blocked Trump's latest immigration policy overnight. The case could reach the Supreme Court."
    },
]

def fmt(results):
    parts = []
    for i, r in enumerate(results):
        n = i + 1
        parts.append(f"[{n}] {r['title']}\n{r['body']}")
    return "\n\n".join(parts)

SOURCES_BLOCK = fmt(SOURCES)
QUESTION = "What is the latest Donald Trump news?"

# ── Variant A: system+user (baseline)
VA_SYSTEM = (
    "You answer questions in prose. When using a fact from search results, "
    "add [N] inline after it. Never list sources or URLs. No References section."
)
VA_USER = f"Search results:\n{SOURCES_BLOCK}\n\nQuestion: {QUESTION}"

# ── Variant B: single user message, very direct
VB_USER = f"""Use ONLY the numbered search results below to answer the question in 2-3 sentences of plain prose. After each fact write the source number in brackets like [1] or [2]. Do NOT create a list. Do NOT print URLs.

Search results:
{SOURCES_BLOCK}

Question: {QUESTION}
Answer in prose:"""

# ── Variant C: few-shot example baked in
VC_USER = f"""You are answering a question using numbered search results. Write a short prose answer (2-3 sentences). Put [N] after each fact you take from source N. No lists, no URLs, no References section.

Example:
Results:
[1] Sky News
The president signed a trade deal today.
[2] BBC
Protests erupted in three cities overnight.

Question: What happened today?
Answer: The president signed a trade deal [1], while protests broke out in three cities [2].

---

Results:
{SOURCES_BLOCK}

Question: {QUESTION}
Answer:"""

# ── Variant D: rules + inline demonstration
VD_USER = f"""Answer the question below in 2-3 sentences using the search results. Rules:
- Write flowing sentences, not a list.
- After each fact, write its source number in [brackets], e.g. "Trump signed an order [1]."
- Never print titles, URLs, or a References section.

Search results:
{SOURCES_BLOCK}

Question: {QUESTION}
Answer:"""

VARIANTS = [
    ("A - sys+user short",   [{"role":"system","content":VA_SYSTEM},{"role":"user","content":VA_USER}]),
    ("B - single direct",    [{"role":"user","content":VB_USER}]),
    ("C - few-shot",         [{"role":"user","content":VC_USER}]),
    ("D - rules+demo",       [{"role":"user","content":VD_USER}]),
]

print(f"MODEL: {MODEL}\n")
print("SOURCES SENT:")
print(SOURCES_BLOCK)
print()

for name, messages in VARIANTS:
    print("=" * 60)
    print(f"VARIANT {name}")
    print("=" * 60)
    try:
        r = ollama.chat(model=MODEL, messages=messages)
        print(r["message"]["content"].strip())
    except Exception as e:
        print(f"ERROR: {e}")
    print()
