import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import sys
import os
import threading
from pathlib import Path
import time

# Wizard GUI for automating the transcription step (Step 3) in the Piper TTS workflow.
class TranscribeWizard:
    def __init__(self, root):
        """Initialize the Transcription Wizard window and its state."""
        self.root = root
        self.root.title("Step 3: Auto-Transcribe")
        self.root.geometry("700x800") # Larger default
        self.root.minsize(600, 600)
        
        # Force window to front on launch - use multiple methods for reliability
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.update()
        self.root.focus_force()
        self.root.after(100, lambda: [
            self.root.attributes("-topmost", False),
            self.root.focus_set()
        ])

        # State variables for dataset path and project name
        self.dataset_dir = None
        self.voice_name = None
        self.parse_args()
        
        # Add scrollable main container
        outer_container = ttk.Frame(root)
        outer_container.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer_container)
        scrollbar = ttk.Scrollbar(outer_container, orient="vertical", command=canvas.yview)
        main_frame = ttk.Frame(canvas, padding="20")

        main_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        window_id = canvas.create_window((0, 0), window=main_frame, anchor="nw")
        
        def _on_canvas_configure(event):
            canvas.itemconfig(window_id, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        
        # Header with step description
        ttk.Label(main_frame, text="Step 3: Transcription", font=("Segoe UI", 16, "bold")).pack(pady=(0, 20))
        
        # Display information about the current project
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill="x", pady=(0, 20))
        ttk.Label(info_frame, text=f"Voice Project: {self.voice_name or 'Unknown'}").pack(anchor="w")
        ttk.Label(info_frame, text=f"Dataset: {self.dataset_dir or 'Unknown'}").pack(anchor="w")
        
        # Scrollable log area for real-time transcription feedback
        entry_frame = ttk.LabelFrame(main_frame, text="Progress Log", padding=10)
        entry_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        self.log_text = tk.Text(entry_frame, height=12, width=60, font=("Consolas", 9), state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True)
        
        scroll = ttk.Scrollbar(entry_frame, command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scroll.set)
        
        # Progress Bar for Step 3 feedback
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x")
        self.progress_label = ttk.Label(main_frame, text="Ready.")
        self.progress_label.pack(pady=(2, 0))

        # Action buttons (Start and Next Step)
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(10, 0))
        
        self.start_btn = ttk.Button(btn_frame, text="Start Transcription", command=self.start_transcription)
        self.start_btn.pack(side="left", padx=5)
        
        self.next_btn = ttk.Button(btn_frame, text="Step 4: Start Training ->", command=self.go_to_training, state="disabled")
        self.next_btn.pack(side="right", padx=5)

        # Handle window close event to ensure background processes are cleaned up
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Internal state for tracking the external transcription process
        self.process = None
        self.is_running = False

        # AUTO-START: If we have a dataset, start transcribing after a short delay
        if self.dataset_dir:
            self.root.after(1000, self.start_transcription)

    def on_close(self):
        """Cleanup before closing the application."""
        if self.process and self.process.poll() is None:
            if messagebox.askyesno("Confirm Exit", "Transcription is still running. Stop it and exit?"):
                try:
                    self.process.terminate()
                except:
                    pass
                self.root.destroy()
        else:
            self.root.destroy()

    def parse_args(self):
        """Parse command line arguments for dataset directory and voice name."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--dataset_dir", help="Dataset directory")
        parser.add_argument("--voice_name", help="Voice name")
        args, unknown = parser.parse_known_args()
        self.dataset_dir = args.dataset_dir
        self.voice_name = args.voice_name

    def log(self, msg):
        """Thread-safe logging helper to display messages in the UI text box."""
        self.log_text.config(state="normal")
        self.log_text.insert("end", str(msg) + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def update_progress(self, percent, current, total):
        """Updates the progress bar and label."""
        self.progress_var.set(percent)
        self.progress_label.config(text=f"Transcribing: {current} / {total} ({int(percent)}%)")

    def start_transcription(self):
        """Invoke the auto_transcribe.py script as a background process."""
        if not self.dataset_dir:
            messagebox.showerror("Error", "No dataset directory provided.")
            return

        # Clear log area for new run
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

        # Disable button to prevent multiple simultaneous runs
        self.start_btn.config(state="disabled")
        self.is_running = True
        
        # Path to the actual transcription worker script
        script_path = Path(__file__).parent.parent / "auto_transcribe.py"
        
        if not script_path.exists():
            self.log(f"Error: Script not found at {script_path}")
            self.start_btn.config(state="normal")
            return

        # Diagnostic: Check if files exist before starting
        try:
            wavs = list(Path(self.dataset_dir).glob("*.wav"))
            if not wavs:
                self.log(f"Warning: No .wav files found in {self.dataset_dir}")
                self.log("Make sure you exported segments from the slicer first!")
                self.start_btn.config(state="normal")
                self.is_running = False
                return
            self.log(f"Found {len(wavs)} wav files. Initializing AI process...")
        except Exception as e:
            self.log(f"Error checking directory: {e}")

        def run():
            """Worker function to execute the transcription script and capture output."""
            try:
                # Use python.exe to ensure we get console output (pythonw.exe suppresses it)
                py_exe = sys.executable.replace("pythonw.exe", "python.exe")
                
                cmd = [py_exe, str(script_path), self.dataset_dir]
                self.log(f"Running: {' '.join(cmd)}")
                
                # Configuration for hiding the console window on Windows
                startupinfo = None
                if os.name == 'nt':
                     startupinfo = subprocess.STARTUPINFO()
                     startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                # Launch the script process
                self.process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.STDOUT, 
                    universal_newlines=True,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                
                # Stream logs line by line to the UI
                if self.process.stdout:
                    for line in self.process.stdout:
                        line = line.strip()
                        if line:
                            # Update the visual text log in the UI
                            self.root.after(0, lambda l=line: self.log(l))
                            
                            # [UX IMPROVEMENT] Parse progress markers from stderr/stdout
                            # auto_transcribe.py prints "PROGRESS:current/total" which we catch here
                            # to update the graphical progress bar.
                            if "PROGRESS:" in line:
                                try:
                                    prog_part = line.split("PROGRESS:")[1].strip()
                                    current, total = map(int, prog_part.split("/"))
                                    percent = (current / total) * 100
                                    self.root.after(0, lambda p=percent, c=current, t=total: self.update_progress(p, c, t))
                                except: pass # Guard against malformed progress lines
                
                self.process.wait()
                
                # Update UI state based on success/failure
                if self.process.returncode == 0:
                    self.root.after(0, self.on_success)
                else:
                    self.root.after(0, lambda: self.log(f"\nFailed with code {self.process.returncode}"))
                    self.root.after(0, lambda: self.start_btn.config(state="normal"))

            except Exception as e:
                self.root.after(0, lambda: self.log(f"Error: {e}"))
                self.root.after(0, lambda: self.start_btn.config(state="normal"))
            finally:
                self.is_running = False

        # Launch the transcription in a background thread to keep the GUI responsive
        threading.Thread(target=run, daemon=True).start()

    def on_success(self):
        """Handle successful transcription completion."""
        self.log("\nTranscription Complete!")
        messagebox.showinfo("Success", "Transcription finished successfully.\nMetadata file created.")
        self.next_btn.config(state="normal")

    def go_to_training(self):
        """Transition from transcription to the training stage."""
        # [STEP 5 TRIGGER] AUTO-TRAIN FLOW: Launch Training Dashboard
        
        # Verify metadata exists as Step 3/4 completes by creating it
        meta_path = Path(self.dataset_dir) / "metadata.csv" 
        if not meta_path.exists():
             if not messagebox.askyesno("Warning", "metadata.csv not found. Continue to training anyway?"):
                 return

        # Path to the Training Dashboard GUI
        dashboard_script = Path(__file__).parent.parent / "training_dashboard_ui.py"
        
        try:
            py_exe = sys.executable.replace("pythonw.exe", "python.exe")
            cmd = [py_exe, str(dashboard_script)]
            if self.voice_name:
                cmd += ["--dojo", self.voice_name]

            # Start dashboard in a new process and close the wizard
            subprocess.Popen(cmd, cwd=str(dashboard_script.parent), creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open training dashboard: {e}")

if __name__ == "__main__":
    # Standard entry point to start the Tkinter application
    root = tk.Tk()
    app = TranscribeWizard(root)
    root.mainloop()
