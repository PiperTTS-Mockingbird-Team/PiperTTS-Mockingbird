import subprocess
import os

def run_git():
    try:
        # Add all changes
        subprocess.run(["git", "add", "."], check=True)
        # Commit
        subprocess.run(["git", "commit", "-m", "Final stable version with frozen requirements"], check=True)
        # Create and checkout branch
        subprocess.run(["git", "checkout", "-b", "v1-stable-release"], check=True)
        print("Successfully created branch v1-stable-release")
    except subprocess.CalledProcessError as e:
        print(f"Error during git operations: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    run_git()
