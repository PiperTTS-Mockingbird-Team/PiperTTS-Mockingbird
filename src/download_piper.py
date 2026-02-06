import os
import platform
import shutil
import tarfile
import zipfile
import urllib.request
import sys
from pathlib import Path

# Fixed version of Piper to ensure stability and compatibility
PIPER_VERSION = "2023.11.14-2"
BASE_URL = f"https://github.com/rhasspy/piper/releases/download/{PIPER_VERSION}"

def get_platform_url():
    """
    Determine the correct Piper release URL based on the current OS and architecture.
    Returns a tuple of (url, filename) or (None, None) if the platform is not supported.
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        # Windows is usually amd64 (x86_64)
        return f"{BASE_URL}/piper_windows_amd64.zip", "piper_windows_amd64.zip"
    
    elif system == "linux":
        # Check for various Linux architectures
        if machine in ["x86_64", "amd64"]:
            return f"{BASE_URL}/piper_linux_x86_64.tar.gz", "piper_linux_x86_64.tar.gz"
        elif machine in ["aarch64", "arm64"]:
            return f"{BASE_URL}/piper_linux_aarch64.tar.gz", "piper_linux_aarch64.tar.gz"
        elif machine.startswith("armv7"):
            return f"{BASE_URL}/piper_linux_armv7l.tar.gz", "piper_linux_armv7l.tar.gz"
            
    elif system == "darwin":
        # macOS supports both Intel and Apple Silicon
        if machine in ["x86_64", "amd64"]:
            return f"{BASE_URL}/piper_macos_x86_64.tar.gz", "piper_macos_x86_64.tar.gz"
        elif machine in ["aarch64", "arm64"]:
            return f"{BASE_URL}/piper_macos_aarch64.tar.gz", "piper_macos_aarch64.tar.gz"

    return None, None

def download_and_extract_piper(target_dir: Path):
    """
    Download and extract the Piper binary to the target directory.
    Handles different archive formats (.zip, .tar.gz) and sets executable permissions on Unix-like systems.
    """
    url, filename = get_platform_url()
    if not url:
        print(f"Error: No compatible Piper binary found for {platform.system()} {platform.machine()}")
        return False

    print(f"Downloading Piper from {url}...")
    
    download_path = target_dir / filename
    temp_download_path = target_dir / f"{filename}.tmp"
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Download with a simple progress indicator in the console
        last_percent = -1

        def progress(count, block_size, total_size):
            nonlocal last_percent
            if total_size > 0:
                percent = int(count * block_size * 100 / total_size)
                if percent != last_percent:
                    # Use a standard format that the Manager UI can intercept for its progress bar
                    # Protocol: PROGRESS:current/total or just percentage for simplicity
                    sys.stdout.write(f"PROGRESS:{percent}/100\n")
                    if percent % 5 == 0:  # Only log to text every 5% to avoid flooding
                        sys.stdout.write(f"Downloading... {percent}%\n")
                    sys.stdout.flush()
                    last_percent = percent

        # Download to temporary file first
        urllib.request.urlretrieve(url, temp_download_path, reporthook=progress)
        
        # Rename to final path on success
        if temp_download_path.exists():
            if download_path.exists():
                os.remove(download_path)
            temp_download_path.rename(download_path)
            
        print("\nDownload complete. Extracting...")

        # Extract based on file extension
        if filename.endswith(".zip"):
            with zipfile.ZipFile(download_path, 'r') as zip_ref:
                zip_ref.extractall(target_dir)
        elif filename.endswith(".tar.gz"):
            with tarfile.open(download_path, "r:gz") as tar_ref:
                tar_ref.extractall(target_dir)
        
        print("Extraction complete.")

        # Ensure executable permissions on Mac/Linux (not needed on Windows)
        if platform.system().lower() != "windows":
            # Check standard extraction path
            piper_exe = target_dir / "piper" / "piper"
            if piper_exe.exists():
                st = os.stat(piper_exe)
                os.chmod(piper_exe, st.st_mode | 0o111)
                print(f"Made {piper_exe} executable.")
            
            # Also check nested structure (some archives extract to ./piper/piper/piper)
            nested_exe = target_dir / "piper" / "piper" / "piper"
            if nested_exe.exists():
                st = os.stat(nested_exe)
                os.chmod(nested_exe, st.st_mode | 0o111)
                print(f"Made {nested_exe} executable.")
        
        # Cleanup the downloaded archive to save space
        try:
            os.remove(download_path)
        except Exception:
            pass

        return True

    except Exception as e:
        print(f"\nError downloading/extracting Piper: {e}")
        # Cleanup temp file if it exists
        if 'temp_download_path' in locals() and temp_download_path.exists():
            try:
                os.remove(temp_download_path)
            except Exception:
                pass
        return False

if __name__ == "__main__":
    # Test run
    script_dir = Path(__file__).resolve().parent
    download_and_extract_piper(script_dir)
