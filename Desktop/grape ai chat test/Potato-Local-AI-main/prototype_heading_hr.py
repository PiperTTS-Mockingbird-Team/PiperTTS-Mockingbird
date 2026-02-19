"""prototype_heading_hr.py
Standalone test window for heading and horizontal-rule rendering.
Run directly:  python prototype_heading_hr.py
"""
import re
import tkinter as tk
from markdown_render import register_heading_hr_tags, apply_headings, apply_horizontal_rules

SAMPLE = """\
# Big Heading H1

Some normal paragraph text after H1.

---

## **Medium Heading H2 with bold**

Another block of body text here with **bold words** and *italic* inline.

---

### Small Heading H3

Last paragraph. Ending with more rules.

***

Normal text after triple-star rule.

___

Normal text after underscore rule.
"""


def build():
    root = tk.Tk()
    root.title("Heading / HR prototype")
    root.configure(bg="#1e1e1e")
    root.geometry("700x520")

    chat = tk.Text(
        root,
        bg="#1e1e1e", fg="#e0e0e0",
        font=("Segoe UI", 11),
        wrap="word", padx=16, pady=12,
        relief="flat", bd=0,
    )
    chat.pack(fill="both", expand=True, padx=10, pady=10)

    # Register tags
    register_heading_hr_tags(chat)
    chat.tag_config('bold', font=("Segoe UI", 11, "bold"))
    chat.tag_config('italic', font=("Segoe UI", 11, "italic"))

    # Insert the raw sample text
    chat.insert("1.0", SAMPLE)

    # Simulate what gui_app does: bold/italic first, THEN headings + HR
    chat.config(state="normal")

    # --- mini bold pass (mirrors gui_app Priority 3) ---
    raw = chat.get("1.0", tk.END)
    for m in reversed(list(re.finditer(r'\*\*(.+?)\*\*', raw, re.DOTALL))):
        before   = raw[:m.start()]
        nl       = before.count('\n')
        col      = m.start() - (before.rfind('\n') + 1)
        s_idx    = f"{1 + nl}.{col}"
        before_e = raw[:m.end()]
        nl_e     = before_e.count('\n')
        col_e    = m.end() - (before_e.rfind('\n') + 1)
        e_idx    = f"{1 + nl_e}.{col_e}"
        chat.delete(s_idx, e_idx)
        chat.insert(s_idx, m.group(1), 'bold')

    # --- headings + HR ---
    apply_headings(chat, "1.0")
    apply_horizontal_rules(chat, "1.0")

    chat.config(state="disabled")

    root.mainloop()


if __name__ == "__main__":
    build()
