import os

def to_unix(filepath):
    with open(filepath, 'rb') as f:
        content = f.read()
    
    new_content = content.replace(b'\r\n', b'\n')
    
    if new_content != content:
        with open(filepath, 'wb') as f:
            f.write(new_content)
        print(f"Fixed: {filepath}")

script_dir = r"make piper voice models/tts_dojo/girlll_dojo/scripts"

for root, dirs, files in os.walk(script_dir):
    for js_file in files:
        file_path = os.path.join(root, js_file)
        to_unix(file_path)

print("Done fixing line endings.")
