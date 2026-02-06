import os

target_dir = r"make piper voice models/tts_dojo"
count = 0

print(f"Scanning {target_dir} for .sh files with Windows line endings...")

for root, dirs, files in os.walk(target_dir):
    for file in files:
        if file.endswith(".sh"):
            full_path = os.path.join(root, file)
            try:
                with open(full_path, 'rb') as f:
                    content = f.read()
                
                if b'\r\n' in content:
                    content = content.replace(b'\r\n', b'\n')
                    with open(full_path, 'wb') as f:
                        f.write(content)
                    print(f"Fixed: {file}")
                    count += 1
            except Exception as e:
                print(f"Error reading {file}: {e}")

print(f"Done. Fixed {count} files.")
