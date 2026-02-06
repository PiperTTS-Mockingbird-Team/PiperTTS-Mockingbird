"""
Piper Storage Manager UI
-------------------------
This module provides a graphical interface for managing disk space used by the Piper TTS system.
It allows users to:
1. Monitor and delete Piper 'dojos' (training environments).
2. Clean up pretrained base models and language packs.
3. Manage production-ready voice models used by the server.
4. Reclaim disk space by pruning Docker images and clearing training caches.
"""

import os
import sys
import shutil
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import threading
import subprocess

# Common utilities for sanitization and config management
from common_utils import validate_voice_name, safe_config_save, safe_config_load

# --- Constants & Paths ---
# ROOT_DIR: The top-level directory of the project, used as a reference point for all relative paths.
ROOT_DIR = Path(__file__).resolve().parent.parent
# DOJO_ROOT: Folder where piper training environments ("dojos") are located.
DOJO_ROOT = ROOT_DIR / "training" / "make piper voice models" / "tts_dojo"
# PRETRAINED_ROOT: Directory containing base checkpoints used for fine-tuning.
PRETRAINED_ROOT = DOJO_ROOT / "PRETRAINED_CHECKPOINTS"
# VOICES_ROOT: Folder where production models used by the Piper Server are stored.
VOICES_ROOT = ROOT_DIR / "voices"

def get_size_bytes(path: Path) -> int:
    """
    Robustly calculates size in bytes for a file or directory.
    Uses an iterative approach for stability with large structures.
    """
    total = 0
    try:
        if not path.exists(): return 0
        if path.is_file(): return path.stat().st_size
        for root, dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except (OSError, PermissionError):
                    continue
    except Exception:
        pass
    return total

def treeview_sort_column(tv, col, reverse):
    """Sorts treeview content when a column header is clicked."""
    l = [(tv.set(k, col), k) for k in tv.get_children('')]
    
    # Try numeric conversion for size columns
    def try_float(v):
        try:
            # Strip " GB", " MB", " files" etc
            return float(v.split()[0].replace(',', ''))
        except (ValueError, IndexError):
            return v.lower()

    l.sort(key=lambda t: try_float(t[0]), reverse=reverse)

    for index, (val, k) in enumerate(l):
        tv.move(k, '', index)

    # Toggle sort order for next click
    tv.heading(col, command=lambda: treeview_sort_column(tv, col, not reverse))

