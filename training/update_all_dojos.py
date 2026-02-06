import shutil
import os
from tqdm import tqdm
from colorama import init, Fore, Style

# Initialize colorama for Windows support
init()

# Use an absolute path relative to the script location so it works if the folder is moved
script_dir = os.path.dirname(os.path.abspath(__file__))
dojo_root = os.path.join(script_dir, "make piper voice models", "tts_dojo")
template_root = os.path.join(dojo_root, "DOJO_CONTENTS")

scripts_to_sync = [
    "run_training.sh",
    "scripts/preprocess_dataset.sh",
    "scripts/utils/piper_training.sh",
    "scripts/utils/checkpoint_grabber.sh",
    "scripts/utils/_control_console.sh",
    "scripts/train.sh",
    "scripts/link_dataset.sh",
    # "scripts/SETTINGS.txt",  # Removed to avoid overwriting user settings (batch size, etc.)
]

# Get list of dojos to update
dojos = [item for item in os.listdir(dojo_root) if item.endswith("_dojo") and item != "DOJO_CONTENTS"]

if not dojos:
    print(f"{Fore.YELLOW}No dojos found to update.{Style.RESET_ALL}")
    exit()

print(f"{Fore.CYAN}Starting workspace-wide script synchronization...{Style.RESET_ALL}")

# Using tqdm for a professional progress bar
for item in tqdm(dojos, desc="Updating Voices", unit="dojo", bar_format="{l_bar}{bar:30}{r_bar}"):
    for rel_path in scripts_to_sync:
        template_path = os.path.join(template_root, rel_path)
        target_path = os.path.join(dojo_root, item, rel_path)
        
        if os.path.exists(template_path):
            # Ensure target directory exists
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(template_path, target_path)
        else:
            tqdm.write(f"{Fore.RED}  - Warning: Template not found for {rel_path} in {item}{Style.RESET_ALL}")

print(f"\n{Fore.GREEN}✔ Successfully synchronized {len(scripts_to_sync)} scripts across {len(dojos)} dojos.{Style.RESET_ALL}")
