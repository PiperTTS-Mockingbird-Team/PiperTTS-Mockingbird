import sys
import re
import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import webbrowser
import requests
from io import BytesIO
from urllib.parse import urlparse, quote
import ollama
from ddgsearch import get_combined_response, get_combined_response_stream
from image_search import get_image_keywords, fetch_images_for_keywords, download_and_process_image
from PIL import Image, ImageTk
from markdown_render import register_heading_hr_tags, apply_headings, apply_horizontal_rules

# ---------------------------------------------------------------------------
# Address detection (ported from chat4 js/maps.js)
# ---------------------------------------------------------------------------
_STREET_SUFFIX = (
    r'(?:Street|St\.?|Avenue|Ave\.?|Boulevard|Blvd\.?|Road|Rd\.?|Lane|Ln\.?|'
    r'Drive|Dr\.?|Court|Ct\.?|Way|Pkwy\.?|Parkway|Place|Pl\.?|Plaza|Plz\.?|'
    r'Square|Sq\.?|Center|Ctr\.?|Centre|Circle|Cir\.?|Terrace|Ter\.?|'
    r'Highway|Hwy\.?|Trail|Trl\.?|Loop)'
)
_STATE_TOKEN = r'(?:[A-Za-z]{2}|[A-Za-z]\.?\s*[A-Za-z]\.?)'

_ADDRESS_PATTERNS = [
    # "123 Main St, City, CA 92373"  (with or without ZIP)
    re.compile(
        r'\b'
        r'\d{1,6}(?:\s+\d/\d)?'
        r'\s+'
        r'(?:(?:N|S|E|W|NE|NW|SE|SW)\.?\s+)?'
        r'(?:[A-Za-z0-9][A-Za-z0-9.\'\-]*\s+){1,7}'
        + _STREET_SUFFIX + r'\b\.?'
        r'(?:\s+(?:N|S|E|W|NE|NW|SE|SW)\.?\b)?'
        r'(?:\s*(?:,\s*)?'
        r'(?:#|Apt\.?|Apartment|Suite|Ste\.?|Unit|Bldg\.?|Building|'
        r'Fl\.?|Floor|Room|Rm\.?|Dept\.?|Department)\s*[A-Za-z0-9\-]+)?'
        r'\s*(?:,\s*|\s+)'
        r'(?:[A-Za-z][A-Za-z.\'\-]*\s*){1,5}'
        r'\s*(?:,\s*|\s+)'
        + _STATE_TOKEN +
        r'(?:\s+\d{5}(?:\-\d{4})?)?'
        r'\b',
        re.IGNORECASE
    ),
    # "PO Box 123, City, CA 92373"
    re.compile(
        r'\b'
        r'P\.?\s*O\.?\s*Box\s*\d{1,10}'
        r'\s*(?:,\s*|\s+)'
        r'(?:[A-Za-z][A-Za-z.\'\-]*\s*){1,5}'
        r'\s*(?:,\s*|\s+)'
        + _STATE_TOKEN +
        r'(?:\s+\d{5}(?:\-\d{4})?)?'
        r'\b',
        re.IGNORECASE
    ),
]


def _find_addresses(text):
    """Return list of (start, end, match_text) for US addresses found in text."""
    results = []
    for pattern in _ADDRESS_PATTERNS:
        for m in pattern.finditer(text):
            s, e = m.start(), m.end()
            # Skip if this range overlaps an already-found match
            if not any(r[0] <= s < r[1] or r[0] < e <= r[1] for r in results):
                results.append((s, e, m.group(0)))
    return sorted(results, key=lambda x: x[0])


# ---------------------------------------------------------------------------
# YouTube transcript fetching
# ---------------------------------------------------------------------------
_YT_URL_PATTERN = re.compile(
    r'((?:https?://)?(?:www\.)?(?:youtube\.com/watch\?(?:[^\s&]*&)*v=|youtu\.be/)([A-Za-z0-9_\-]{11})[^\s]*)',
    re.IGNORECASE
)

def _extract_youtube_video_id(text):
    """Return (full_url, video_id) if a YouTube URL is found in text, else (None, None)."""
    m = _YT_URL_PATTERN.search(text)
    if m:
        full_url = m.group(1)
        if not full_url.startswith('http'):
            full_url = 'https://' + full_url
        return full_url, m.group(2)
    return None, None

