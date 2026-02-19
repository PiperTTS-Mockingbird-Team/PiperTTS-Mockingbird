"""
Quick visual test for citation hyperlinks.
Run this script — a small window will appear with text containing [1] and [2].
They should appear blue + underlined and open a browser when clicked.
"""
import tkinter as tk
from tkinter import scrolledtext
import webbrowser

FAKE_SOURCES = [
    {'href': 'https://www.example.com/source1', 'title': 'Example Source 1'},
    {'href': 'https://www.wikipedia.org/',       'title': 'Wikipedia'},
]

FAKE_ANSWER = (
    "Key lime pie is a delicious dessert [1]. "
    "It originated in the Florida Keys and is well documented [2]. "
    "Some recipes also call for a graham cracker crust [1]."
)


def inject_citations(widget, sources, answer_start='1.0'):
    url_map = {}
    for i, src in enumerate(sources):
        url = src.get('href', '') or src.get('url', '') or src.get('link', '')
        if url:
            url_map[i + 1] = url

    if not url_map:
        print("No URLs found in sources!")
        return

    counter = [0]

    widget.config(state='normal')
    try:
        for n, url in url_map.items():
            marker = f'[{n}]'
            search_from = answer_start
            found_any = False
            while True:
                pos = widget.search(marker, search_from, stopindex=tk.END, exact=True)
                if not pos:
                    break
                found_any = True
                end_pos = f'{pos}+{len(marker)}c'
                search_from = end_pos

                # Shared base tag
                widget.tag_add('cite_link', pos, end_pos)

                # Unique click tag with its own tag_config (same trick as map addresses)
                uid = counter[0]
                counter[0] += 1
                click_tag = f'_cite_click_{uid}'
                widget.tag_add(click_tag, pos, end_pos)
                widget.tag_config(
                    click_tag,
                    foreground='#7dd3fc',
                    underline=True,
                    font=("Segoe UI", 8, "bold"),
                )

                def _open(e=None, u=url):
                    print(f"Opening: {u}")
                    webbrowser.open(u)

                widget.tag_bind(click_tag, '<Button-1>', _open)
                widget.tag_bind(click_tag, '<Enter>',
                    lambda e: widget.config(cursor='hand2'))
                widget.tag_bind(click_tag, '<Leave>',
                    lambda e: widget.config(cursor=''))

                print(f"  Tagged [{n}] at {pos}..{end_pos} -> {url}")

            if not found_any:
                print(f"  WARNING: [{n}] not found in text!")
    finally:
        widget.config(state='disabled')


root = tk.Tk()
root.title("Citation Hyperlink Test")
root.geometry("600x300")
root.configure(bg="#2b2b2b")

widget = scrolledtext.ScrolledText(
    root, wrap=tk.WORD, state='disabled',
    font=("Segoe UI", 11),
    bg="#363636", fg="#e0e0e0",
    padx=10, pady=10
)
widget.pack(expand=True, fill='both', padx=10, pady=10)

# Configure shared tag (style is actually applied per click_tag below)
widget.tag_config('cite_link', foreground='#7dd3fc', underline=True,
                  font=("Segoe UI", 8, "bold"))

# Insert content tag so it matches app conditions
widget.tag_config('content', foreground='#e0e0e0')

widget.config(state='normal')
widget.insert(tk.END, FAKE_ANSWER, 'content')
widget.config(state='disabled')

print("Injecting citations...")
inject_citations(widget, FAKE_SOURCES, answer_start='1.0')
print("Done. [1] and [2] should be blue + underlined and clickable.")

root.mainloop()
