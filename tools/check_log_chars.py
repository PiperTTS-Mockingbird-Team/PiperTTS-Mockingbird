
try:
    with open("training_recent_logs.txt", "r", encoding="utf-16") as f:
        content = f.read()
except:
    with open("training_recent_logs.txt", "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

lines = content.splitlines()
for line in lines[:50]:
    if any(ord(c) > 127 for c in line):
        print(f"Found line with non-ascii: {line!r}")
