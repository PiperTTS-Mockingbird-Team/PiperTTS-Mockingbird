import sys
import re
import ollama
import concurrent.futures
from datetime import datetime
from urllib.parse import urlparse

# Import the new multi-source search system (SearXNG -> DuckDuckGo -> Bing)
from multi_search import search_internet, search_multi_source

# Fix for Windows console encoding issues
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, Exception):
        import io
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        except Exception:
            pass

# search_internet is now imported from multi_search.py
# It tries SearXNG first, then DuckDuckGo, then Bing as fallbacks

OPTIMIZER_MODEL = 'qwen3:1.7b'

# Per search angle: how many candidates to fetch, and how many to keep after scoring
CANDIDATES_PER_ANGLE = 8
TOP_N_PER_ANGLE = 3


def _score_result(result, query):
    """Score a result for relevance to a query. Higher = better."""
    query_words = set(query.lower().split())
    title = (result.get('title') or '').lower()
    body = (result.get('body') or '').lower()
    title_hits = sum(1 for w in query_words if w in title)
    body_hits = sum(1 for w in query_words if w in body)
    body_len_bonus = min(len(body) / 500.0, 1.0)  # reward richer snippets, cap at 1.0
    return title_hits * 2 + body_hits + body_len_bonus


def _dedupe_by_domain(results):
    """Remove duplicate domains, keeping the highest-scored result per domain."""
    seen = set()
    deduped = []
    for r in results:
        try:
            domain = urlparse(r.get('href', '')).netloc.lower().lstrip('www.')
        except Exception:
            domain = ''
        if domain not in seen:
            seen.add(domain)
            deduped.append(r)
    return deduped

NEEDS_SEARCH_SYSTEM_MSG = """Decide if a question needs an internet search. Reply ONLY: YES or NO

YES - needs internet:
- Current events, news, weather, prices, stocks, sports results
- Questions about events after 2023 or with years like 2024, 2025, 2026
- Real-time data: "what time is it in...", "weather in...", "price of..."
- Specific products, releases, or schedules that change
- Questions about specific people or characters: "is X alive", "how old is X", "what is X's favorite food", "who did X marry"
- Factual details that might not be in your training data
- Any question where the answer could have changed recently

NO - does NOT need internet:
- Writing/creating: "write a poem", "write code", "create a story"
- Math/logic: "what is 2+2", "solve this equation"
- Conversation: "hello", "tell me a joke", "how are you"
- General Advice: "tips for sleep", "how to cook rice", "study advice"
- Definitions: "what does ephemeral mean"
- Translation: "translate hello to spanish"
- Explaining concepts: "what is recursion", "explain gravity", "how does DNA work"

If the question refers to a person/character from history ("he", "him", "she") and the detail wasn't already mentioned, say YES.
When in doubt, say YES.
Reply with ONLY: YES or NO"""

# Keywords that always mean "search the internet" — no need to ask the LLM
ALWAYS_SEARCH_KEYWORDS = [
    'trending', 'latest', 'recent', 'newest', 'new', 'current',
    'today', 'tonight', 'yesterday', 'this week', 'this month', 'this year',
    'right now', 'breaking', 'update', 'updated',
    'price', 'cost', 'stock', 'weather', 'forecast',
    'score', 'results', 'winner', 'standings',
    'release date', 'coming out', 'launched', 'announced',
    'news', 'rumor', 'leaked',
    'look up', 'look it up', 'search', 'internet', 'google', 'find me', 'search for',
    '2024', '2025', '2026', '2027',
]

def needs_internet_search(query, history=None):
    """Decides if a query needs an internet search. 
    First checks for obvious keywords, then falls back to the LLM."""
    query_lower = query.lower()
    
    # Fast path: if any keyword is in the query, always search
    for keyword in ALWAYS_SEARCH_KEYWORDS:
        if keyword in query_lower:
            return True
    
    # Slow path: ask the LLM
    try:
        history_block = f"\nConversation History:\n{history}\n" if history else ""
        response = ollama.chat(
            model=OPTIMIZER_MODEL,
            messages=[
                {'role': 'system', 'content': NEEDS_SEARCH_SYSTEM_MSG},
                {'role': 'user', 'content': f"{history_block}Current User Question: {query}"}
            ]
        )
        answer = response['message']['content'].strip().upper()
        # Look for YES/NO in the response
        if 'NO' in answer:
            return False
        return True  # Default to searching if unclear
    except Exception:
        return True  # Default to searching on error

OPTIMIZER_SYSTEM_MSG = """You split user questions into search engine queries. Always reply using ONLY this format:

If 1 search is enough:
SEARCH: the query

If 2-3 searches are better:
SEARCH: first query
SEARCH: second query

IMPORTANT: Each search must be about something DIFFERENT. Never rephrase the same question multiple times.

When comparing things, search for each thing SEPARATELY, not the comparison:
GOOD for "difference between X and Y fries":
SEARCH: how are X fries made
SEARCH: how are Y fries made
BAD:
SEARCH: X vs Y fries
SEARCH: comparing X and Y fries
SEARCH: difference between X and Y fries

When a question is broad, search for different angles:
GOOD for "whats the news":
SEARCH: latest breaking news today
SEARCH: world news headlines today

NEVER split simple factual questions like "what time is it in tokyo".

Reply with ONLY SEARCH: lines. Nothing else. Max 3 lines."""

