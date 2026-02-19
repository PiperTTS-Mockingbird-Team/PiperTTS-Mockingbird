import os
import sys
import hashlib
import tkinter as tk
from tkinter import scrolledtext

import requests
from PIL import Image, ImageTk


# Twemoji CDN (stable). You can swap versions if needed.
TWEMOJI_BASE = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72"


def _is_regional_indicator(cp: int) -> bool:
    return 0x1F1E6 <= cp <= 0x1F1FF


def _is_vs16(cp: int) -> bool:
    return cp == 0xFE0F


def _is_zwj(cp: int) -> bool:
    return cp == 0x200D


def _is_skin_tone(cp: int) -> bool:
    return 0x1F3FB <= cp <= 0x1F3FF


def _is_keycap(cp: int) -> bool:
    # combining enclosing keycap
    return cp == 0x20E3


def _is_emoji_base(cp: int) -> bool:
    # Heuristic emoji ranges (good enough for UI usage)
    if cp in (0x00A9, 0x00AE):
        return True
    if 0x2600 <= cp <= 0x27BF:
        return True
    if 0x1F000 <= cp <= 0x1FAFF:
        return True
    if 0x2300 <= cp <= 0x23FF:
        return True
    # Keycap bases: 0-9, #, *
    if cp in (0x0023, 0x002A) or 0x0030 <= cp <= 0x0039:
        return True
    return False


def iter_emoji_clusters(text: str):
    """Yield (start, end, cluster) for emoji-like grapheme clusters.

    Uses `regex` module if installed for accurate grapheme cluster handling.
    Falls back to a pragmatic ZWJ/VS16/modifier heuristic.
    """
    try:
        import regex as re2  # type: ignore

        # Grapheme clusters: \X
        # Use Extended_Pictographic or regional-indicator flags.
        for m in re2.finditer(r"\X", text):
            cluster = m.group(0)
            if re2.search(r"\p{Extended_Pictographic}", cluster):
                yield m.start(), m.end(), cluster
                continue
            # Flags are two regional indicators
            cps = [ord(ch) for ch in cluster]
            if len(cps) == 2 and all(_is_regional_indicator(cp) for cp in cps):
                yield m.start(), m.end(), cluster
                continue
    except Exception:
        i = 0
        n = len(text)
        while i < n:
            cp = ord(text[i])

            # Flags
            if _is_regional_indicator(cp):
                start = i
                i += 1
                if i < n and _is_regional_indicator(ord(text[i])):
                    i += 1
                    yield start, i, text[start:i]
                    continue
                # single RIS, treat as normal char
                continue

            if not _is_emoji_base(cp):
                i += 1
                continue

            start = i
            i += 1

            # Optional VS16
            if i < n and _is_vs16(ord(text[i])):
                i += 1

            # Optional keycap sequence: [0-9#*] FE0F? 20E3
            if i < n and _is_keycap(ord(text[i])):
                i += 1
                yield start, i, text[start:i]
                continue

            # Optional skin tone modifier
            if i < n and _is_skin_tone(ord(text[i])):
                i += 1

            # ZWJ sequences
            while i < n and _is_zwj(ord(text[i])):
                i += 1
                if i >= n:
                    break
                if not _is_emoji_base(ord(text[i])) and not _is_regional_indicator(ord(text[i])):
                    break
                i += 1
                if i < n and _is_vs16(ord(text[i])):
                    i += 1
                if i < n and _is_skin_tone(ord(text[i])):
                    i += 1

            yield start, i, text[start:i]


def twemoji_codepoints(cluster: str) -> str:
    cps = [ord(ch) for ch in cluster]
    return "-".join(format(cp, "x") for cp in cps)


def fetch_twemoji_png(codepoints: str, cache_dir: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)

    # Name is already a canonical codepoint sequence; still hash to be safe.
    safe_name = hashlib.sha1(codepoints.encode("utf-8")).hexdigest()[:16]
    local_path = os.path.join(cache_dir, f"{safe_name}-{codepoints}.png")

    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        return local_path

    url = f"{TWEMOJI_BASE}/{codepoints}.png"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    with open(local_path, "wb") as f:
        f.write(r.content)
    return local_path


