import tkinter as tk
from tkinter import scrolledtext, filedialog


PY_SAMPLE = """# demo: python highlighting via Tk tags

import os

class Greeter:
    def __init__(self, name: str):
        self.name = name

    def greet(self) -> str:
        msg = f\"Hello, {self.name}!\"
        print(msg)
        return msg

if __name__ == '__main__':
    Greeter('Robert').greet()
"""


def _apply_demo_tags(text: tk.Text):
    """Very small, manual highlighter to prove multi-color rendering works."""
    # VS Code-ish colors
    colors = {
        'kw': '#569cd6',       # keywords
        'type': '#4ec9b0',     # class names / types
        'str': '#ce9178',      # strings
        'com': '#6a9955',      # comments
        'num': '#b5cea8',      # numbers
        'func': '#dcdcaa',     # function names
    }

    for tag, color in colors.items():
        text.tag_config(tag, foreground=color)

    src = text.get('1.0', 'end-1c')

    # Comments (entire line after '#')
    for line_idx, line in enumerate(src.splitlines(), start=1):
        hash_pos = line.find('#')
        if hash_pos != -1:
            start = f"{line_idx}.{hash_pos}"
            end = f"{line_idx}.end"
            text.tag_add('com', start, end)

    # Strings (simple quotes + double quotes; demo-level only)
    # Apply from left to right, non-greedy-ish; good enough for a visual test.
    def color_simple_strings(quote_char: str):
        import re
        pattern = re.compile(re.escape(quote_char) + r"([^\\" + quote_char + r"\\]|\\.)*" + re.escape(quote_char))
        for m in pattern.finditer(src):
            s = m.start()
            e = m.end()
            start = f"1.0+{s}c"
            end = f"1.0+{e}c"
            text.tag_add('str', start, end)

    color_simple_strings("'")
    color_simple_strings('"')

    # Keywords (very small set)
    import re
    for kw in [
        'import', 'from', 'class', 'def', 'return', 'if', 'else', 'elif',
        'for', 'while', 'try', 'except', 'as', 'with', 'pass', 'print',
    ]:
        for m in re.finditer(rf"\b{re.escape(kw)}\b", src):
            text.tag_add('kw', f"1.0+{m.start()}c", f"1.0+{m.end()}c")

    # Class name after "class "
    for m in re.finditer(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", src):
        name = m.group(1)
        name_start = m.start(1)
        name_end = m.end(1)
        text.tag_add('type', f"1.0+{name_start}c", f"1.0+{name_end}c")

    # Function name after "def "
    for m in re.finditer(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)", src):
        name_start = m.start(1)
        name_end = m.end(1)
        text.tag_add('func', f"1.0+{name_start}c", f"1.0+{name_end}c")

    # Numbers
    for m in re.finditer(r"\b\d+\b", src):
        text.tag_add('num', f"1.0+{m.start()}c", f"1.0+{m.end()}c")


def _create_embedded_code_block(parent, language: str, code_text: str):
    """Create a widget that visually matches the in-chat code block UI."""
    HEADER_BG = '#2d2d2d'
    BODY_BG = '#1a1a1a'
    BORDER_CLR = '#444444'

    BTN_CFG = dict(
        bg=HEADER_BG,
        fg='#cccccc',
        font=("Segoe UI", 9),
        bd=0,
        relief='flat',
        cursor='hand2',
        padx=6,
        pady=3,
        activebackground='#3d3d3d',
        activeforeground='white',
    )

    container = tk.Frame(
        parent,
        bg=BODY_BG,
        highlightbackground=BORDER_CLR,
        highlightthickness=1,
    )

    header = tk.Frame(container, bg=HEADER_BG)
    header.pack(fill='x', side='top')

    lang_display = language or 'code'
    tk.Label(
        header,
        text=lang_display,
        bg=HEADER_BG,
        fg='#888888',
        font=("Segoe UI", 9, 'italic'),
        padx=8,
    ).pack(side='left')

    body_frame = tk.Frame(container, bg=BODY_BG)
    body_frame.pack(fill='x', side='top')

    # Horiz scrollbar like the real widget
    h_scroll = tk.Scrollbar(body_frame, orient='horizontal')
    code_widget = tk.Text(
        body_frame,
        font=("Consolas", 10),
        bg=BODY_BG,
        fg='#d4d4d4',
        insertbackground='white',
        wrap='none',
        bd=0,
        padx=10,
        pady=8,
        height=max(2, min(len(code_text.splitlines()) or 1, 16)),
        xscrollcommand=h_scroll.set,
        state='normal',
    )
    code_widget.insert('1.0', code_text.rstrip())
    _apply_demo_tags(code_widget)
    code_widget.config(state='disabled')
    h_scroll.config(command=code_widget.xview)

    code_widget.pack(fill='x', side='top')
    h_scroll.pack(fill='x', side='top')

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
        # Works even if the widget is embedded
        container.clipboard_clear()
        container.clipboard_append(code_text)
        copy_btn.config(text='✔ Copied')
        container.after(1200, lambda: copy_btn.config(text='⧉ Copy'))

    def save_code():
        ext = '.py' if (language or '').lower() in ('python', 'py') else '.txt'
        path = filedialog.asksaveasfilename(
            defaultextension=ext,
            initialfile=f'code{ext}',
            filetypes=[('All files', '*.*')],
        )
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(code_text)

    def preview_code():
        win = tk.Toplevel(container)
        win.title(f'Preview — {lang_display}')
        win.configure(bg=BODY_BG)
        win.geometry('700x500')
        txt = scrolledtext.ScrolledText(
            win,
            font=("Consolas", 11),
            bg=BODY_BG,
            fg='#d4d4d4',
            wrap='word',
            bd=0,
            padx=12,
            pady=12,
        )
        txt.pack(expand=True, fill='both')
        txt.insert('1.0', code_text)
        txt.config(state='disabled')

    # Buttons (right side)
    tk.Button(header, text='⊙ Preview', command=preview_code, **BTN_CFG).pack(side='right', padx=2)
    tk.Button(header, text='⤓ Save', command=save_code, **BTN_CFG).pack(side='right', padx=2)
    copy_btn = tk.Button(header, text='⧉ Copy', command=copy_code, **BTN_CFG)
    copy_btn.pack(side='right', padx=2)
    collapse_btn = tk.Button(header, text='▾', command=toggle_collapse, **BTN_CFG)
    collapse_btn.pack(side='right', padx=(2, 6))

    return container


def main():
    root = tk.Tk()
    root.title('Prototype — Embedded Chat Code Block Colors')
    root.configure(bg='#1e1e1e')
    root.geometry('950x700')

    # Chat box like the app
    chat = scrolledtext.ScrolledText(
        root,
        wrap=tk.WORD,
        state='disabled',
        font=("Segoe UI", 11),
        bg="#363636",
        fg="#e0e0e0",
        insertbackground="white",
        bd=0,
        padx=10,
        pady=10,
    )
    chat.pack(expand=True, fill='both', padx=16, pady=16)

    chat.config(state='normal')
    chat.insert(tk.END, "AI\n", ('ai',))
    chat.insert(tk.END, "Here is a code block embedded inside the chat widget:\n\n", ('content',))

    # Embed the code block widget exactly like gui_app does
    code_block = _create_embedded_code_block(chat, 'python', PY_SAMPLE)
    chat.window_create(tk.END, window=code_block)
    chat.insert(tk.END, "\n\nMore text after the code block.\n", ('content',))
    chat.config(state='disabled')

    # Keep a reference so Tk doesn't GC embedded widgets
    chat._embedded = [code_block]

    root.mainloop()


if __name__ == '__main__':
    main()
