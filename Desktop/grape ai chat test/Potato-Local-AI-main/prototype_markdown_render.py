"""prototype_markdown_render.py
Standalone test window for heading + horizontal-rule rendering.
Run:  python prototype_markdown_render.py
"""

import tkinter as tk
from markdown_render import register_heading_hr_tags, apply_headings, apply_horizontal_rules

SAMPLE = """\
### Key Terms

• CSS Animation
• Keyframes
• JavaScript
• Spinner
• Text Overlay

---

### Code Example

Here is some inline explanation text followed by more content.

## Section Two

This is a second-level heading above a divider.

---

# Big Heading

Regular body text underneath a top-level heading.

*** 

### Another H3

___ 

Done.
"""

def render(chat: tk.Text) -> None:
    chat.config(state='normal')
    chat.delete('1.0', tk.END)
    chat.insert(tk.END, SAMPLE, 'content')

    start = '1.0'
    apply_headings(chat, start)
    apply_horizontal_rules(chat, start)

    chat.config(state='disabled')


def main() -> None:
    root = tk.Tk()
    root.title('Markdown Render — Prototype')
    root.configure(bg='#1e1e1e')
    root.geometry('620x600')

    chat = tk.Text(
        root,
        bg='#1e1e1e', fg='#e0e0e0',
        font=('Segoe UI', 11),
        wrap='word',
        bd=0,
        padx=18, pady=14,
        state='disabled',
    )
    chat.pack(fill='both', expand=True, padx=10, pady=10)

    # Register all tags (same call used by gui_app)
    register_heading_hr_tags(chat)
    chat.tag_config('content', foreground='#e0e0e0')

    btn = tk.Button(
        root, text='Re-render',
        bg='#2d2d2d', fg='#cccccc',
        font=('Segoe UI', 10),
        relief='flat', cursor='hand2',
        command=lambda: render(chat),
    )
    btn.pack(pady=(0, 10))

    render(chat)
    root.mainloop()


if __name__ == '__main__':
    main()