def analyze_and_optimize_query(query, history=None, model=None):
    """Uses qwen2.5:1.5b to determine if a query needs multiple specific searches."""
    current_date = datetime.now().strftime("%B %d, %Y")
    try:
        history_block = f"\nConversation History:\n{history}\n" if history else ""
        response = ollama.chat(
            model=OPTIMIZER_MODEL,
            messages=[
                {'role': 'system', 'content': f"Today's date is {current_date}.\n\n{OPTIMIZER_SYSTEM_MSG}"},
                {'role': 'user', 'content': f"{history_block}Current User Question: {query}"}
            ]
        )
        content = response['message']['content'].strip()
        
        # Parse lines starting with 'SEARCH:'
        search_terms = []
        for line in content.split('\n'):
            line = line.strip()
            if line.upper().startswith('SEARCH:'):
                term = line[7:].strip()  # Remove 'SEARCH:' prefix
                if term:
                    search_terms.append(term)
            
            # Hard cutoff at 3
            if len(search_terms) >= 3:
                break
        
        return search_terms if search_terms else [query]
    except Exception:
        return [query]

def perform_concurrent_searches(queries):
    """Executes multiple searches in parallel.
    Fetches CANDIDATES_PER_ANGLE results per query, scores each set against its
    own query, keeps TOP_N_PER_ANGLE best per angle, then deduplicates by domain.
    Returns a tuple: (narrowed_results, errors, total_candidates_fetched)
    """
    per_query_results = {}  # query -> scored top-N list
    errors = set()
    total_candidates = 0
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(queries))
    future_to_query = {executor.submit(search_internet, q, CANDIDATES_PER_ANGLE): q for q in queries}
    try:
        for future in concurrent.futures.as_completed(future_to_query, timeout=15):
            q = future_to_query[future]
            try:
                results, error_type = future.result(timeout=10)
                total_candidates += len(results)
                if error_type:
                    errors.add(error_type)
                # Score against this angle's query and keep top N
                scored = sorted(results, key=lambda r: _score_result(r, q), reverse=True)
                per_query_results[q] = scored[:TOP_N_PER_ANGLE]
            except concurrent.futures.TimeoutError:
                errors.add('timeout')
                print("Search future timed out")
            except Exception as e:
                errors.add('error')
                print(f"Search future failed: {e}")
    except concurrent.futures.TimeoutError:
        errors.add('timeout')
        print("Overall search batch timed out")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    # Merge all per-angle top-N lists and deduplicate by domain
    merged = [r for results in per_query_results.values() for r in results]
    narrowed = _dedupe_by_domain(merged)
    print(f"Search pipeline: {total_candidates} candidates → {len(narrowed)} after scoring & dedup")
    return narrowed, errors, total_candidates

# ---------------------------------------------------------------------------
# Source formatting
# ---------------------------------------------------------------------------
_MAX_CHARS_PER_SOURCE = 1200
_MAX_TOTAL_CHARS = 12000

def _format_sources_for_prompt(search_results):
    """Format search results as a numbered block for the model prompt.
    Title + snippet only — no URLs (URLs cause small models to echo them as lists).
    """
    sections = []
    total_chars = 0
    for i, r in enumerate(search_results):
        n = i + 1
        title   = (r.get('title') or 'Source').strip()
        content = (r.get('body')  or '').strip()
        if len(content) > _MAX_CHARS_PER_SOURCE:
            content = content[:_MAX_CHARS_PER_SOURCE] + '...'
        section = f'[{n}] {title}\n{content}'
        sep = 2 if sections else 0
        if total_chars + sep + len(section) > _MAX_TOTAL_CHARS:
            break
        sections.append(section)
        total_chars += sep + len(section)
    return '\n\n'.join(sections)


def _build_search_prompt(query, search_context, current_date, history=None, transcript=None):
    """Build the prompt asking for an answer WITH in-text citations.
    Citations are generated in a single pass for better speed and simplicity.
    """
    history_block = (
        f"Previous conversation (use only if relevant):\n{history}\n\n"
        if history else ""
    )
    transcript_block = (
        f"Video transcript (primary source for video questions):\n{transcript}\n\n"
        if transcript else ""
    )
    return (
        f"Today's date: {current_date}\n\n"
        f"{history_block}"
        f"{transcript_block}"
        f"Answer the question below in 2-4 clear sentences using the search results.\n"
        f"If you need to think or analyze before answering, wrap your process in <think> tags.\n"
        f"Use **bold** for key terms and bulleted lists for multiple items.\n"
        f"After any fact from a source, add its citation number in square brackets [N].\n"
        f"For example: \"Paris is the capital of France [1].\" or \"The Eiffel Tower was built in 1889 [2].\"\n\n"
        f"Search results:\n{search_context}\n\n"
        f"Question: {query}\n"
        f"Answer:"
    )