def get_youtube_transcript(video_id):
    """Fetch captions via youtube-transcript-api (v1.x instance API).
    Returns (transcript_text, language_code) or (None, error_message).
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=['en', 'en-GB', 'en-US'])
        text = ' '.join(snip.text for snip in fetched)
        return text, 'en'
    except Exception:
        # Fall back: try without specifying language (takes whatever is available)
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            api = YouTubeTranscriptApi()
            fetched = api.fetch(video_id)
            text = ' '.join(snip.text for snip in fetched)
            return text, 'auto'
        except Exception as e:
            return None, str(e)


# Force UTF-8 encoding for Windows terminals
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        import io
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        except Exception:
            pass

class SearchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Local Search AI")
        self.root.geometry("700x700")
        self.root.configure(bg="#2b2b2b")  # Dark background
        self.history = []  # Store last 3 turns as (role, content) pairs
        self.image_references = []  # Keep references to prevent garbage collection
        self._current_image_row = None  # Active image row frame for current response
        self._current_sources_bar = None  # Active sources bar frame for current response
        self._pending_sources = []  # Search results to render as sources
        self._maps_favicon_photo = None  # Cached Google Maps favicon for address buttons

        # Header
        header_frame = tk.Frame(root, bg="#1e1e1e", height=50)
        header_frame.pack(fill='x')
        
        title_label = tk.Label(
            header_frame, 
            text="Local AI Search Assistant", 
            font=("Segoe UI", 16, "bold"), 
            bg="#1e1e1e", 
            fg="#ffffff"
        )
        title_label.pack(pady=10)

        # Chat display area
        chat_frame = tk.Frame(root, bg="#2b2b2b")
        chat_frame.pack(expand=True, fill='both', padx=20, pady=10)

        self.chat_display = scrolledtext.ScrolledText(
            chat_frame, 
            wrap=tk.WORD, 
            state='disabled',
            font=("Segoe UI", 11),
            bg="#363636",
            fg="#e0e0e0",
            insertbackground="white",
            bd=0,
            padx=10,
            pady=10
        )
        self.chat_display.pack(expand=True, fill='both')
        
        # Configure tags for message styling
        self.chat_display.tag_config('user', foreground='#93c5fd', font=("Segoe UI", 9, "bold"), spacing1=14, justify='right')
        self.chat_display.tag_config('ai', foreground='#adadad', font=("Segoe UI", 11, "bold"), spacing1=10)
        self.chat_display.tag_config('content', foreground='#e0e0e0', spacing3=15)
        self.chat_display.tag_config('error', foreground='#ff5555')
        self.chat_display.tag_config('status_label', foreground='#888888', font=("Segoe UI", 10, "italic"))
        self.chat_display.tag_config('status_value', foreground='#c586c0', font=("Segoe UI", 10))
        self.chat_display.tag_config('status_yes', foreground='#4ec9b0', font=("Segoe UI", 10, "bold"))
        self.chat_display.tag_config('status_no', foreground='#ce9178', font=("Segoe UI", 10, "bold"))
        self.chat_display.tag_config('status_bullet', foreground='#dcdcaa', font=("Segoe UI", 10))
        self.chat_display.tag_config('status_searching', foreground='#569cd6', font=("Segoe UI", 10, "italic"))
        self.chat_display.tag_config('status_warning', foreground='#e5c07b', font=("Segoe UI", 10, "italic"))
        self.chat_display.tag_config('image_header', foreground='#888888', font=("Segoe UI", 10, "italic"), spacing1=15)
        self.chat_display.tag_config('image_caption', foreground='#9cdcfe', font=("Segoe UI", 9), spacing1=8)
        # Markdown tags
        self.chat_display.tag_config('bold', font=("Segoe UI", 11, "bold"))
        self.chat_display.tag_config('italic', font=("Segoe UI", 11, "italic"))
        self.chat_display.tag_config('bullet', lmargin1=40, lmargin2=50)
        self.chat_display.tag_config('code', background='#2d2d2d', font=("Consolas", 10), borderwidth=1, relief='flat')
        self.chat_display.tag_config('inline_code', background='#2d2d2d', foreground='#ce9178',
                                     font=("Consolas", 10), borderwidth=1, relief='flat')
        # Heading + horizontal-rule tags (registered in markdown_render.py)
        register_heading_hr_tags(self.chat_display)
        # Emoji support (Windows): render emoji glyphs using an emoji-capable font.
        # Tk doesn't do font fallback per-glyph, so we apply this tag only to emoji ranges.
        self.chat_display.tag_config('emoji', font=("Segoe UI Emoji", 11))
        self.chat_display.tag_config('think_header', foreground='#9b8ab0', font=("Segoe UI", 9, "bold"), spacing1=8)
        self.chat_display.tag_config('think', foreground='#777777', font=("Segoe UI", 10, "italic"),
                                     lmargin1=20, lmargin2=20, spacing3=8)
        
        # Detected address highlight
        self.chat_display.tag_config('map_addr', foreground='#60a5fa', underline=True)
        # Inline citation tag (shared base — visual style overridden per-occurrence below)
        self.chat_display.tag_config('cite_link', foreground='#7dd3fc', underline=True,
                                     font=("Segoe UI", 8, "bold"))

        # Input area
        input_frame = tk.Frame(root, bg="#2b2b2b")
        input_frame.pack(fill='x', padx=20, pady=(0, 20))

        self.input_field = tk.Entry(
            input_frame, 
            # Use an emoji-capable font so typed/pasted emoji display correctly.
            font=("Segoe UI Emoji", 12),
            bg="#404040",
            fg="white",
            insertbackground="white",
            bd=0,
            relief=tk.FLAT
        )
        self.input_field.pack(side='left', expand=True, fill='x', ipady=8, padx=(0, 10))
        self.input_field.bind("<Return>", lambda event: self.start_search())

        # Styled button
        self.send_button = tk.Button(
            input_frame, 
            text="Search", 
            command=self.start_search,
            font=("Segoe UI", 11, "bold"),
            bg="#007acc",
            fg="white",
            activebackground="#005c99",
            activeforeground="white",
            bd=0,
            relief=tk.FLAT,
            cursor="hand2"
        )
        self.send_button.pack(side='right', ipadx=15, ipady=5)

        # Status bar
        self.status_label = tk.Label(
            root, 
            text="Ready", 
            bd=1, 
            relief=tk.SUNKEN, 
            anchor=tk.W,
            bg="#1e1e1e",
            fg="#808080",
            font=("Segoe UI", 9)
        )
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

    def _tag_emojis_in_range(self, start_idx: str, end_idx: str):
        """Apply the 'emoji' tag to emoji characters within the given text range."""
        try:
            text = self.chat_display.get(start_idx, end_idx)
        except Exception:
            return

        if not text:
            return

        # Fast pre-check: if nothing even near emoji planes, bail.
        if not any(ord(ch) >= 0x2600 for ch in text):
            return

        def is_emoji_char(ch: str) -> bool:
            cp = ord(ch)
            # Variation selector-16 and ZWJ are parts of many emoji sequences.
            if cp in (0xFE0F, 0x200D):
                return True
            # Flags
            if 0x1F1E6 <= cp <= 0x1F1FF:
                return True
            # Misc symbols + dingbats
            if 0x2600 <= cp <= 0x27BF:
                return True
            # Main emoji blocks
            if 0x1F300 <= cp <= 0x1FAFF:
                return True
            # Some additional symbols commonly rendered as emoji
            if 0x2300 <= cp <= 0x23FF:
                return True
            return False

        in_run = False
        run_start = 0
        for i, ch in enumerate(text):
            if is_emoji_char(ch):
                if not in_run:
                    in_run = True
                    run_start = i
            else:
                if in_run:
                    self.chat_display.tag_add('emoji', f"{start_idx}+{run_start}c", f"{start_idx}+{i}c")
                    in_run = False

        if in_run:
            self.chat_display.tag_add('emoji', f"{start_idx}+{run_start}c", f"{start_idx}+{len(text)}c")

        # Keep emoji font on top if combined with other tags.
        try:
            self.chat_display.tag_raise('emoji')
        except Exception:
            pass

    def _apply_code_block_coloring(self, code_widget: tk.Text, language: str, code_text: str):
        """Apply lightweight, dependency-free syntax coloring using Tk Text tags.

        This is intentionally simple (regex + heuristics) and designed to match the
        embedding behavior of our in-chat code blocks (window_create + tk.Text).
        """
        import re

        src = (code_text or '')
        if not src:
            return

        # Avoid locking the UI on huge code blocks
        if len(src) > 120_000 or src.count('\n') > 2500:
            return

        lang = (language or '').strip().lower()

        # VS Code-ish colors
        COLORS = {
            'kw': '#569cd6',
            'type': '#4ec9b0',
            'func': '#dcdcaa',
            'str': '#ce9178',
            'com': '#6a9955',
            'num': '#b5cea8',
            'key': '#9cdcfe',
        }

        for tag, color in COLORS.items():
            code_widget.tag_config(tag, foreground=color)

        def add(tag: str, start: int, end: int):
            if end <= start:
                return
            code_widget.tag_add(tag, f'1.0+{start}c', f'1.0+{end}c')

        def merge_ranges(ranges):
            if not ranges:
                return []
            ranges = sorted(ranges)
            merged = [list(ranges[0])]
            for s, e in ranges[1:]:
                if s <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], e)
                else:
                    merged.append([s, e])
            return [(s, e) for s, e in merged]

        def intersects(merged, s: int, e: int) -> bool:
            """Return True if [s,e) overlaps any merged range."""
            if not merged:
                return False
            # Binary search by start positions
            import bisect
            starts = [a for a, _ in merged]
            i = bisect.bisect_right(starts, s) - 1
            for j in (i, i + 1):
                if 0 <= j < len(merged):
                    ms, me = merged[j]
                    if s < me and e > ms:
                        return True
            return False

        def find_ranges(pattern: str, flags=0, group: int = 0):
            out = []
            for m in re.finditer(pattern, src, flags):
                if group == 0:
                    out.append((m.start(), m.end()))
                else:
                    out.append((m.start(group), m.end(group)))
            return out

        def apply_ranges(tag: str, ranges):
            for s, e in ranges:
                add(tag, s, e)

        def color_regex_filtered(tag: str, pattern: str, flags=0, group: int = 0, protected=None):
            protected = protected or []
            for m in re.finditer(pattern, src, flags):
                if group == 0:
                    s, e = m.start(), m.end()
                else:
                    s, e = m.start(group), m.end(group)
                if not intersects(protected, s, e):
                    add(tag, s, e)

        # -----------------------------------------------------------------
        # Phase 1: Strings (create protected ranges)
        # -----------------------------------------------------------------
        string_ranges = []
        if lang in ('python', 'py'):
            string_ranges += find_ranges(r"'''[\s\S]*?'''", flags=re.MULTILINE)
            string_ranges += find_ranges(r'"""[\s\S]*?"""', flags=re.MULTILINE)
            string_ranges += find_ranges(r"'(?:[^\\'\n]|\\.)*'", flags=re.MULTILINE)
            string_ranges += find_ranges(r'"(?:[^\\"\n]|\\.)*"', flags=re.MULTILINE)
        elif lang in ('javascript', 'js', 'typescript', 'ts'):
            string_ranges += find_ranges(r'`(?:[^\\`\n]|\\.)*`', flags=re.MULTILINE)
            string_ranges += find_ranges(r"'(?:[^\\'\n]|\\.)*'", flags=re.MULTILINE)
            string_ranges += find_ranges(r'"(?:[^\\"\n]|\\.)*"', flags=re.MULTILINE)
        else:
            string_ranges += find_ranges(r"'(?:[^\\'\n]|\\.)*'", flags=re.MULTILINE)
            string_ranges += find_ranges(r'"(?:[^\\"\n]|\\.)*"', flags=re.MULTILINE)

        string_ranges = merge_ranges(string_ranges)
        apply_ranges('str', string_ranges)

        # -----------------------------------------------------------------
        # Phase 2: Comments (skip anything inside strings)
        # -----------------------------------------------------------------
        comment_ranges = []
        if lang in ('python', 'py'):
            for s, e in find_ranges(r'#.*?$', flags=re.MULTILINE):
                if not intersects(string_ranges, s, e):
                    comment_ranges.append((s, e))
        elif lang in ('javascript', 'js', 'typescript', 'ts'):
            for s, e in find_ranges(r'//.*?$', flags=re.MULTILINE):
                if not intersects(string_ranges, s, e):
                    comment_ranges.append((s, e))
            for s, e in find_ranges(r'/\*[\s\S]*?\*/', flags=re.MULTILINE):
                if not intersects(string_ranges, s, e):
                    comment_ranges.append((s, e))
        elif lang in ('html', 'htm', 'xml', 'svg'):
            comment_ranges += find_ranges(r'<!--[\s\S]*?-->', flags=re.MULTILINE)
        elif lang in ('css',):
            comment_ranges += find_ranges(r'/\*[\s\S]*?\*/', flags=re.MULTILINE)
        else:
            comment_ranges += find_ranges(r'#.*?$', flags=re.MULTILINE)
            comment_ranges += find_ranges(r'//.*?$', flags=re.MULTILINE)

        comment_ranges = merge_ranges(comment_ranges)
        apply_ranges('com', comment_ranges)

        protected = merge_ranges(string_ranges + comment_ranges)

        # -----------------------------------------------------------------
        # Phase 3: Everything else (skip strings/comments)
        # -----------------------------------------------------------------
        color_regex_filtered('num', r'\b\d+(?:\.\d+)?\b', protected=protected)

        if lang in ('python', 'py'):
            kws = [
                'import', 'from', 'as', 'class', 'def', 'return', 'pass', 'raise',
                'if', 'elif', 'else', 'for', 'while', 'try', 'except', 'finally',
                'with', 'lambda', 'yield', 'in', 'is', 'and', 'or', 'not',
                'True', 'False', 'None',
            ]
            for kw in kws:
                color_regex_filtered('kw', rf'\b{re.escape(kw)}\b', protected=protected)
            color_regex_filtered('type', r'\bclass\s+([A-Za-z_][A-Za-z0-9_]*)', group=1, protected=protected)
            color_regex_filtered('func', r'\bdef\s+([A-Za-z_][A-Za-z0-9_]*)', group=1, protected=protected)

        elif lang in ('javascript', 'js', 'typescript', 'ts'):
            kws = [
                'import', 'from', 'export', 'default', 'class', 'function', 'return',
                'const', 'let', 'var', 'if', 'else', 'for', 'while', 'switch', 'case',
                'try', 'catch', 'finally', 'throw', 'new', 'this', 'true', 'false', 'null',
            ]
            for kw in kws:
                color_regex_filtered('kw', rf'\b{re.escape(kw)}\b', protected=protected)
            color_regex_filtered('type', r'\bclass\s+([A-Za-z_$][A-Za-z0-9_$]*)', group=1, protected=protected)
            color_regex_filtered('func', r'\bfunction\s+([A-Za-z_$][A-Za-z0-9_$]*)', group=1, protected=protected)
            # foo(  -> function call-ish
            color_regex_filtered('func', r'\b([A-Za-z_$][A-Za-z0-9_$]*)\s*(?=\()', group=1, protected=protected)

        elif lang in ('json',):
            color_regex_filtered('key', r'"((?:[^\\"\n]|\\.)+)"\s*:', flags=re.MULTILINE, group=1, protected=protected)
            for kw in ('true', 'false', 'null'):
                color_regex_filtered('kw', rf'\b{kw}\b', protected=protected)

        elif lang in ('html', 'htm', 'xml', 'svg'):
            color_regex_filtered('type', r'<\/?\s*([A-Za-z][A-Za-z0-9:_\-]*)', group=1, protected=protected)
            color_regex_filtered('key', r'\b([A-Za-z_:][A-Za-z0-9:_\-]*)\s*=', group=1, protected=protected)

        elif lang in ('css',):
            color_regex_filtered('key', r'\b([a-zA-Z\-]+)\s*:', group=1, protected=protected)

        # Ensure comments/strings win if overlapping other tags
        for t in ('kw', 'type', 'func', 'num', 'key'):
            try:
                code_widget.tag_lower(t)
            except Exception:
                pass
        for t in ('str', 'com'):
            try:
                code_widget.tag_raise(t)
            except Exception:
                pass


    def _format_markdown(self, start_pos, end_pos):
        """Parse markdown in the given text range and apply Tkinter styles.

        Strategy: collect all pattern matches from the raw string using regex,
        deduplicate overlapping matches (bold wins over italic), then apply every
        substitution in REVERSE character order so deletions don't shift later ops.
        Bullets are done in a second pass on the refreshed text.
        """
        import re

        self.chat_display.config(state='normal')
        try:
            raw = self.chat_display.get(start_pos, end_pos)
            sp_line, sp_col = map(int, self.chat_display.index(start_pos).split('.'))

            def char_to_idx(offset):
                """Convert a char offset in `raw` to a Tkinter 'line.col' index.
                Uses the ORIGINAL raw string — only valid when applied right-to-left."""
                before = raw[:offset]
                nl_count = before.count('\n')
                last_nl = before.rfind('\n')
                col = offset - (last_nl + 1)
                if nl_count == 0:
                    return f"{sp_line}.{sp_col + col}"
                return f"{sp_line + nl_count}.{col}"

            # ------------------------------------------------------------------
            # Collect ops: (char_start, char_end, tag, replacement_text)
            # Use a claimed-ranges set so lower-priority patterns can't overlap
            # a range already taken by a higher-priority one.
            # ------------------------------------------------------------------
            ops = []
            claimed = []  # list of (start, end) already assigned

            def overlaps(s, e):
                return any(s < ce and e > cs for cs, ce in claimed)

            # Priority 1 — code blocks  ```…```
            for m in re.finditer(r'```([a-zA-Z0-9_+#-]*)[ \t]*\n?([\s\S]*?)```', raw):
                if not overlaps(m.start(), m.end()):
                    lang = m.group(1).strip()
                    code_text = m.group(2)
                    ops.append((m.start(), m.end(), 'code_block', (lang, code_text)))
                    claimed.append((m.start(), m.end()))

            # Priority 2 — think blocks  <think>…</think>
            for m in re.finditer(r'<think>([\s\S]*?)(?:</think>|$)', raw, re.IGNORECASE):
                if not overlaps(m.start(), m.end()):
                    ops.append((m.start(), m.end(), 'think', m.group(1).strip()))
                    claimed.append((m.start(), m.end()))

            # Priority 3 — bold  **text**
            for m in re.finditer(r'\*\*(.+?)\*\*', raw, re.DOTALL):
                if not overlaps(m.start(), m.end()):
                    ops.append((m.start(), m.end(), 'bold', m.group(1)))
                    claimed.append((m.start(), m.end()))

            # Priority 4 — italic  *text*
            # Require the * is not adjacent to another * (avoids bold remnants),
            # and content doesn't start/end with whitespace (avoids "x * y").
            for m in re.finditer(r'(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)', raw):
                if not overlaps(m.start(), m.end()):
                    ops.append((m.start(), m.end(), 'italic', m.group(1)))
                    claimed.append((m.start(), m.end()))

            # Priority 5 — inline code  `code`  (single backtick, not triple)
            for m in re.finditer(r'(?<!`)(`{1})(?!`)(.+?)(?<!`)\1(?!`)', raw, re.DOTALL):
                if not overlaps(m.start(), m.end()):
                    ops.append((m.start(), m.end(), 'inline_code', m.group(2)))
                    claimed.append((m.start(), m.end()))

            # Apply all ops in REVERSE order (right-to-left) so positions stay valid
            ops.sort(key=lambda x: x[0], reverse=True)
            for char_start, char_end, tag, replacement in ops:
                w_start = char_to_idx(char_start)
                w_end   = char_to_idx(char_end)
                self.chat_display.delete(w_start, w_end)
                if tag == 'think':
                    pass  # removed from answer area; shown in Thoughts section above Answer:
                elif tag == 'code_block':
                    lang, code_text = replacement
                    widget = self._create_code_block_widget(lang, code_text)
                    self.chat_display.insert(w_start, '\n')
                    self.chat_display.window_create(w_start, window=widget)
                elif tag == 'inline_code':
                    self.chat_display.insert(w_start, replacement, 'inline_code')
                else:
                    self.chat_display.insert(w_start, replacement, tag)

            # ------------------------------------------------------------------
            # Bullet pass — re-read the now-modified text so offsets are fresh
            # ------------------------------------------------------------------
            raw2 = self.chat_display.get(start_pos, end_pos)
            sp_line2, sp_col2 = map(int, self.chat_display.index(start_pos).split('.'))

            for i, line in enumerate(raw2.split('\n')):
                stripped = line.strip()
                # Must look like "* text", "- text", or "• text"
                if not stripped or stripped[0] not in ('*', '-', '•') or len(stripped) < 2 or stripped[1] != ' ':
                    continue

                widget_line = sp_line2 + i
                col_offset  = sp_col2 if i == 0 else 0
                line_start_idx = f"{widget_line}.{col_offset}"
                line_end_idx   = self.chat_display.index(f"{widget_line}.end")

                self.chat_display.tag_add('bullet', line_start_idx, line_end_idx)

                # Swap raw markdown bullet char for a proper •
                if stripped[0] in ('*', '-'):
                    bullet_col = col_offset + line.find(stripped[0])
                    bullet_idx = f"{widget_line}.{bullet_col}"
                    self.chat_display.delete(bullet_idx, f"{bullet_idx}+1c")
                    self.chat_display.insert(bullet_idx, '•', 'status_bullet')

            # Heading pass — replace ### / ## / # with styled heading text.
            try:
                apply_headings(self.chat_display, start_pos)
            except Exception:
                pass

            # Horizontal-rule pass — replace --- / *** / ___ with a divider widget.
            try:
                apply_horizontal_rules(self.chat_display, start_pos)
            except Exception:
                pass

            # Emoji pass — tag emoji chars so they render with an emoji-capable font.
            # Use the current 'end' to ensure we include any changes made above.
            try:
                final_end = self.chat_display.index(tk.END)
                self._tag_emojis_in_range(start_pos, final_end)
            except Exception:
                pass

        finally:
            self.chat_display.config(state='disabled')

    def _create_code_block_widget(self, language, code_text):
        """Create an embedded code block widget with a header bar and action buttons.
        Mimics the chat4 code block UI: language label + Collapse / Copy / Save / Preview.
        """
        from tkinter import filedialog

        HEADER_BG  = '#2d2d2d'
        BODY_BG    = '#1a1a1a'
        BORDER_CLR = '#444444'
        BTN_CFG = dict(
            bg=HEADER_BG, fg='#cccccc', font=("Segoe UI", 9),
            bd=0, relief='flat', cursor='hand2', padx=6, pady=3,
            activebackground='#3d3d3d', activeforeground='white',
        )

        container = tk.Frame(
            self.chat_display,
            bg=BODY_BG,
            highlightbackground=BORDER_CLR,
            highlightthickness=1,
        )

        # ── Header bar ────────────────────────────────────────────────────
        header = tk.Frame(container, bg=HEADER_BG)
        header.pack(fill='x', side='top')

        lang_display = language if language else 'code'
        tk.Label(
            header, text=lang_display,
            bg=HEADER_BG, fg='#888888',
            font=("Segoe UI", 9, 'italic'), padx=8,
        ).pack(side='left')

        # ── Code body (collapsible) ────────────────────────────────────────
        body_frame = tk.Frame(container, bg=BODY_BG)
        body_frame.pack(fill='x', side='top')

        line_count = len(code_text.splitlines()) or 1
        code_height = max(2, min(line_count, 25))

        h_scroll = tk.Scrollbar(body_frame, orient='horizontal')
        code_widget = tk.Text(
            body_frame,
            font=("Consolas", 10),
            bg=BODY_BG, fg='#d4d4d4',
            insertbackground='white',
            wrap='none',
            bd=0, padx=10, pady=8,
            height=code_height,
            xscrollcommand=h_scroll.set,
            state='normal',
        )
        code_insert = (code_text or '').rstrip()
        code_widget.insert('1.0', code_insert)
        # Apply token coloring (prototype-proven). Must happen before disabling.
        self._apply_code_block_coloring(code_widget, language, code_insert)
        code_widget.config(state='disabled')
        h_scroll.config(command=code_widget.xview)
        code_widget.pack(fill='x', side='top')
        h_scroll.pack(fill='x', side='top')

        # ── Button callbacks ───────────────────────────────────────────────
        _collapsed = [False]

        def toggle_collapse():
            if _collapsed[0]:
                body_frame.pack(fill='x', side='top')
                collapse_btn.config(text='▾')
                _collapsed[0] = False
            else:
                body_frame.pack_forget()
                collapse_btn.config(text='▸')
                _collapsed[0] = True

        def copy_code():
            self.root.clipboard_clear()
            self.root.clipboard_append(code_text)
            copy_btn.config(text='✔ Copied')
            self.root.after(1500, lambda: copy_btn.config(text='⧉ Copy'))

        def save_code():
            import datetime
            _EXT_MAP = {
                'python': '.py', 'py': '.py',
                'javascript': '.js', 'js': '.js',
                'typescript': '.ts', 'ts': '.ts',
                'html': '.html', 'css': '.css',
                'json': '.json', 'yaml': '.yaml', 'yml': '.yaml',
                'bash': '.sh', 'shell': '.sh', 'sh': '.sh',
                'sql': '.sql', 'c': '.c', 'cpp': '.cpp',
                'java': '.java', 'rust': '.rs', 'go': '.go',
                'markdown': '.md', 'md': '.md',
                'svg': '.svg', 'xml': '.xml', 'go': '.go',
            }
            ext = _EXT_MAP.get((language or '').lower(), '.txt')
            ts = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            default_name = f"code-{ts}{ext}"
            path = filedialog.asksaveasfilename(
                defaultextension=ext,
                initialfile=default_name,
                filetypes=[(f"{lang_display} files", f'*{ext}'), ('All files', '*.*')],
            )
            if path:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(code_text)

        def preview_code():
            lang_lower = (language or '').lower()
            if lang_lower == 'svg':
                _preview_svg()
            elif lang_lower in ('markdown', 'md'):
                _preview_markdown()
            elif lang_lower in ('html', 'htm', ''):
                _preview_html_inline(code_text)
            else:
                # Generic popup viewer
                win = tk.Toplevel(self.root)
                win.title(f'Preview — {lang_display}')
                win.configure(bg=BODY_BG)
                win.geometry('700x500')
                txt = scrolledtext.ScrolledText(
                    win,
                    font=("Consolas", 11),
                    bg=BODY_BG, fg='#d4d4d4',
                    wrap='word', bd=0, padx=12, pady=12,
                )
                txt.pack(expand=True, fill='both')
                txt.insert('1.0', code_text)
                txt.config(state='disabled')

        def _preview_html_inline(html_src):
            """Render HTML code in an inline Tkinter window using tkinterweb.
            Mirrors chat4's preview.html: toolbar (Desktop/Mobile toggle, Refresh),
            console panel at the bottom showing render errors.
            Falls back to writing a temp file and opening the browser if tkinterweb
            is not installed.
            """
            TB_BG    = '#1e293b'
            TB_BTN   = '#334155'
            TB_HOVER = '#475569'
            BODY_DARK = '#0b1220'
            CON_BG   = '#0f172a'
            CON_FG   = '#e2e8f0'

            try:
                import tkinterweb  # pip install tkinterweb
            except ImportError:
                # Graceful browser fallback
                import tempfile
                with tempfile.NamedTemporaryFile(
                    'w', suffix='.html', delete=False, encoding='utf-8'
                ) as f:
                    f.write(html_src)
                    tmp = f.name
                webbrowser.open(f'file:///{tmp}')
                return

            win = tk.Toplevel(self.root)
            win.title('Code Preview')
            win.configure(bg=BODY_DARK)
            win.geometry('900x650')

            # ── Toolbar ─────────────────────────────────────────────
            toolbar = tk.Frame(win, bg=TB_BG, pady=6)
            toolbar.pack(fill='x', side='top')

            tk.Label(
                toolbar, text='Code Preview',
                bg=TB_BG, fg='#f8fafc',
                font=("Segoe UI", 11, 'bold'), padx=12,
            ).pack(side='left')

            _TB_BTN = dict(
                bg=TB_BTN, fg='white', font=("Segoe UI", 9),
                bd=0, relief='flat', cursor='hand2', padx=10, pady=4,
                activebackground=TB_HOVER, activeforeground='white',
            )

            # ── Preview frame (houses the HtmlFrame with optional width cap) ──
            preview_outer = tk.Frame(win, bg=BODY_DARK)
            preview_outer.pack(expand=True, fill='both', side='top')

            html_frame = tkinterweb.HtmlFrame(preview_outer, messages_enabled=False)
            html_frame.pack(expand=True, fill='both')

            # ── Console panel ──────────────────────────────────────────
            console_frame = tk.Frame(win, bg=CON_BG)
            # not packed yet (hidden by default)

            con_header = tk.Frame(console_frame, bg='#1e293b')
            con_header.pack(fill='x')
            tk.Label(
                con_header, text='CONSOLE',
                bg='#1e293b', fg='#94a3b8',
                font=("Consolas", 9), padx=8, pady=3,
            ).pack(side='left')

            console_log = scrolledtext.ScrolledText(
                console_frame,
                font=("Consolas", 10), bg=CON_BG, fg=CON_FG,
                height=7, bd=0, padx=8, pady=4, wrap='word',
                state='disabled',
            )
            console_log.tag_config('error', foreground='#f87171', background='rgba(220,38,38,0.1)')
            console_log.tag_config('warn',  foreground='#fbbf24')
            console_log.pack(fill='both', expand=True)

            _console_visible = [False]

            def log_to_console(msg, level='log'):
                console_log.config(state='normal')
                tag = 'error' if level == 'error' else ('warn' if level == 'warn' else '')
                console_log.insert(tk.END, msg + '\n', tag)
                console_log.see(tk.END)
                console_log.config(state='disabled')
                # Auto-show console on errors, like chat4
                if level == 'error' and not _console_visible[0]:
                    toggle_console()

            def toggle_console():
                if _console_visible[0]:
                    console_frame.pack_forget()
                    console_btn.config(text='Show Console')
                    _console_visible[0] = False
                else:
                    console_frame.pack(fill='x', side='bottom', before=preview_outer)
                    console_btn.config(text='Hide Console')
                    _console_visible[0] = True

            # ── Render function ──────────────────────────────────────────
            def render(src):
                try:
                    html_frame.load_html(src)
                except Exception as exc:
                    log_to_console(f'Render error: {exc}', 'error')

            render(html_src)

            # ── Desktop / Mobile toggle ─────────────────────────────────
            _view_mode = ['desktop']

            def toggle_view():
                if _view_mode[0] == 'desktop':
                    _view_mode[0] = 'mobile'
                    win.geometry('415x650')
                    device_btn.config(text='Mobile View')
                else:
                    _view_mode[0] = 'desktop'
                    win.geometry('900x650')
                    device_btn.config(text='Desktop View')
                render(html_src)

            # ── Toolbar buttons (right side) ────────────────────────────
            console_btn = tk.Button(toolbar, text='Show Console', command=toggle_console, **_TB_BTN)
            console_btn.pack(side='right', padx=4)

            tk.Button(toolbar, text='Refresh', command=lambda: render(html_src), **_TB_BTN).pack(side='right', padx=4)

            device_btn = tk.Button(toolbar, text='Desktop View', command=toggle_view, **_TB_BTN)
            device_btn.pack(side='right', padx=4)

        def _preview_markdown():
            """Render a Markdown code block as HTML in the default browser."""
            import tempfile
            # Simple markdown → HTML via built-in patterns (no extra deps needed)
            # Falls back to <pre> if markdown2 / mistune not available.
            html_body = None
            for mod_name in ('markdown2', 'mistune', 'markdown'):
                try:
                    if mod_name == 'markdown2':
                        import markdown2
                        html_body = markdown2.markdown(code_text, extras=['fenced-code-blocks', 'tables'])
                    elif mod_name == 'mistune':
                        import mistune
                        html_body = mistune.html(code_text)
                    elif mod_name == 'markdown':
                        import markdown as _md
                        html_body = _md.markdown(code_text, extensions=['fenced_code', 'tables'])
                    break
                except ImportError:
                    continue
            if html_body is None:
                # No markdown library — wrap in <pre>
                html_body = f'<pre>{code_text}</pre>'
            doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<style>
  :root{{color-scheme:dark}}
  body{{margin:0;padding:20px;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
        background:#020617;color:#e2e8f0;max-width:860px;margin:auto}}
  a{{color:#60a5fa}} pre{{overflow-x:auto;padding:12px;border:1px solid rgba(255,255,255,.1);
  border-radius:10px;background:rgba(255,255,255,.04)}}
  code{{font-family:ui-monospace,Consolas,monospace}}
  ul,ol{{padding-left:1.5rem}} table{{border-collapse:collapse}}
  th,td{{border:1px solid rgba(255,255,255,.15);padding:6px 12px}}
</style></head><body>{html_body}</body></html>"""
            with tempfile.NamedTemporaryFile(
                'w', suffix='.html', delete=False, encoding='utf-8'
            ) as f:
                f.write(doc)
                tmp = f.name
            webbrowser.open(f'file:///{tmp}')

        def _preview_svg():
            """Render the SVG visually in a Tkinter window.
            Uses cairosvg if available; falls back to opening in the browser.
            """
            try:
                import cairosvg
                from PIL import Image as _PilImage, ImageTk as _PilImageTk
                import io
                # Render at 2x for crispness on HiDPI
                png_bytes = cairosvg.svg2png(
                    bytestring=code_text.encode('utf-8'), scale=2
                )
                img = _PilImage.open(io.BytesIO(png_bytes))

                win = tk.Toplevel(self.root)
                win.title('Preview — SVG')
                win.configure(bg='#1a1a1a')

                # Fit inside 800×600 while preserving aspect ratio
                MAX_W, MAX_H = 800, 600
                w, h = img.size
                scale = min(MAX_W / w, MAX_H / h, 1.0)
                disp_img = img.resize(
                    (int(w * scale), int(h * scale)),
                    _PilImage.LANCZOS,
                )
                photo = _PilImageTk.PhotoImage(disp_img)

                win.geometry(f"{disp_img.width + 20}x{disp_img.height + 20}")
                canvas = tk.Canvas(
                    win,
                    width=disp_img.width, height=disp_img.height,
                    bg='#1a1a1a', highlightthickness=0,
                )
                canvas.pack(padx=10, pady=10)
                canvas.create_image(0, 0, anchor='nw', image=photo)
                # Keep reference so GC doesn't collect it
                canvas._photo = photo

            except ImportError:
                # cairosvg not installed — fall back to browser
                import tempfile
                with tempfile.NamedTemporaryFile(
                    'w', suffix='.svg', delete=False, encoding='utf-8'
                ) as f:
                    f.write(code_text)
                    tmp = f.name
                webbrowser.open(f'file:///{tmp}')
            except Exception as exc:
                from tkinter import messagebox as _mb
                _mb.showerror('SVG Preview Error', str(exc))

        # ── Buttons (right side of header) ────────────────────────────────
        lang_lower = (language or '').lower()
        if lang_lower in ('html', 'css', 'javascript', 'js', 'python', 'py',
                          'svg', 'xml', 'markdown', 'md', ''):
            preview_btn = tk.Button(header, text='⊙ Preview', command=preview_code, **BTN_CFG)
            preview_btn.pack(side='right', padx=2)

        tk.Button(header, text='⤓ Save', command=save_code, **BTN_CFG).pack(side='right', padx=2)

        copy_btn = tk.Button(header, text='⧉ Copy', command=copy_code, **BTN_CFG)
        copy_btn.pack(side='right', padx=2)

        collapse_btn = tk.Button(header, text='▾', command=toggle_collapse, **BTN_CFG)
        collapse_btn.pack(side='right', padx=(2, 6))

        return container

    def append_message(self, sender, message, tag):
        self.chat_display.config(state='normal')
        if tag == 'user':
            # "You" label right-aligned above the bubble
            self.chat_display.insert(tk.END, f"{sender}\n", 'user')

            # Compute wraplength from current widget width (fallback 450px)
            widget_w = self.chat_display.winfo_width()
            wrap = max(200, (widget_w if widget_w > 1 else 500) - 180)

            # Build bubble widget, then right-align it via computed left padding
            bubble = tk.Frame(self.chat_display, bg='#2563eb', padx=12, pady=6)
            lbl = tk.Label(
                bubble, text=message,
                bg='#2563eb', fg='white',
                font=("Segoe UI", 11),
                wraplength=wrap,
                justify='left',
                anchor='w',
            )
            lbl.pack()
            bubble.update_idletasks()

            right_margin = 10
            bubble_w = bubble.winfo_reqwidth()
            left_pad = max(8, widget_w - bubble_w - right_margin - 24)

            self.chat_display.window_create(tk.END, window=bubble, padx=left_pad, pady=2)
            self.chat_display.insert(tk.END, '\n')
        else:
            self.chat_display.insert(tk.END, f"{sender}\n", tag)
            msg_start = self.chat_display.index(tk.END)
            self.chat_display.insert(tk.END, f"{message}\n", 'content')
            msg_end = self.chat_display.index(tk.END)
            self._tag_emojis_in_range(msg_start, msg_end)
        self.chat_display.see(tk.END)
        self.chat_display.config(state='disabled')

    def append_header(self, sender, tag):
        self.chat_display.config(state='normal')
        start = self.chat_display.index(tk.END)
        self.chat_display.insert(tk.END, f"{sender}\n", tag)
        end = self.chat_display.index(tk.END)
        self._tag_emojis_in_range(start, end)
        self.chat_display.see(tk.END)
        self.chat_display.config(state='disabled')

    def append_token(self, token):
        self.chat_display.config(state='normal')
        self.chat_display.insert(tk.END, token, 'content')
        # Stream chunks can split emoji sequences; rescan a small tail window.
        try:
            tail_start = self.chat_display.index('end-20c')
        except Exception:
            tail_start = '1.0'
        tail_end = self.chat_display.index(tk.END)
        self._tag_emojis_in_range(tail_start, tail_end)
        self.chat_display.see(tk.END)
        self.chat_display.config(state='disabled')

    def append_status(self, label, value, value_tag='status_value'):
        """Append a status line like 'Optimize Search: Yes' to the chat."""
        self.chat_display.config(state='normal')
        start = self.chat_display.index(tk.END)
        self.chat_display.insert(tk.END, f"{label} ", 'status_label')
        self.chat_display.insert(tk.END, f"{value}\n", value_tag)
        end = self.chat_display.index(tk.END)
        self._tag_emojis_in_range(start, end)
        self.chat_display.see(tk.END)
        self.chat_display.config(state='disabled')

    def _ensure_sources_bar(self):
        """Create the sources bar frame if not yet created for this response."""
        if self._current_sources_bar is None:
            frame = tk.Frame(self.chat_display, bg="#2b2b2b", pady=4)
            lbl = tk.Label(frame, text="Sources", bg="#2b2b2b", fg="#666688",
                           font=("Segoe UI", 9, "italic"), padx=4)
            lbl.pack(side='left', padx=(2, 10))
            self.chat_display.config(state='normal')
            self.chat_display.window_create(tk.END, window=frame)
            self.chat_display.insert(tk.END, '\n')
            self.chat_display.see(tk.END)
            self.chat_display.config(state='disabled')
            self._current_sources_bar = frame
        return self._current_sources_bar

    def _add_source_pill(self, number, title, url, favicon_photo=None):
        """Add a single clickable source pill to the sources bar."""
        try:
            frame = self._ensure_sources_bar()

            pill = tk.Frame(frame, bg="#3a3a4a", cursor="hand2", pady=2, padx=6)
            pill.pack(side='left', padx=3)

            num_lbl = tk.Label(pill, text=f"[{number}]", bg="#3a3a4a", fg="#666688",
                               font=("Segoe UI", 8, "bold"))
            num_lbl.pack(side='left', padx=(0, 3))

            if favicon_photo:
                fav_lbl = tk.Label(pill, image=favicon_photo, bg="#3a3a4a", bd=0)
                fav_lbl.pack(side='left', padx=(0, 4))
            else:
                fav_lbl = None

            short = title[:28] + "\u2026" if len(title) > 28 else title
            txt_lbl = tk.Label(pill, text=short, bg="#3a3a4a", fg="#aaaacc",
                               font=("Segoe UI", 9), cursor="hand2")
            txt_lbl.pack(side='left')

            def open_url(e=None, u=url):
                if u and u.startswith('http'):
                    webbrowser.open(u)

            def on_enter(e):
                pill.config(bg="#4a4a6a")
                num_lbl.config(bg="#4a4a6a")
                txt_lbl.config(bg="#4a4a6a")
                if fav_lbl: fav_lbl.config(bg="#4a4a6a")

            def on_leave(e):
                pill.config(bg="#3a3a4a")
                num_lbl.config(bg="#3a3a4a")
                txt_lbl.config(bg="#3a3a4a")
                if fav_lbl: fav_lbl.config(bg="#3a3a4a")

            for widget in [pill, num_lbl, txt_lbl] + ([fav_lbl] if fav_lbl else []):
                widget.bind("<Button-1>", open_url)
                widget.bind("<Enter>", on_enter)
                widget.bind("<Leave>", on_leave)

            self.chat_display.see(tk.END)
        except Exception as e:
            print(f"Error adding source pill: {e}")

    def _ensure_image_row(self):
        """Create the image row frame if it doesn't exist yet for the current response."""
        if self._current_image_row is None:
            frame = tk.Frame(self.chat_display, bg="#363636", pady=6)
            self.chat_display.config(state='normal')
            self.chat_display.window_create(tk.END, window=frame)
            self.chat_display.insert(tk.END, '\n')
            self.chat_display.see(tk.END)
            self.chat_display.config(state='disabled')
            self._current_image_row = frame
        return self._current_image_row

    def _add_image_to_row(self, img_obj, lightbox_img):
        """Add one image to the current horizontal image row as soon as it's ready."""
        try:
            frame = self._ensure_image_row()
            photo = ImageTk.PhotoImage(img_obj)
            self.image_references.append(photo)  # Keep reference to prevent GC
            lbl = tk.Label(frame, image=photo, bg="#363636", bd=0, cursor="hand2")
            lbl.bind("<Button-1>", lambda e, lb=lightbox_img: self.show_lightbox(lb))
            lbl.pack(side='left', padx=3)
            self.chat_display.see(tk.END)
        except Exception as e:
            print(f"Error adding image to row: {e}")

    def show_lightbox(self, img_obj):
        """Show a dimmed full-screen overlay with the image centred on top."""
        # Semi-transparent black overlay
        overlay = tk.Toplevel(self.root)
        overlay.attributes('-fullscreen', True)
        overlay.attributes('-alpha', 0.80)
        overlay.configure(bg='black')
        overlay.attributes('-topmost', True)
        overlay.overrideredirect(True)

        # Image popup centred on screen
        popup = tk.Toplevel(self.root)
        popup.configure(bg='#1a1a2e')
        popup.attributes('-topmost', True)
        popup.overrideredirect(True)  # No title bar

        photo = ImageTk.PhotoImage(img_obj)
        self.image_references.append(photo)

        img_lbl = tk.Label(popup, image=photo, bg='#1a1a2e', bd=0)
        img_lbl.pack(padx=24, pady=24)

        close_hint = tk.Label(popup, text="Click anywhere or press Esc to close",
                              bg='#1a1a2e', fg='#666688', font=("Segoe UI", 9))
        close_hint.pack(pady=(0, 14))

        # Centre the popup using known image dimensions + fixed padding
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        pw = img_obj.width + 48   # 24px left + 24px right padding
        ph = img_obj.height + 62  # 24px top + 24px bottom + ~14px hint label
        x = (sw - pw) // 2
        y = (sh - ph) // 2
        popup.geometry(f"{pw}x{ph}+{x}+{y}")

        def close(e=None):
            overlay.destroy()
            popup.destroy()

        overlay.bind('<Button-1>', close)
        popup.bind('<Button-1>', close)
        overlay.bind('<Escape>', close)
        popup.bind('<Escape>', close)
        popup.focus_force()

    def _get_maps_favicon(self):
        """Fetch and cache the Google Maps favicon (16 x 16 px)."""
        if self._maps_favicon_photo is not None:
            return self._maps_favicon_photo
        try:
            fav_url = "https://www.google.com/s2/favicons?domain=maps.google.com&sz=32"
            resp = requests.get(fav_url, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
            resp.raise_for_status()
            img = Image.open(BytesIO(resp.content)).convert("RGBA")
            img = img.resize((16, 16), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.image_references.append(photo)  # prevent GC
            self._maps_favicon_photo = photo
        except Exception as exc:
            print(f"Could not fetch Maps favicon: {exc}")
            self._maps_favicon_photo = False  # falsy sentinel so we don't retry
        return self._maps_favicon_photo

    def _annotate_addresses(self, full_answer):
        """Scan the just-completed answer for US addresses and add inline Maps buttons."""
        found = _find_addresses(full_answer)
        if not found:
            return

        favicon = self._get_maps_favicon()

        # Collect positions already tagged so multiple responses don't re-annotate
        already_tagged = set()
        idx = '1.0'
        while True:
            tag_range = self.chat_display.tag_nextrange('map_addr', idx)
            if not tag_range:
                break
            already_tagged.add(tag_range[0])
            idx = tag_range[1]

        self.chat_display.config(state='normal')
        try:
            for _s, _e, addr_text in found:
                search_from = '1.0'
                while True:
                    pos = self.chat_display.search(
                        addr_text, search_from, stopindex=tk.END, exact=True
                    )
                    if not pos:
                        break
                    end_pos = f"{pos}+{len(addr_text)}c"
                    search_from = end_pos
                    if pos in already_tagged:
                        continue

                    # Highlight the address text
                    self.chat_display.tag_add('map_addr', pos, end_pos)
                    already_tagged.add(pos)

                    # Unique tag so we can bind a click to this specific address
                    uid = getattr(self, '_map_addr_counter', 0)
                    self._map_addr_counter = uid + 1
                    click_tag = f'map_addr_click_{uid}'
                    self.chat_display.tag_add(click_tag, pos, end_pos)
                    self.chat_display.tag_config(click_tag, foreground='#60a5fa', underline=True)

                    def _open(e=None, a=addr_text):
                        webbrowser.open(
                            f"https://www.google.com/maps/search/?api=1&query={quote(a)}"
                        )

                    self.chat_display.tag_bind(click_tag, '<Button-1>', _open)
                    self.chat_display.tag_bind(click_tag, '<Enter>',
                        lambda e: self.chat_display.config(cursor='hand2'))
                    self.chat_display.tag_bind(click_tag, '<Leave>',
                        lambda e: self.chat_display.config(cursor=''))

                    # Build the inline icon button
                    btn = tk.Frame(self.chat_display, bg='#363636', cursor='hand2', bd=0)
                    if favicon:
                        icon = tk.Label(btn, image=favicon, bg='#363636', bd=0, cursor='hand2')
                    else:
                        icon = tk.Label(btn, text='\U0001f4cd', bg='#363636', bd=0,
                                        cursor='hand2', font=("Segoe UI", 9))
                    icon.pack(side='left')

                    btn.bind('<Button-1>', _open)
                    icon.bind('<Button-1>', _open)

                    self.chat_display.window_create(end_pos, window=btn, pady=1)
        finally:
            self.chat_display.config(state='disabled')

    def _inject_inline_citations(self, sources):
        """Find every [N] marker in the chat widget and make it a clickable
        hyperlink.  Already-tagged markers (from previous responses) are
        detected by the presence of a _cite_click_* tag and skipped."""
        if not sources:
            return

        # Build number -> URL lookup
        url_map = {}
        for i, src in enumerate(sources):
            url = src.get('href', '') or src.get('url', '') or src.get('link', '')
            if url:
                url_map[i + 1] = url

        if not url_map:
            return

        self.chat_display.config(state='normal')
        try:
            for n, url in url_map.items():
                marker = f'[{n}]'
                search_from = '1.0'
                while True:
                    pos = self.chat_display.search(
                        marker, search_from, stopindex=tk.END, exact=True
                    )
                    if not pos:
                        break
                    end_pos = f'{pos}+{len(marker)}c'
                    search_from = end_pos

                    # Skip markers that were already hyperlinked by a previous response
                    if any(t.startswith('_cite_click_') for t in self.chat_display.tag_names(pos)):
                        continue

                    # Unique click tag — tag_config on it wins over the 'content' tag
                    uid = getattr(self, '_cite_counter', 0)
                    self._cite_counter = uid + 1
                    click_tag = f'_cite_click_{uid}'
                    self.chat_display.tag_add(click_tag, pos, end_pos)
                    self.chat_display.tag_config(
                        click_tag,
                        foreground='#7dd3fc',
                        underline=True,
                        font=("Segoe UI", 8, "bold"),
                    )

                    def _open(e=None, u=url):
                        webbrowser.open(u)

                    self.chat_display.tag_bind(click_tag, '<Button-1>', _open)
                    self.chat_display.tag_bind(click_tag, '<Enter>',
                        lambda e: self.chat_display.config(cursor='hand2'))
                    self.chat_display.tag_bind(click_tag, '<Leave>',
                        lambda e: self.chat_display.config(cursor=''))
        finally:
            self.chat_display.config(state='disabled')

    def _append_tagged(self, text, tag):
        """Append text with a specific tag."""
        self.chat_display.config(state='normal')
        self.chat_display.insert(tk.END, text, tag)
        self.chat_display.see(tk.END)
        self.chat_display.config(state='disabled')

    def update_status(self, text):
        self.status_label.config(text=text)

    def start_search(self):
        query = self.input_field.get().strip()
        if not query:
            return

        self.input_field.delete(0, tk.END)
        self.append_message("You", query, 'user')
        self.update_status("Processing...")
        self.send_button.config(state='disabled')

        # Detect YouTube URL — video_id is passed into the unified process_query
        _, yt_id = _extract_youtube_video_id(query)

        # Format history according to user rules: last 3 messages, truncated if > 300 chars
        formatted_history = ""
        recent_history = self.history[-3:]
        for role, content in recent_history:
            if len(content) > 300:
                truncated = f"{content[:300]}...{content[-300:]}"
            else:
                truncated = content
            formatted_history += f"{role}: {truncated}\n"

        # Single code path for everything — video_id=None means no transcript fetch
        threading.Thread(target=self.process_query, args=(query, formatted_history), kwargs={'video_id': yt_id}, daemon=True).start()

    def process_query(self, query, history_string, video_id=None):
        full_answer = ""
        transcript = None
        try:
            self.root.after(0, lambda: self.append_header("AI Assistant", 'ai'))

            # If a YouTube video was detected, fetch transcript first
            if video_id:
                self.root.after(0, lambda: self.append_status("YouTube:", "Fetching transcript...", 'status_searching'))
                self.root.after(0, lambda: self.update_status("Fetching YouTube transcript..."))
                raw_transcript, lang_or_err = get_youtube_transcript(video_id)
                if raw_transcript is None:
                    self.root.after(0, lambda e=lang_or_err: self.append_status(
                        "YouTube:", f"No transcript available — {e}", 'status_warning'))
                else:
                    words = raw_transcript.split()
                    if len(words) > 3000:
                        raw_transcript = ' '.join(words[:3000]) + '\n[Transcript truncated]'
                    word_count = len(raw_transcript.split())
                    self.root.after(0, lambda wc=word_count: self.append_status(
                        "Transcript:", f"Fetched ({wc:,} words)", 'status_yes'))
                    transcript = raw_transcript
                    # Pre-seed sources bar with the YouTube video as source [1]
                    yt_full_url = f"https://www.youtube.com/watch?v={video_id}"
                    self._pending_sources = [{'href': yt_full_url, 'title': f'YouTube Video ({video_id})'}]

            for chunk in get_combined_response_stream(query, history=history_string, transcript=transcript):
                if isinstance(chunk, dict):
                    status = chunk.get('status')
                    
                    if status == 'checking_search':
                        self.root.after(0, lambda: self.update_status("Checking if search is needed..."))
                    
                    elif status == 'search_decision':
                        needs = chunk['needs_search']
                        if needs:
                            self.root.after(0, lambda: self.append_status("Internet Search:", "Yes", 'status_yes'))
                        else:
                            self.root.after(0, lambda: self.append_status("Internet Search:", "No — answering directly", 'status_no'))
                    
                    elif status == 'analyzing':
                        self.root.after(0, lambda: self.update_status("Analyzing query..."))
                    
                    elif status == 'optimize_result':
                        optimized = chunk['optimized']
                        queries = chunk['queries']
                        if optimized:
                            self.root.after(0, lambda: self.append_status("Optimize Search:", "Yes", 'status_yes'))
                            for q in queries:
                                self.root.after(0, lambda q=q: self.append_status("  •", q, 'status_bullet'))
                        else:
                            self.root.after(0, lambda: self.append_status("Optimize Search:", "No", 'status_no'))
                    
                    elif status == 'searching':
                        self.root.after(0, lambda: self.append_status("", "Searching web...", 'status_searching'))
                        self.root.after(0, lambda: self.update_status("Searching the web..."))
                    
                    elif status == 'search_done':
                        count = chunk['count']
                        top_n = chunk.get('top_n', 3)
                        source = chunk.get('source', 'unknown')
                        errors = chunk.get('errors', set())
                        self.root.after(0, lambda c=count, n=top_n, s=source: self.append_status(
                            f"Results:", f"{c} fetched · {n} sent to model", 'status_value'
                        ))
                        if 'ratelimit' in errors:
                            self.root.after(0, lambda: self.append_status("  ⚠", "Rate limited — some results may be missing", 'status_warning'))
                        if 'timeout' in errors:
                            self.root.after(0, lambda: self.append_status("  ⏱", "Some searches timed out", 'status_warning'))
                        self._pending_sources = self._pending_sources + chunk.get('top_results', [])
                    
                    elif status == 'answering':
                        def _insert_thoughts_placeholder():
                            self.chat_display.config(state='normal')
                            # Insert Thoughts header + placeholder immediately
                            self.chat_display.insert(tk.END, 'Thoughts:\n', 'think_header')
                            self.chat_display.mark_set('thoughts_ph_start', 'end-1c')
                            self.chat_display.mark_gravity('thoughts_ph_start', 'left')
                            self.chat_display.insert(tk.END, '...\n', 'think')
                            self.chat_display.mark_set('thoughts_ph_end', 'end-1c')
                            self.chat_display.mark_gravity('thoughts_ph_end', 'left')
                            self.chat_display.see(tk.END)
                            self.chat_display.config(state='disabled')
                        self.root.after(0, _insert_thoughts_placeholder)
                        self.root.after(0, lambda: self.append_status("", "", 'status_label'))  # blank line
                        self.root.after(0, lambda: self.append_status("Answer:", "", 'status_label'))
                        self.root.after(0, lambda: self.update_status("Generating answer..."))
                        # Record start position (at the end after "Answer:\n")
                        def _set_start():
                            self._ai_response_start = self.chat_display.index('end-1c')
                        self.root.after(0, _set_start)

                    # Note: 'rewriting_citations' and 'rewritten_answer' statuses removed
                    # Citations are now generated in single-pass streaming
                else:
                    # Regular answer token
                    full_answer += chunk
                    self.root.after(0, lambda c=chunk: self.append_token(c))
            
            # --- POST-STREAM FORMATTING AND ANNOTATIONS ---
            def _post_process():
                import re as _re
                ai_end = self.chat_display.index(tk.END)
                if hasattr(self, '_ai_response_start'):
                    self._format_markdown(self._ai_response_start, ai_end)

                # Replace the '...' placeholder with real thoughts content
                think_match = _re.search(r'<think>([\s\S]*?)(?:</think>|$)', full_answer, _re.IGNORECASE)
                thoughts_text = think_match.group(1).strip() if think_match else None
                marks = self.chat_display.mark_names()
                if 'thoughts_ph_start' in marks and 'thoughts_ph_end' in marks:
                    self.chat_display.config(state='normal')
                    self.chat_display.delete('thoughts_ph_start', 'thoughts_ph_end')
                    replacement = (thoughts_text + '\n') if thoughts_text else 'N/A\n'
                    self.chat_display.insert('thoughts_ph_start', replacement, 'think')
                    self.chat_display.config(state='disabled')

                # Original annotation logic follows
                self._annotate_addresses(full_answer)
                self._inject_inline_citations(pending_sources)

            # Add a final newline for spacing and update history
            self.root.after(0, lambda: self.append_token("\n"))
            self.history.append(("User", query))
            self.history.append(("Assistant", full_answer))

            # --- ANNOTATE ADDRESSES (Moved to post_process) ---
            # self.root.after(0, lambda fa=full_answer: self._annotate_addresses(fa))

            # --- FETCH AND DISPLAY IMAGES ---
            self.root.after(0, lambda: self.update_status("Finding relevant images..."))
            image_keywords = get_image_keywords(query, full_answer)

            # Reset row/sources so each response gets a fresh set
            self._current_image_row = None
            self._current_sources_bar = None
            pending_sources = self._pending_sources
            self._pending_sources = []

            # Deduplicate sources
            seen_urls = set()
            deduped_sources = []
            for r in pending_sources:
                url = r.get('href', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    deduped_sources.append(r)
            pending_sources = deduped_sources

            # Call the new post-process function
            self.root.after(0, _post_process)

            if image_keywords:
                all_image_urls = fetch_images_for_keywords(image_keywords, candidates_per_keyword=5)

                # Load images progressively — each appears in the row as soon as it downloads
                for kw in image_keywords:
                    urls = all_image_urls.get(kw, [])
                    success_count = 0
                    for url in urls:
                        if success_count >= 3:
                            break
                        result = download_and_process_image(url, max_size=(130, 90))
                        if result:
                            thumb, lightbox = result
                            self.root.after(0, lambda t=thumb, lb=lightbox: self._add_image_to_row(t, lb))
                            success_count += 1

                self.root.after(0, lambda: self.append_token("\n"))

            # --- RENDER SOURCES BAR ---
            for i, r in enumerate(pending_sources):
                url = r.get('href', '')
                title = r.get('title', '') or url
                number = i + 1
                favicon_photo = None
                if url.startswith('http'):
                    try:
                        hostname = urlparse(url).netloc
                        fav_url = f"https://www.google.com/s2/favicons?domain={hostname}&sz=32"
                        fav_resp = requests.get(fav_url, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
                        fav_resp.raise_for_status()
                        fav_img = Image.open(BytesIO(fav_resp.content)).convert("RGBA")
                        fav_img = fav_img.resize((14, 14), Image.Resampling.LANCZOS)
                        favicon_photo = ImageTk.PhotoImage(fav_img)
                        self.image_references.append(favicon_photo)
                    except Exception:
                        pass
                self.root.after(0, lambda n=number, ti=title, u=url, fp=favicon_photo:
                                self._add_source_pill(n, ti, u, fp))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.root.after(0, lambda: self.update_status("Ready"))
            self.root.after(0, lambda: self.send_button.config(state='normal'))

if __name__ == "__main__":
    root = tk.Tk()
    app = SearchApp(root)
    root.mainloop()