class StorageManagerUI:
    """
    Main Application Class for the Piper Storage Manager.
    Handles the initialization of the Tkinter UI and orchestration of storage-related tasks.
    """
    def __init__(self, root):
        """
        Initialize the Storage Manager application.
        
        Args:
            root (tk.Tk): The root Tkinter window.
        """
        self.root = root
        self.root.title("Piper Storage Manager")
        self.root.geometry("900x700")

        # Force window to front on launch - use multiple methods for reliability
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.update()
        self.root.focus_force()
        self.root.after(100, lambda: [
            self.root.attributes("-topmost", False),
            self.root.focus_set()
        ])

        # Setup widgets and layouts
        self.setup_ui()
        # Initial scan of the storage
        self.refresh_data()

    def setup_ui(self):
        """
        Constructs the user interface, including the notebook tabs and control buttons.
        """
        # Header - Contains title and global refresh button
        header = ttk.Frame(self.root, padding="10")
        header.pack(fill="x")
        
        ttk.Label(header, text="Piper Storage & Cleanup", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(header, text="🔄 Refresh All", command=self.refresh_data).pack(side="right", padx=5)

        # Notebook for Tabs - Main organization of the storage content categories
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Tab 1: Training Dojos ---
        # Used for keeping track of active/inactive training environments
        self.dojo_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.dojo_tab, text=" Training Dojos ")
        
        dojo_scroll = ttk.Frame(self.dojo_tab)
        dojo_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Treeview for Dojo data
        cols = ("Name", "Size", "Path")
        self.dojo_tree = ttk.Treeview(dojo_scroll, columns=cols, show="headings", height=15)
        for col in cols:
            self.dojo_tree.heading(col, text=col if col != "Size" else "Size (GB)", 
                                   command=lambda c=col: treeview_sort_column(self.dojo_tree, c, False))
            
        self.dojo_tree.column("Name", width=200)
        self.dojo_tree.column("Size", width=100, anchor="center")
        self.dojo_tree.column("Path", width=400)
        self.dojo_tree.pack(side="left", fill="both", expand=True)
        self.dojo_tree.bind("<Double-1>", lambda e: self.open_selected_dojo())
        
        # Scrollbar for the Treeview
        sb = ttk.Scrollbar(dojo_scroll, orient="vertical", command=self.dojo_tree.yview)
        sb.pack(side="right", fill="y")
        self.dojo_tree.configure(yscrollcommand=sb.set)

        # Dojo action buttons
        dojo_actions = ttk.Frame(self.dojo_tab, padding=10)
        dojo_actions.pack(fill="x")
        ttk.Button(dojo_actions, text="🗑 Delete Selected Dojo", command=self.delete_selected_dojo).pack(side="left", padx=5)
        ttk.Button(dojo_actions, text="📂 Open Folder", command=self.open_selected_dojo).pack(side="left", padx=5)

        # --- Tab 2: Pretrained Models & Languages ---
        # Manages the base models that Piper uses for fine-tuning
        self.model_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.model_tab, text=" Pretrained Models ")
        
        model_scroll = ttk.Frame(self.model_tab)
        model_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Treeview for models/folders
        m_cols = ("File/Folder", "Language", "Size")
        self.model_tree = ttk.Treeview(model_scroll, columns=m_cols, show="headings")
        for col in m_cols:
            self.model_tree.heading(col, text=col if col != "Size" else "Size (MB)", 
                                    command=lambda c=col: treeview_sort_column(self.model_tree, c, False))
        
        self.model_tree.column("Size", width=100, anchor="center")
        self.model_tree.pack(side="left", fill="both", expand=True)
        # Bind double click to open the containing folder
        self.model_tree.bind("<Double-1>", lambda e: self.open_selected_model_folder())
        
        sb2 = ttk.Scrollbar(model_scroll, orient="vertical", command=self.model_tree.yview)
        sb2.pack(side="right", fill="y")
        self.model_tree.configure(yscrollcommand=sb2.set)

        # Model action buttons
        model_actions = ttk.Frame(self.model_tab, padding=10)
        model_actions.pack(fill="x")
        ttk.Button(model_actions, text="🗑 Delete Selected Model", command=self.delete_selected_model).pack(side="left", padx=5)
        ttk.Button(model_actions, text="🧹 Keep Only English (Cleanup)", command=self.cleanup_non_english).pack(side="right", padx=5)

        # --- Tab 3: Production Voices ---
        # Manages the optimized models ready for TTS serving
        self.voice_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.voice_tab, text=" Installed Voices (Server) ")
        
        voice_scroll = ttk.Frame(self.voice_tab)
        voice_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Treeview for voices
        v_cols = ("Name", "Files", "Size")
        self.voice_tree = ttk.Treeview(voice_scroll, columns=v_cols, show="headings")
        for col in v_cols:
            self.voice_tree.heading(col, text=col if col != "Size" else "Total Size (MB)", 
                                    command=lambda c=col: treeview_sort_column(self.voice_tree, c, False))
            
        self.voice_tree.column("Size", width=100, anchor="center")
        self.voice_tree.pack(side="left", fill="both", expand=True)
        self.voice_tree.bind("<Double-1>", lambda e: self.open_selected_voice_folder())
        
        sb3 = ttk.Scrollbar(voice_scroll, orient="vertical", command=self.voice_tree.yview)
        sb3.pack(side="right", fill="y")
        self.voice_tree.configure(yscrollcommand=sb3.set)

        # Voice action buttons
        voice_actions = ttk.Frame(self.voice_tab, padding=10)
        voice_actions.pack(fill="x")
        ttk.Button(voice_actions, text="🗑 Delete Selected Voice", command=self.delete_selected_voice).pack(side="left", padx=5)

        # --- Tab 4: System & Docker ---
        # Advanced cleanup for Docker images and training artifacts
        self.sys_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.sys_tab, text=" System & Docker ")
        
        sys_frame = ttk.Frame(self.sys_tab, padding=20)
        sys_frame.pack(fill="both", expand=True)

        # Docker Image Section - For reclaiming massive space (17GB+)
        dock_lf = ttk.LabelFrame(sys_frame, text=" Docker Training Environment ", padding=15)
        dock_lf.pack(fill="x", pady=(0, 20))
        
        self.docker_status_var = tk.StringVar(value="Checking Docker status...")
        ttk.Label(dock_lf, textvariable=self.docker_status_var, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        
        desc = ("The Docker image contains the 17.5GB training environment (CUDA, PyTorch, Linux).\n"
                "If you delete this, you reclaim 17GB+ immediately, but it MUST be re-downloaded\n"
                "the next time you start training a voice.")
        ttk.Label(dock_lf, text=desc, foreground="#666", wraplength=700).pack(anchor="w", pady=10)
        
        self.prune_docker_btn = ttk.Button(dock_lf, text="🗑 Delete Training Image (Reclaim ~17.5 GB)", 
                                         command=self.prune_docker_image, state="disabled")
        self.prune_docker_btn.pack(anchor="w")

        # Cache Section - For clearing intermediate training files
        cache_lf = ttk.LabelFrame(sys_frame, text=" Training Cache Cleanup ", padding=15)
        cache_lf.pack(fill="x")
        
        cache_desc = ("Training 'Cache' folders store pre-processed audio and phoneme data.\n"
                     "Cleaning these is safe and will not harm your training progress or model files.")
        ttk.Label(cache_lf, text=cache_desc, foreground="#2c3e50", font=("Segoe UI", 9, "bold"), wraplength=700).pack(anchor="w", pady=(0, 10))
        
        # UI visualization for Pros and Cons of wiping cache
        pc_frame = ttk.Frame(cache_lf)
        pc_frame.pack(fill="x", pady=5)
        
        pro_frame = ttk.Frame(pc_frame)
        pro_frame.pack(side="left", fill="both", expand=True)
        ttk.Label(pro_frame, text="PROS:", foreground="#27ae60", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(pro_frame, text="• Reclaims 300MB-1GB per dojo\n• Ensures fresh data if dataset changed\n• Zero risk to model progress", foreground="#666").pack(anchor="w")

        con_frame = ttk.Frame(pc_frame)
        con_frame.pack(side="left", fill="both", expand=True, padx=(20, 0))
        ttk.Label(con_frame, text="CONS:", foreground="#e67e22", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(con_frame, text="• Next training session starts slower\n• Temporary high CPU while rebuilding\n• Re-downloads some base files", foreground="#666").pack(anchor="w")

        btn_frame = ttk.Frame(cache_lf)
        btn_frame.pack(fill="x", pady=(15, 0))
        ttk.Button(btn_frame, text="🧹 Wipe ALL Dojo Caches", command=self.wipe_all_caches).pack(side="left")

        # Footer Status bar for informational messages
        footer = ttk.Frame(self.root)
        footer.pack(side="bottom", fill="x")
        
        self.status_bar = ttk.Label(footer, text="Ready", relief="sunken", anchor="w")
        self.status_bar.pack(side="left", fill="x", expand=True)
        
        self.total_space_lbl = ttk.Label(footer, text="Total Managed: 0.00 GB", font=("Segoe UI", 9, "bold"), padding=(10, 0))
        self.total_space_lbl.pack(side="right")

    def refresh_data(self):
        """
        Triggers a fresh scan of all storage directories in a background thread to keep UI responsive.
        Populates all Treeviews and checks Docker status.
        """
        self.status_bar.config(text="Scanning storage... please wait")
        
        def work():
            total_bytes = 0
            
            # --- Collection Phase ---
            dojo_data = []
            if DOJO_ROOT.exists():
                for item in DOJO_ROOT.iterdir():
                    if item.is_dir() and item.name.endswith("_dojo"):
                        size = get_size_bytes(item)
                        total_bytes += size
                        dojo_data.append((item.name, f"{size/(1024**3):.2f}", str(item)))

            model_data = []
            if PRETRAINED_ROOT.exists():
                for sub in ["default", "languages"]:
                    path = PRETRAINED_ROOT / sub
                    if not path.exists(): continue
                    for f in path.glob("*"):
                        if f.name == ".SAMPLING_RATE": continue # skip metadata
                        size = get_size_bytes(f)
                        total_bytes += size
                        m_type = "Default Base" if sub == "default" else "Language Pack"
                        model_data.append((f.name, m_type, f"{size/(1024**2):.1f} MB"))

            voice_data = []
            if VOICES_ROOT.exists():
                skip = ["HOW_TO_ADD_VOICES.md"]
                for item in VOICES_ROOT.iterdir():
                    if item.name in skip: continue
                    size = get_size_bytes(item)
                    total_bytes += size
                    if item.is_dir():
                        files = list(item.glob("*"))
                        voice_data.append((item.name, f"{len(files)} files", f"{size/(1024**2):.1f}"))
                    elif item.suffix in [".onnx", ".json"]:
                        voice_data.append((item.name, "Individual File", f"{size/(1024**2):.1f}"))

            # --- Docker Image Check ---
            docker_status = "Docker not detected or not running."
            docker_state = "disabled"
            try:
                img_check = subprocess.run(["docker", "images", "--format", "{{.Size}}", "domesticatedviking/textymcspeechy-piper:latest"], 
                                         capture_output=True, text=True, shell=True)
                size_str = img_check.stdout.strip()
                if size_str:
                    docker_status = f"Training Environment: INSTALLED (Size: {size_str})"
                    docker_state = "normal"
                    # Try to parse docker size (e.g. "17.5GB")
                    try:
                        num = float(size_str.replace('GB', '').replace('MB', '').strip())
                        if 'GB' in size_str: total_bytes += int(num * (1024**3))
                        elif 'MB' in size_str: total_bytes += int(num * (1024**2))
                    except: pass
                else:
                    docker_status = "Training Environment: NOT FOUND (Already deleted)"
            except Exception: pass

            # --- UI Update Phase (back on main thread) ---
            def update_ui():
                # Clear all
                for tv in [self.dojo_tree, self.model_tree, self.voice_tree]:
                    for i in tv.get_children(): tv.delete(i)
                
                # Insert new
                for d in dojo_data: self.dojo_tree.insert("", "end", values=d)
                for m in model_data: self.model_tree.insert("", "end", values=m)
                for v in voice_data: self.voice_tree.insert("", "end", values=v)
                
                self.docker_status_var.set(docker_status)
                self.prune_docker_btn.config(state=docker_state)
                self.total_space_lbl.config(text=f"Total Managed: {total_bytes/(1024**3):.2f} GB")
                self.status_bar.config(text="Refresh complete.")

            self.root.after(0, update_ui)

        threading.Thread(target=work, daemon=True).start()

    def delete_selected_dojo(self):
        """
        Deletes the selected training dojo from disk after user confirmation.
        WARNING: This is permanent.
        """
        sel = self.dojo_tree.selection()
        if not sel: return
        
        name = self.dojo_tree.item(sel[0], "values")[0]
        full_path = Path(self.dojo_tree.item(sel[0], "values")[2])
        
        if messagebox.askyesno("CONFIRM DELETE", f"Are you absolutely sure you want to delete '{name}'?\n\nThis will permanently destroy all training progress and checkpoints within this dojo."):
            try:
                # Use the Training Manager's safe deletion logic instead of raw rmtree
                from training_manager import training_manager
                result = training_manager.delete_dojo(name)
                
                if result.get("ok"):
                    self.refresh_data()
                    messagebox.showinfo("Deleted", f"Successfully removed {name}")
                else:
                    messagebox.showerror("Error", f"Deletion failed: {result.get('error')}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not delete: {e}")

    def open_selected_dojo(self):
        """
        Opens the selected dojo's location in the system file explorer.
        """
        sel = self.dojo_tree.selection()
        if not sel: return
        full_path = self.dojo_tree.item(sel[0], "values")[2]
        if os.path.exists(full_path):
            os.startfile(full_path)

    def open_selected_model_folder(self):
        """Opens folder containing selected pretrained model."""
        sel = self.model_tree.selection()
        if not sel: return
        name = self.model_tree.item(sel[0], "values")[0]
        for p in [PRETRAINED_ROOT / "default" / name, PRETRAINED_ROOT / "languages" / name]:
            if p.exists():
                os.startfile(p.parent if p.is_file() else p)
                break

    def open_selected_voice_folder(self):
        """Opens the folder containing the production voice model."""
        sel = self.voice_tree.selection()
        if not sel: return
        name = self.voice_tree.item(sel[0], "values")[0]
        target = VOICES_ROOT / name
        if target.exists():
            os.startfile(target.parent if target.is_file() else target)

    def delete_selected_model(self):
        """
        Deletes a pretrained base model or language pack.
        """
        sel = self.model_tree.selection()
        if not sel: return
        name = self.model_tree.item(sel[0], "values")[0]
        
        # Locate the actual path in default or language folders
        target = None
        for p in [PRETRAINED_ROOT / "default" / name, PRETRAINED_ROOT / "languages" / name]:
            if p.exists():
                target = p
                break
        
        if target and messagebox.askyesno("Delete Model", f"Delete {name}?"):
            try:
                if target.is_dir(): shutil.rmtree(target)
                else: target.unlink()
                self.refresh_data()
            except Exception as e:
                messagebox.showerror("Error", e)

    def cleanup_non_english(self):
        """
        Utility function to purge all non-English language models to save space.
        """
        if not messagebox.askyesno("Cleanup", "This will delete all pretrained models that are NOT 'en' (English). Continue?"):
            return
        
        lang_path = PRETRAINED_ROOT / "languages"
        if lang_path.exists():
            count = 0
            for item in lang_path.glob("*"):
                # If it doesn't start with 'en' (e.g., 'es', 'fr', 'de'), delete it
                if not item.name.startswith("en"):
                    try:
                        if item.is_dir(): shutil.rmtree(item)
                        else: item.unlink()
                        count += 1
                    except: pass
            self.refresh_data()
            messagebox.showinfo("Cleanup Done", f"Removed {count} non-English items.")

    def delete_selected_voice(self):
        """
        Deletes a production voice model. Usually includes .onnx and .json files.
        """
        sel = self.voice_tree.selection()
        if not sel: return
        name = self.voice_tree.item(sel[0], "values")[0]
        
        try:
            # Sanitize the name before using it in a path operation
            safe_name = validate_voice_name(name)
            target = VOICES_ROOT / safe_name
        except ValueError:
            messagebox.showerror("Error", "Invalid voice name detected.")
            return
        
        if target.exists() and messagebox.askyesno("Delete Voice", f"Are you sure you want to delete the production voice model '{name}'?\n\nThis will remove it from the server."):
            try:
                if target.is_dir(): shutil.rmtree(target)
                else: target.unlink()
                self.refresh_data()
                messagebox.showinfo("Deleted", f"Successfully removed {name}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not delete: {e}")

    def prune_docker_image(self):
        """
        Runs the Docker RMI command to remove the large training image.
        """
        msg = ("Are you sure you want to delete the 17.5GB Training Image?\n\n"
               "IT IS RECOVERABLE: You just hit 'Start Training' in the dashboard "
               "and it will download it again (requires internet).")
        if messagebox.askyesno("Confirm Delete", msg):
            self.status_bar.config(text="Deleting Docker image... this may take a moment.")
            def work():
                try:
                    # Executes the removal command. Note: if the container is running, this might fail unless forced.
                    subprocess.run(["docker", "rmi", "domesticatedviking/textymcspeechy-piper:latest"], 
                                 capture_output=True, check=True, shell=True)
                    self.root.after(0, lambda: messagebox.showinfo("Success", "Training image removed. ~17.5GB reclaimed."))
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to delete image: {e}"))
                self.root.after(0, self.refresh_data)
            
            # Run prune in background thread
            threading.Thread(target=work, daemon=True).start()

    def wipe_all_caches(self):
        """
        Iterates through all dojos and removes their training cache folders.
        Caches contain pre-processed features (linear spectrograms, etc.) which can be massive.
        """
        if messagebox.askyesno("Wipe Caches", "Delete all pre-processed training files? (Safe to do, but next training will take longer to start)"):
            count = 0
            # Glob search for all cache directories within dojo structures
            for cache_dir in DOJO_ROOT.glob("*/training_folder/cache"):
                if cache_dir.is_dir():
                    try:
                        shutil.rmtree(cache_dir)
                        count += 1
                    except: pass
            self.refresh_data()
            messagebox.showinfo("Done", f"Wiped cache for {count} dojo(s).")

if __name__ == "__main__":
    # Standard Tkinter entry point
    root = tk.Tk()
    app = StorageManagerUI(root)
    root.mainloop()


