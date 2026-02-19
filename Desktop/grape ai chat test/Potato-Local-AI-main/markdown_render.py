"""markdown_render.py
Extra markdown rendering passes used by gui_app.py.

Handles:
  - # / ## / ### headings
  - --- / *** / ___ horizontal rules

Kept in a separate file so gui_app.py stays manageable.
"""

import re
import tkinter as tk


# ---------------------------------------------------------------------------
# Tag registration
# ---------------------------------------------------------------------------

def register_heading_hr_tags(chat_display: tk.Text) -> None:
    """Register Tkinter text tags for h1/h2/h3 headings and horizontal rules.
    Call this once after the chat_display widget is created (in __init__)."""
    chat_display.tag_config(
        'h1',
        font=("Segoe UI", 18, "bold"),
        foreground='#ffffff',
        spacing1=14,
        spacing3=6,
    )
    chat_display.tag_config(
        'h2',
        font=("Segoe UI", 15, "bold"),
        foreground='#e8e8e8',
        spacing1=11,
        spacing3=4,
    )
    chat_display.tag_config(
        'h3',
        font=("Segoe UI", 13, "bold"),
        foreground='#c8c8c8',
        spacing1=9,
        spacing3=3,
    )
    # 'hr' tag is not used directly on text — the rule is an embedded widget —
    # but we register it so other code can query it without KeyError.
    chat_display.tag_config('hr', spacing1=4, spacing3=4)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _char_offset_to_idx(raw: str, offset: int, sp_line: int, sp_col: int) -> str:
    """Convert a character offset in *raw* into a Tkinter 'line.col' index.

    *sp_line* / *sp_col* are the line/column of raw[0] inside the widget.
    Only valid when applied right-to-left (so earlier deletions do not shift
    positions used later)."""
    before   = raw[:offset]
    nl_count = before.count('\n')
    last_nl  = before.rfind('\n')
    col      = offset - (last_nl + 1)
    if nl_count == 0:
        return f"{sp_line}.{sp_col + col}"
    return f"{sp_line + nl_count}.{col}"


# ---------------------------------------------------------------------------
# Heading pass
# ---------------------------------------------------------------------------

def apply_headings(chat_display: tk.Text, start_pos: str) -> None:
    """Detect # / ## / ### at the start of lines, strip the marker, and apply
    the matching heading tag over the remaining content.

    Only the '## ' prefix is deleted so any existing bold/italic sub-tags on
    the rest of the line are preserved.  The heading tag is then added to
    cover the whole content portion.

    Must be called while chat_display is in 'normal' (editable) state.
    Processes matches in reverse order so deletions never shift later offsets.
    """
    raw = chat_display.get(start_pos, tk.END)
    sp_line, sp_col = map(int, chat_display.index(start_pos).split('.'))

    # Match the leading hashes + space; content captured in group 2
    heading_re = re.compile(r'^(#{1,3} +)', re.MULTILINE)
    matches = list(heading_re.finditer(raw))

    for m in reversed(matches):
        prefix      = m.group(1)          # e.g. "## "
        level       = prefix.count('#')   # 1, 2 or 3
        tag         = f'h{level}'

        # Position of the prefix
        prefix_start = _char_offset_to_idx(raw, m.start(), sp_line, sp_col)
        prefix_end   = _char_offset_to_idx(raw, m.end(),   sp_line, sp_col)

        # End of the line (content after the prefix)
        line_end_str = chat_display.index(f"{prefix_start} lineend")

        # 1. Delete just the "## " prefix
        chat_display.delete(prefix_start, prefix_end)

        # 2. Apply heading tag from where the prefix was to end of the line
        #    (prefix_start now points at the first content char after deletion)
        chat_display.tag_add(tag, prefix_start, line_end_str)


# ---------------------------------------------------------------------------
# Horizontal-rule pass
# ---------------------------------------------------------------------------

def _make_hr_widget(chat_display: tk.Text) -> tk.Canvas:
    """Return a Canvas that draws a 1-px horizontal rule."""
    bg = chat_display.cget('bg')
    c = tk.Canvas(chat_display, height=12, bg=bg, highlightthickness=0, bd=0)
    # Draw at y=6 so there's a little breathing room above/below
    c.create_line(0, 6, 4000, 6, fill='#555555', width=1)
    return c


def apply_horizontal_rules(chat_display: tk.Text, start_pos: str) -> None:
    """Replace standalone --- / *** / ___ lines with an embedded Canvas divider.

    Must be called while chat_display is in 'normal' (editable) state.
    Processes matches in reverse order so deletions never shift later offsets.
    """
    raw = chat_display.get(start_pos, tk.END)
    sp_line, sp_col = map(int, chat_display.index(start_pos).split('.'))

    hr_re = re.compile(r'^[ \t]*(-{3,}|\*{3,}|_{3,})[ \t]*$', re.MULTILINE)
    matches = list(hr_re.finditer(raw))

    for m in reversed(matches):
        idx_start = _char_offset_to_idx(raw, m.start(), sp_line, sp_col)
        idx_end   = _char_offset_to_idx(raw, m.end(),   sp_line, sp_col)

        widget = _make_hr_widget(chat_display)
        chat_display.delete(idx_start, idx_end)
        # stretch=True makes the canvas expand to fill the text widget's width
        chat_display.window_create(idx_start, window=widget, stretch=True)
