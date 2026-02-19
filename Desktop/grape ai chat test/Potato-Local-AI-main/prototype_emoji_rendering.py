import tkinter as tk
from tkinter import scrolledtext
from tkinter import font as tkfont


def tag_emojis_in_widget(text_widget: tk.Text, start_idx: str, end_idx: str, tag_name: str = "emoji"):
    """Apply `tag_name` to emoji-ish characters within [start_idx, end_idx)."""
    try:
        text = text_widget.get(start_idx, end_idx)
    except Exception:
        return

    if not text:
        return

    # Quick precheck
    if not any(ord(ch) >= 0x2000 for ch in text):
        return

    def is_emojiish_char(ch: str) -> bool:
        cp = ord(ch)
        # ZWJ and variation selectors commonly appear inside emoji sequences.
        if cp in (0x200D, 0xFE0F):
            return True
        # Regional indicators (flags)
        if 0x1F1E6 <= cp <= 0x1F1FF:
            return True
        # Misc symbols + dingbats (many render as emoji in modern fonts)
        if 0x2600 <= cp <= 0x27BF:
            return True
        # Main emoji blocks
        if 0x1F300 <= cp <= 0x1FAFF:
            return True
        # Supplemental symbols & pictographs-like
        if 0x2300 <= cp <= 0x23FF:
            return True
        return False

    in_run = False
    run_start = 0
    for i, ch in enumerate(text):
        if is_emojiish_char(ch):
            if not in_run:
                in_run = True
                run_start = i
        else:
            if in_run:
                text_widget.tag_add(tag_name, f"{start_idx}+{run_start}c", f"{start_idx}+{i}c")
                in_run = False

    if in_run:
        text_widget.tag_add(tag_name, f"{start_idx}+{run_start}c", f"{start_idx}+{len(text)}c")

    try:
        text_widget.tag_raise(tag_name)
    except Exception:
        pass


SAMPLES = [
    "Basic: 🙂 😂 😭 🥹 🤖 🚀 ✅ ❌",
    "Hearts/VS16: ❤️ ♥️ 💜",
    "Flags: 🇺🇸 🇬🇧 🇨🇦 🇯🇵",
    "ZWJ family: 👨‍👩‍👧‍👦  |  woman technologist: 👩‍💻",
    "Skin tones: 👍 👍🏽 👍🏿",
    "Symbols: ☑️ ☕ ✈️ ⚠️",
]


def main():
    root = tk.Tk()
    root.title("Emoji Rendering Prototype")
    root.geometry("900x650")

    # Fonts that commonly exist on Windows.
    emoji_font_candidates = [
        "Segoe UI Emoji",
        "Segoe UI Symbol",
        "Apple Color Emoji",
        "Noto Color Emoji",
        "Twemoji Mozilla",
        "EmojiOne Color",
    ]

    available_fonts = set(tkfont.families(root))
    present = [f for f in emoji_font_candidates if f in available_fonts]

    header = tk.Frame(root)
    header.pack(fill="x", padx=10, pady=10)

    tk.Label(header, text="Emoji-capable fonts detected:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    tk.Label(header, text=", ".join(present) if present else "(none of the common emoji fonts were found)").pack(anchor="w")

    # Choose an emoji font if present; otherwise keep default.
    emoji_font_name = present[0] if present else "Segoe UI"

    # Entry test
    entry_frame = tk.Frame(root)
    entry_frame.pack(fill="x", padx=10)

    tk.Label(entry_frame, text="Entry (emoji font):").pack(anchor="w")
    entry = tk.Entry(entry_frame, font=(emoji_font_name, 14))
    entry.pack(fill="x")
    entry.insert(0, "Type/paste emoji here: 🙂 🚀 ❤️ 👩‍💻 🇺🇸")

    # Two panes: left normal insertion, right insertion + emoji tagging
    panes = tk.PanedWindow(root, orient="horizontal", sashrelief="raised")
    panes.pack(expand=True, fill="both", padx=10, pady=10)

    left = tk.Frame(panes)
    right = tk.Frame(panes)
    panes.add(left)
    panes.add(right)

    tk.Label(left, text="ScrolledText A: normal Segoe UI", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    a = scrolledtext.ScrolledText(left, wrap="word", font=("Segoe UI", 12))
    a.pack(expand=True, fill="both")

    tk.Label(right, text=f"ScrolledText B: Segoe UI + emoji tag ({emoji_font_name})", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    b = scrolledtext.ScrolledText(right, wrap="word", font=("Segoe UI", 12))
    b.pack(expand=True, fill="both")

    # Tag with emoji font
    b.tag_config("emoji", font=(emoji_font_name, 12))

    # Optional: visibly mark emoji runs so you can confirm the tag applied.
    b.tag_config("emoji_debug", background="#222222")

    def insert_samples():
        a.delete("1.0", "end")
        b.delete("1.0", "end")

        for s in SAMPLES:
            a.insert("end", s + "\n")

            start = b.index("end")
            b.insert("end", s + "\n")
            end = b.index("end")

            tag_emojis_in_widget(b, start, end, "emoji")
            # Also apply a debug background on the same ranges (so we can see it worked)
            # We do this by re-running the tagging logic into a second tag.
            tag_emojis_in_widget(b, start, end, "emoji_debug")

        a.insert("end", "\nIf A shows boxes but B shows emoji: tagging+font works.\n")
        b.insert("end", "\nIf B still shows boxes: your Tk build/font stack can’t render emoji.\n")

    def show_codepoints():
        # Dump the current Entry string as codepoints.
        s = entry.get()
        lines = []
        for ch in s:
            cp = ord(ch)
            lines.append(f"U+{cp:04X}  {ch}")
        win = tk.Toplevel(root)
        win.title("Codepoints")
        t = scrolledtext.ScrolledText(win, wrap="word", font=("Consolas", 10))
        t.pack(expand=True, fill="both")
        t.insert("1.0", "\n".join(lines))
        t.config(state="disabled")

    btns = tk.Frame(root)
    btns.pack(fill="x", padx=10, pady=(0, 10))

    tk.Button(btns, text="Insert sample lines", command=insert_samples).pack(side="left")
    tk.Button(btns, text="Show entry codepoints", command=show_codepoints).pack(side="left", padx=10)
    tk.Button(btns, text="Quit", command=root.destroy).pack(side="right")

    insert_samples()
    root.mainloop()


if __name__ == "__main__":
    main()