def get_combined_response(query, model='qwen3:1.7b', history=None):
    """Combines internet search results with an Ollama model response."""
    current_date = datetime.now().strftime("%A, %B %d, %Y")
    
    # Step 0: Check if we even need to search
    do_search = needs_internet_search(query, history=history)
    print(f"Needs internet search: {do_search}")
    
    search_context = None
    search_results = None
    if do_search:
        # Analyze and optimize search
        search_queries = analyze_and_optimize_query(query, history=history, model=model)
        print(f"Optimized search terms: {search_queries}")
        
        search_results, search_errors, _ = perform_concurrent_searches(search_queries)
        
        if search_results:
            search_context = _format_sources_for_prompt(search_results)
        else:
            search_context = None

    try:
        # Build the prompt with conversation history if provided
        history_block = f"\nConversation History (for context):\n{history}\n" if history else ""

        if search_context:
            prompt = _build_search_prompt(query, search_context, current_date, history=history)
        else:
            prompt = (
                f"Today's date: {current_date}\n\n"
                f"{history_block}"
                f"If you need to think or analyze before answering, wrap your process in <think> tags.\n"
                f"Use **bold** for key terms and bulleted lists for multiple items.\n"
                f"Question: {query}"
            )
        response = ollama.chat(
            model=model,
            messages=[{'role': 'user', 'content': prompt}]
        )
        answer = response['message']['content']
        # Single-pass citations: answer already includes [N] markers
        return answer
    except Exception as e:
        print(f"Error in Ollama: {e}")
        return f"Response Error: {e}"

def get_combined_response_stream(query, model='qwen3:1.7b', history=None, transcript=None):
    """Combines internet search results with an Ollama model response stream.
    Yields dicts for status updates and plain strings for answer tokens.
    Status dicts: {'status': 'type', ...}
    Optionally accepts a pre-fetched video transcript to inject as extra context.
    """
    current_date = datetime.now().strftime("%A, %B %d, %Y")

    # Step 0: Check if we need to search at all
    # If a transcript is present, give the LLM a brief preview so it can decide
    # whether an internet search would still add value on top of the video content.
    yield {'status': 'checking_search'}
    search_decision_context = history
    if transcript:
        preview = transcript[:400]
        search_decision_context = (
            f"[A video transcript is available. First 400 chars: {preview}]\n"
            f"{history or ''}"
        )
    do_search = needs_internet_search(query, history=search_decision_context)
    yield {'status': 'search_decision', 'needs_search': do_search}
    
    search_context = None
    search_results = None
    if do_search:
        # Pass search_decision_context so the optimizer sees the transcript preview
        # and can form smart search terms (e.g. "Jack Russell breed info" not "dog in video")
        yield {'status': 'analyzing'}
        search_queries = analyze_and_optimize_query(query, history=search_decision_context, model=model)
        print(f"Optimized search terms: {search_queries}")
        
        optimized = len(search_queries) > 1 or search_queries[0].lower() != query.lower()
        yield {'status': 'optimize_result', 'optimized': optimized, 'queries': search_queries}
        
        # Step 2: Searching the web
        yield {'status': 'searching'}
        search_results, search_errors, total_candidates = perform_concurrent_searches(search_queries)
        yield {'status': 'search_done', 'count': total_candidates, 'top_n': len(search_results), 'errors': search_errors, 'top_results': search_results}
        
        if search_results:
            search_context = _format_sources_for_prompt(search_results)
        else:
            search_context = None

    try:
        # Step 3: Generate answer
        yield {'status': 'answering'}

        if search_context or transcript:
            prompt = _build_search_prompt(
                query, search_context or '', current_date,
                history=history, transcript=transcript
            )
        else:
            history_block = (
                f"Previous conversation (use only if relevant):\n{history}\n\n"
                if history else ""
            )
            prompt = (
                f"Today's date: {current_date}\n\n"
                f"{history_block}"
                f"If you need to think or analyze before answering, wrap your process in <think> tags.\n"
                f"Use **bold** for key terms and bulleted lists for multiple items.\n"
                f"Question: {query}"
            )

        # Single-pass streaming: citations are generated as the model streams
        stream = ollama.chat(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            stream=True
        )
        for chunk in stream:
            yield chunk['message']['content']

    except Exception as e:
        print(f"Error in Ollama: {e}")
        yield f"Response Error: {e}"

if __name__ == "__main__":
    # Test block
    user_query = input("Ask anything: ")
    print("\nProcessing...")
    ans = get_combined_response(user_query)
    print(f"\nAI: {ans}")
    print("="*50)
