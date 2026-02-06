import os
from tqdm import tqdm
from colorama import init, Fore, Style

# Initialize colorama
init()

def to_unix(filepath):
    try:
        with open(filepath, 'rb') as f:
            content = f.read()
        
        new_content = content.replace(b'\r\n', b'\n')
        
        if new_content != content:
            with open(filepath, 'wb') as f:
                f.write(new_content)
            return True
    except Exception as e:
        print(f"{Fore.RED}Error with {filepath}: {e}{Style.RESET_ALL}")
    return False

# Fix all scripts in the entire tts_dojo directory structure
base_dir = r"training/make piper voice models/tts_dojo"

print(f"{Fore.CYAN}Scanning and fixing line endings in {base_dir}...{Style.RESET_ALL}")

# First, collect all files to process so we can show an accurate progress bar
files_to_process = []
for root, dirs, files in os.walk(base_dir):
    for file in files:
        if file.endswith(('.sh', '.txt', '.conf', '.py')):
            files_to_process.append(os.path.join(root, file))

fixed_count = 0
for file_path in tqdm(files_to_process, desc="Fixing Files", unit="file", bar_format="{l_bar}{bar:30}{r_bar}"):
    if to_unix(file_path):
        fixed_count += 1

print(f"\n{Fore.GREEN}✔ Done! Fixed line endings in {fixed_count} files.{Style.RESET_ALL}")