def insert_with_twemoji_images(text_widget: tk.Text, text: str, *, font_px: int = 16, cache_dir: str = ".twemoji_cache"):
    """Insert text into widget, replacing emoji clusters with images."""
    # Keep references on widget to avoid GC.
    refs = getattr(text_widget, "_emoji_image_refs", None)
    if refs is None:
        refs = []
        text_widget._emoji_image_refs = refs  # type: ignore[attr-defined]

    pos = 0
    for start, end, cluster in iter_emoji_clusters(text):
        if start > pos:
            text_widget.insert("end", text[pos:start])

        codepoints = twemoji_codepoints(cluster)
        try:
            png_path = fetch_twemoji_png(codepoints, cache_dir)
            img = Image.open(png_path).convert("RGBA")

            # Scale to roughly match text height.
            target = int(font_px * 1.2)
            img = img.resize((target, target), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            refs.append(photo)
            text_widget.image_create("end", image=photo)
        except Exception:
            # Fallback: insert raw cluster
            text_widget.insert("end", cluster)

        pos = end

    if pos < len(text):
        text_widget.insert("end", text[pos:])


SAMPLES = [
    "Basic: 🙂 😂 😭 🥹 🤖 🚀 ✅ ❌\n",
    "Hearts/VS16: ❤️ ♥️ 💜\n",
    "Flags: 🇺🇸 🇬🇧 🇨🇦 🇯🇵\n",
    "ZWJ family: 👨‍👩‍👧‍👦 | woman technologist: 👩‍💻\n",
    "Skin tones: 👍 👍🏽 👍🏿\n",
    "Keycaps: 1️⃣ 2️⃣ #️⃣ *️⃣\n",
]


def main():
    root = tk.Tk()
    root.title("Emoji-as-Images Prototype (Twemoji)")
    root.geometry("980x650")

    top = tk.Frame(root)
    top.pack(fill="x", padx=10, pady=10)

    info = (
        "This prototype renders emojis as Twemoji images embedded in a Tk Text widget.\n"
        "If this looks like real emoji, we can port the same approach into the main chat UI."
    )
    tk.Label(top, text=info, justify="left").pack(anchor="w")

    entry = tk.Entry(top, font=("Segoe UI", 12))
    entry.pack(fill="x", pady=(10, 6))
    entry.insert(0, "Try typing/pasting emoji here 🙂 🚀 ❤️ 👩‍💻 🇺🇸 1️⃣")

    btns = tk.Frame(top)
    btns.pack(fill="x")

    body = tk.Frame(root)
    body.pack(expand=True, fill="both", padx=10, pady=10)

    left = tk.Frame(body)
    right = tk.Frame(body)
    left.pack(side="left", expand=True, fill="both", padx=(0, 8))
    right.pack(side="left", expand=True, fill="both", padx=(8, 0))

    tk.Label(left, text="A) Normal Tk text", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    normal = scrolledtext.ScrolledText(left, wrap="word", font=("Segoe UI", 12))
    normal.pack(expand=True, fill="both")

    tk.Label(right, text="B) Twemoji images in Tk text", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    imgtext = scrolledtext.ScrolledText(right, wrap="word", font=("Segoe UI", 12))
    imgtext.pack(expand=True, fill="both")

    def render_samples():
        normal.config(state="normal")
        imgtext.config(state="normal")
        normal.delete("1.0", "end")
        imgtext.delete("1.0", "end")

        for s in SAMPLES:
            normal.insert("end", s)
            insert_with_twemoji_images(imgtext, s, font_px=12, cache_dir=os.path.join(os.path.dirname(__file__), ".twemoji_cache"))

        normal.insert("end", "\nPaste/Type below and click Render input:\n")
        imgtext.insert("end", "\nPaste/Type below and click Render input:\n")

        normal.config(state="disabled")
        imgtext.config(state="disabled")

    def render_input():
        s = entry.get() + "\n"
        normal.config(state="normal")
        imgtext.config(state="normal")
        normal.insert("end", s)
        insert_with_twemoji_images(imgtext, s, font_px=12, cache_dir=os.path.join(os.path.dirname(__file__), ".twemoji_cache"))
        normal.see("end")
        imgtext.see("end")
        normal.config(state="disabled")
        imgtext.config(state="disabled")

    def copy_plain():
        root.clipboard_clear()
        root.clipboard_append(entry.get())

    tk.Button(btns, text="Render samples", command=render_samples).pack(side="left")
    tk.Button(btns, text="Render input", command=render_input).pack(side="left", padx=8)
    tk.Button(btns, text="Copy plain text", command=copy_plain).pack(side="left")
    tk.Button(btns, text="Quit", command=root.destroy).pack(side="right")

    render_samples()
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
