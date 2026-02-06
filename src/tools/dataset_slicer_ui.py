import os
import sys
import time
import shutil
import subprocess
import threading
import tempfile
import math
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

# Add parent directory to path for audio_playback
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import audio_playback

# --- External Dependencies ---
# Try importing numpy for faster waveform processing
try:
    import numpy as np
except ImportError:
    np = None

def ensure_ffmpeg():
    """
    Checks if ffmpeg is available in the system path.
    If missing on Windows, attempts to install it via winget.
    FFmpeg is required by pydub for non-WAV formats like MP3/M4A.
    """
    try:
        # Test if ffmpeg is accessible
        subprocess.run(["ffmpeg", "-version"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except FileNotFoundError:
        try:
            # Attempt automatic installation via winget (Gyan.FFmpeg is a standard Windows build)
            subprocess.run(["winget", "install", "Gyan.FFmpeg", "--accept-source-agreements", "--accept-package-agreements"], 
                          capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            messagebox.showinfo("Installing FFmpeg", "FFmpeg was missing and is being installed via Winget.\nPlease restart this app once the installation completes.")
        except Exception as e:
            # Fallback if winget fails or is not available
            messagebox.showwarning("FFmpeg Missing", "FFmpeg is required for MP3 support but could not be installed automatically.\nPlease install FFmpeg manually.")

# Try importing pydub for audio manipulation and silence detection
try:
    from pydub import AudioSegment
    from pydub.silence import detect_nonsilent
except ImportError:
    pass

class AudioSlicerApp:
    """
    Main application class for the Piper Dataset Slicer.
    Provides a GUI for loading audio files, visualizing waveforms,
    and manually or automatically slicing audio into segments for training.
    """
    def __init__(self, root):
        self.root = root
        self.root.title("Piper Dataset Slicer")
        self.root.geometry("1000x800")
        
        # Force window to front on launch - use multiple methods for reliability
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.update()
        self.root.focus_force()
        self.root.after(100, lambda: [
            self.root.attributes("-topmost", False),
            self.root.focus_set()
        ])

        # Audio State Data
        self.audio = None
        self.samples = None
        self.sample_rate = 0
        self.duration_ms = 0
        self.file_path = None
        self.temp_wav = "temp_playback.wav" # Temporary file for audio playback
        
        # Playback State
        self.is_playing = False
        self.current_playback_start_timestamp = 0 
        self.playback_offset = 0 # ms where we started playing from
        self._play_token = 0 # Unique ID for each playback session to prevent races
        # Monotonic token incremented on each play/stop.
        # Lets background playback threads detect that they've been superseded.
        self._play_token = 0
        
        # Slicing Data
        self.segments = [] # List of (start_ms, end_ms) timestamps
        self.segment_voice_ids = None  # Optional list aligned to segments for multi-speaker datasets
        
        # Visualization & Interaction State
        self.zoom_level = 100 # Horizontal scale: pixels per second
        self.view_offset_ms = 0 # Start time of the currently visible waveform window
        self.view_width_px = 0 # Updated dynamicallly during resize
        self.selection_start_ms = None # Start of the user's manual selection
        self.selection_end_ms = None # End of the user's manual selection
        self.drag_mode = None # Tracks whether user is creating, moving, or resizing a selection

        # CLI-based state initialization
        self.dataset_dir = None
        self.voice_name = None
        self.parse_cli_args()
        
        self.setup_ui()
        
        # Bind events for responsive UI
        self.waveform_canvas.bind("<Configure>", self.on_canvas_resize)
        
        # Start the background loop that keeps the playback cursor moving
        self.update_playback_cursor()

    def parse_cli_args(self):
        """
        Handles command-line arguments if the tool is launched from another script.
        Supported args: --dataset_dir, --voice_name
        """
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--dataset_dir", help="Path to the dataset directory")
        parser.add_argument("--voice_name", help="Name of the voice project")
        args, unknown = parser.parse_known_args()
        
        if args.dataset_dir:
            self.dataset_dir = args.dataset_dir
            # Ensure the output directory exists
            try: os.makedirs(self.dataset_dir, exist_ok=True)
            except: pass
        
        if args.voice_name:
            self.voice_name = args.voice_name
            self.root.title(f"Piper Dataset Slicer - {self.voice_name}")

    def setup_ui(self):
        """
        Initializes the GUI layout using Tkinter's ttk widgets.
        Organized into frames: Load Bar, Waveform Display, Controls, and Segment List.
        """
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # --- Section 1: Top Bar (File Loading & Workflow Navigation) ---
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Button(top_frame, text="📂 Load Audio File", command=self.load_file).pack(side="left")
        self.file_label = ttk.Label(top_frame, text="No file loaded", foreground="#666")
        self.file_label.pack(side="left", padx=10)

        # "Next" button specifically for being called from automated workflows
        if self.dataset_dir:
            ttk.Button(top_frame, text="➡️ Next: Transcribe", command=self.go_to_transcribe).pack(side="right")
        
        # --- Section 2: Waveform Visualization Area ---
        wave_frame = ttk.LabelFrame(main_frame, text="Waveform (Drag to Select)", padding="5")
        wave_frame.pack(fill="x", pady=5)
        
        self.waveform_canvas = tk.Canvas(wave_frame, height=200, bg="#1e1e1e", highlightthickness=0)
        self.waveform_canvas.pack(fill="x", expand=True)
        
        # Horizontal scrollbar for navigating through long audio files
        self.h_scroll = ttk.Scrollbar(wave_frame, orient="horizontal", command=self.on_scroll)
        self.h_scroll.pack(fill="x", pady=(2,0))
        
        # Interaction events for the canvas (selection, zooming, scrolling)
        self.waveform_canvas.bind("<Button-1>", self.on_click)
        self.waveform_canvas.bind("<B1-Motion>", self.on_drag)
        self.waveform_canvas.bind("<ButtonRelease-1>", self.on_release)
        self.waveform_canvas.bind("<Motion>", self.on_hover)
        self.waveform_canvas.bind("<Button-3>", self.on_right_click)  # Right-click seek
        self.waveform_canvas.bind("<MouseWheel>", self.on_zoom) # Windows systems
        self.waveform_canvas.bind("<Button-4>", self.on_zoom) # Linux: scroll up
        self.waveform_canvas.bind("<Button-5>", self.on_zoom) # Linux: scroll down

        # --- Section 3: Time & Selection Metrics ---
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill="x", pady=5)
        
        # Large clock for current seek position
        self.time_label = ttk.Label(info_frame, text="00:00.000", font=("Consolas", 18, "bold"))
        self.time_label.pack(side="left")
        
        # Display selected duration/range info
        self.sel_label = ttk.Label(info_frame, text="Selection: None", font=("Consolas", 12))
        self.sel_label.pack(side="right")

        # --- Section 4: Main Controls ---
        ctrl_frame = ttk.Frame(main_frame)
        ctrl_frame.pack(fill="x", pady=10)
        
        # Playback control
        self.play_btn = ttk.Button(ctrl_frame, text="▶ Play (Space)", command=self.toggle_play, state="disabled")
        self.play_btn.pack(side="left", padx=5)
        
        # Context-sensitive playback button
        self.play_sel_btn = ttk.Button(ctrl_frame, text="Length: --", command=self.play_selection, state="disabled")
        self.play_sel_btn.pack(side="left", padx=5)

        ttk.Separator(ctrl_frame, orient="vertical").pack(side="left", padx=10, fill="y")
        
        # Slicing tools
        self.add_sel_btn = ttk.Button(ctrl_frame, text="➕ Add Selection to List (Enter)", command=self.add_selection, state="disabled")
        self.add_sel_btn.pack(side="left", padx=5)
        
        ttk.Button(ctrl_frame, text="Clear (Esc)", command=self.clear_selection).pack(side="left", padx=5)
        
        ttk.Separator(ctrl_frame, orient="vertical").pack(side="left", padx=10, fill="y")
        
        # Automation & Analysis tools
        ttk.Button(ctrl_frame, text="⚡ Auto-Detect Silence", command=self.auto_detect).pack(side="left", padx=5)
        ttk.Button(ctrl_frame, text="🎙️ Filter by Voice", command=self.filter_by_voice).pack(side="left", padx=5)
        ttk.Button(ctrl_frame, text="🧑‍🤝‍🧑 Split by Voice Changes", command=self.split_by_voice_changes).pack(side="left", padx=5)
        ttk.Button(ctrl_frame, text="🏷️ Label Voices", command=self.categorize_voices).pack(side="left", padx=5)
        
        # --- Section 5: Segment Management List ---
        list_frame = ttk.LabelFrame(main_frame, text="Segments (Select Multi to Merge)", padding="5")
        list_frame.pack(fill="both", expand=True, pady=5)
        
        self.seg_list = tk.Listbox(list_frame, height=8, font=("Consolas", 10), selectmode="extended")
        self.seg_list.pack(fill="both", expand=True, side="left")
        
        # List interactions
        self.seg_list.bind("<Double-Button-1>", self.restore_segment_from_list) # Seek to segment on double click
        self.seg_list.bind("<Delete>", lambda e: self.remove_segment_item())
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.seg_list.yview)
        scrollbar.pack(side="right", fill="y")
        self.seg_list.config(yscrollcommand=scrollbar.set)
        
        # Context menu for right-clicking individual segments
        self.list_menu = tk.Menu(self.root, tearoff=0)
        self.list_menu.add_command(label="Play Segment", command=lambda: self.restore_segment_from_list(None) or self.play_selection())
        self.list_menu.add_command(label="Delete", command=self.remove_segment_item)
        self.list_menu.add_separator()
        self.list_menu.add_command(label="Merge Selected", command=self.merge_segments_clicked)
        self.list_menu.add_command(label="Merge Small Gaps (All)...", command=self.merge_small_gaps_all)
        self.list_menu.add_command(label="Remove Short Segments (All)...", command=self.remove_short_segments_all)
        self.list_menu.add_command(label="Split by Voice Changes...", command=self.split_by_voice_changes)
        self.list_menu.add_command(label="Label Voices...", command=self.categorize_voices)
        
        def do_popup(event):
            """Shows the context menu on right-click."""
            try: self.list_menu.tk_popup(event.x_root, event.y_root)
            finally: self.list_menu.grab_release()
        self.seg_list.bind("<Button-3>", do_popup)
        
        # --- Section 6: Bulk Management Actions ---
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill="x", pady=5)
        
        ttk.Button(bottom_frame, text="Remove Selected", command=self.remove_segment_item).pack(side="left")
        ttk.Button(bottom_frame, text="Merge Selected", command=self.merge_segments_clicked).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="Merge Small Gaps (All)...", command=self.merge_small_gaps_all).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="Remove Short (All)...", command=self.remove_short_segments_all).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="EXPORT ALL SEGMENTS", command=self.export_segments).pack(side="right")
        
        # 7. Status Bar
        self.status_var = tk.StringVar()
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill="x")

        # Global Keys
        self.root.bind("<space>", lambda e: self.toggle_play())
        self.root.bind("<Return>", lambda e: self.add_selection())
        self.root.bind("<Escape>", lambda e: self.clear_selection())
        
    def log(self, msg):
        """Updates the status bar with a message."""
        self.status_var.set(msg)

    def _invalidate_voice_labels(self):
        """Clears voice grouping/labeling data when the dataset changes."""
        self.segment_voice_ids = None

    def _ensure_numpy(self):
        """
        Attempts to import and use numpy for high-performance audio processing.
        If missing, offers to install it via pip.
        """
        global np
        if np is not None:
            return True

        try:
            import numpy as _np
            np = _np
            return True
        except Exception:
            pass

        if messagebox.askyesno("Dependency Missing", "This feature needs 'numpy'. Install it now?"):
            try:
                # Use current interpreter to install numpy
                py_exe = sys.executable.replace("pythonw.exe", "python.exe")
                flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                subprocess.check_call([py_exe, "-m", "pip", "install", "numpy"], creationflags=flags)
                import numpy as _np
                np = _np
                return True
            except Exception as e:
                messagebox.showerror("Install Failed", str(e))
        return False

    def _dot(self, a, b):
        """Helper for computing dot products, uses numpy if available, otherwise pure Python."""
        if np is not None:
            return float(np.dot(a, b))
        return float(sum((float(x) * float(y)) for x, y in zip(a, b)))

    def _rebuild_segment_listbox(self):
        """Synchronizes the visible Tkinter Listbox with the internal segments list."""
        self.seg_list.delete(0, tk.END)
        for i, (start, end) in enumerate(self.segments):
            prefix = ""
            # If voice classification info exists, prepend it (e.g., "V1 | ...")
            if self.segment_voice_ids and i < len(self.segment_voice_ids):
                vid = self.segment_voice_ids[i]
                if vid is not None:
                    prefix = f"V{int(vid)} | "
            self.seg_list.insert(tk.END, f"{prefix}{self.format_ms_full(start)} - {self.format_ms_full(end)} | {int(end-start)}ms")

    def load_file(self):
        """
        Prompts user to select an audio file and loads it into memory via pydub.
        Loads occur in a background thread to keep the UI responsive for large files.
        """
        path = filedialog.askopenfilename(filetypes=[("Audio Files", "*.mp3 *.wav *.ogg *.flac *.m4a")])
        if not path: return

        # Trigger ffmpeg check for compressed formats
        ext = os.path.splitext(path)[1].lower()
        if ext in {".mp3", ".m4a", ".ogg", ".flac"}:
            try:
                ensure_ffmpeg()
            except Exception:
                pass
        
        self.log(f"Loading {os.path.basename(path)}... this may take a moment.")
        self.root.update()
        
        def _load():
            try:
                self.file_path = path
                self.audio = AudioSegment.from_file(path)
                self.duration_ms = len(self.audio)
                self.sample_rate = self.audio.frame_rate
                self.segments = []
                self._invalidate_voice_labels()
                
                # --- Audio Sample Data Extraction for Visualization ---
                self.log("Processing waveform data...")
                raw_data = self.audio.raw_data
                
                if np is not None:
                    # Optimized loading using numpy
                    dtype = np.int16
                    if self.audio.sample_width == 4:
                        dtype = np.int32
                    elif self.audio.sample_width == 1:
                        dtype = np.int8

                    self.samples = np.frombuffer(raw_data, dtype=dtype)
                    # Convert to mono if necessary by taking only the first channel
                    if self.audio.channels > 1:
                        self.samples = self.samples[:: self.audio.channels]
                else:
                    # Fallback to standard Python arrays
                    try:
                        self.samples = self.audio.get_array_of_samples()
                        if self.audio.channels > 1:
                            self.samples = self.samples[:: self.audio.channels]
                    except Exception:
                        self.samples = None
                
                # Update UI on the main thread after loading
                self.root.after(0, self.finish_load)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to load: {e}"))
                
        threading.Thread(target=_load, daemon=True).start()

    def finish_load(self):
        """Finalizes UI state once audio data is successfully loaded into memory."""
        self.file_label.config(text=f"{os.path.basename(self.file_path)} ({self.duration_ms/1000:.1f}s)")
        self.play_btn.config(state="normal")
        self.log("Ready.")
        self.seg_list.delete(0, tk.END)
        self.playback_offset = 0
        self.view_offset_ms = 0
        self.zoom_level = 50 # Start with a reasonable zoom level

        # Force a layout update to ensure we have valid dimensions for drawing
        try:
            self.root.update_idletasks()
            w = self.waveform_canvas.winfo_width()
            if w and w > 1:
                self.view_width_px = w
        except Exception:
            pass

        self.full_redraw()

    # --- Waveform Logic & Drawing ---
    
    def ms_to_x(self, ms):
        """Converts a timestamp (ms) to a relative X coordinate on the canvas."""
        rel_ms = ms - self.view_offset_ms
        return (rel_ms / 1000.0) * self.zoom_level

    def x_to_ms(self, x):
        """Converts a canvas X coordinate to an absolute timestamp (ms)."""
        rel_ms = (x / self.zoom_level) * 1000.0
        return self.view_offset_ms + rel_ms

    def on_canvas_resize(self, event):
        """Handles canvas resizing by updating stored width and redrawing the waveform."""
        self.view_width_px = event.width
        if self.audio:
            self.draw_waveform()
            self.update_scroll_view()

    def draw_waveform(self):
        """
        Renders the audio waveform onto the canvas based on current zoom and scroll position.
        Uses a decimated representation of the samples for performance.
        """
        self.waveform_canvas.delete("wave")
        self.waveform_canvas.delete("grid")
        
        if self.audio is None or self.samples is None:
            return

        width = self.view_width_px if self.view_width_px and self.view_width_px > 1 else self.waveform_canvas.winfo_width()
        if not width or width <= 1:
            return

        # Vertical setup
        height = self.waveform_canvas.winfo_height()
        mid_y = height / 2
        
        # Calculate time range currently visible in the horizontal viewport
        visible_duration_ms = (width / self.zoom_level) * 1000.0
        start_ms = self.view_offset_ms
        end_ms = start_ms + visible_duration_ms
        
        # Convert time bounds to sample indices
        start_sample = int(start_ms * self.sample_rate / 1000)
        end_sample = int(end_ms * self.sample_rate / 1000)
        
        # Boundary clipping
        if start_sample < 0: start_sample = 0
        if end_sample > len(self.samples): end_sample = len(self.samples)
        
        if end_sample <= start_sample: return # Nothing to render
        
        # Extract the visible subset of audio samples
        chunk = self.samples[start_sample:end_sample]
        
        # Performance optimization: Downsample data to match pixel resolution
        # We aim for roughly one data point per horizontal pixel.
        if len(chunk) > width * 2:
            step = len(chunk) // width
            reduced = chunk[::step] # Simple decimation: fast but can miss narrow peaks
        else:
            reduced = chunk
            
        # Vertical scaling setup (16-bit or 32-bit audio)
        max_amp = 32768 # Standard 16-bit max
        if self.audio.sample_width == 4: max_amp = 2147483648
        
        # Construct the points list for canvas polyline
        points = []
        x_step = width / len(reduced)
        
        for i, val in enumerate(reduced):
            x = i * x_step
            # Normalize and scale to fit mid_y
            y_norm = val / max_amp
            y = mid_y - (y_norm * (height / 2) * 0.95) # 95% height padding
            points.append(x)
            points.append(y)
            
        if len(points) > 4:
            self.waveform_canvas.create_line(points, fill="#00aaff", tags="wave")
            
        # --- Time Grid Rendering ---
        # Adjust grid interval based on zoom level to prevent clutter
        grid_step_s = 1
        if self.zoom_level < 20: grid_step_s = 5
        if self.zoom_level < 5: grid_step_s = 10
        if self.zoom_level > 150: grid_step_s = 0.5
        
        first_sec = math.ceil(start_ms / 1000)
        current_sec = first_sec
        while (current_sec * 1000) < end_ms:
            x = self.ms_to_x(current_sec * 1000)
            # Vertical tic line
            self.waveform_canvas.create_line(x, 0, x, height, fill="#333", dash=(2, 2), tags="grid")
            # Timestamp label
            self.waveform_canvas.create_text(x + 2, height - 10, text=f"{current_sec}s", anchor="w", fill="#666", font=("Arial", 8), tags="grid")
            current_sec += grid_step_s

        # Redraw transient elements (selection, cursor, etc)
        self.draw_overlays()

    def draw_overlays(self):
        """Renders non-waveform static/dynamic elements: saved segments, current selection, and cursor."""
        # Clear existing transient visual objects
        self.waveform_canvas.delete("cursor")
        self.waveform_canvas.delete("selection")
        self.waveform_canvas.delete("saved_seg")
        
        height = self.waveform_canvas.winfo_height()

        # --- Render Saved Segments ---
        for start, end in self.segments:
            s_x = self.ms_to_x(start)
            e_x = self.ms_to_x(end)
            
            # Skip if segment is completely outside the current view
            if e_x < 0 or s_x > self.view_width_px:
                continue
                
            # Draw a dashed rectangle around saved segments
            self.waveform_canvas.create_rectangle(s_x, 0, e_x, height, 
                                                fill="", outline="#00ff00", width=1, dash=(2,4), tags="saved_seg")

        # --- Render Active Selection ---
        if self.selection_start_ms is not None and self.selection_end_ms is not None:
            s_x = self.ms_to_x(self.selection_start_ms)
            e_x = self.ms_to_x(self.selection_end_ms)
            
            x1 = min(s_x, e_x)
            x2 = max(s_x, e_x)
            
            self.waveform_canvas.create_rectangle(x1, 0, x2, height, fill="#ffffff", stipple="gray25", outline="#ffff00", width=2, tags="selection")
            
        # Draw Play Head
        if not self.is_playing:
            cursor_x = self.ms_to_x(self.playback_offset)
        else:
            elapsed = (time.time() - self.current_playback_start_timestamp) * 1000
            cursor_x = self.ms_to_x(self.playback_offset + elapsed)
            
        if 0 <= cursor_x <= self.view_width_px:
            self.waveform_canvas.create_line(cursor_x, 0, cursor_x, height, fill="#ff0000", width=2, tags="cursor")

    def full_redraw(self):
        self.draw_waveform()
        self.update_scroll_view()

    # --- Interaction ---

    def on_hover(self, event):
        """Updates the mouse cursor icon when hovering over selection edges."""
        if not self.audio: return
        # Check if near edges of an existing selection
        if self.selection_start_ms is None or self.selection_end_ms is None:
            self.waveform_canvas.config(cursor="")
            return

        x = event.x
        # Convert ms boundaries to pixel coordinates
        s_x = self.ms_to_x(self.selection_start_ms)
        e_x = self.ms_to_x(self.selection_end_ms)
        
        # Ensure x1 < x2 for comparison
        x1 = min(s_x, e_x)
        x2 = max(s_x, e_x)
        
        threshold = 10 
        
        if abs(x - x1) < threshold or abs(x - x2) < threshold:
            # Change cursor to indicate horizontal resizing is possible
            self.waveform_canvas.config(cursor="sb_h_double_arrow")
        else:
            self.waveform_canvas.config(cursor="")

    def on_click(self, event):
        """Handles mouse down: starts new selection, resizes, or seeks playback."""
        if not self.audio: return
        ms = self.x_to_ms(event.x)
        x = event.x
        
        # Default to new selection mode
        self.drag_mode = "new"
        
        # Check if we clicked on the boundary of an existing selection
        if self.selection_start_ms is not None and self.selection_end_ms is not None:
             s_x = self.ms_to_x(self.selection_start_ms)
             e_x = self.ms_to_x(self.selection_end_ms)
             
             curr_start = min(self.selection_start_ms, self.selection_end_ms)
             curr_end = max(self.selection_start_ms, self.selection_end_ms)
             
             x1 = self.ms_to_x(curr_start)
             x2 = self.ms_to_x(curr_end)
             
             threshold = 10
             
             if abs(x - x1) < threshold:
                 self.drag_mode = "resize_start"
                 self.selection_start_ms = curr_start
                 self.selection_end_ms = curr_end
             elif abs(x - x2) < threshold:
                 self.drag_mode = "resize_end"
                 self.selection_start_ms = curr_start
                 self.selection_end_ms = curr_end
        
        if self.drag_mode == "new":
            self.click_start_ms = ms
            
            # Pause audio and move playhead to the clicked point
            if self.is_playing:
                self.stop()
            
            self.playback_offset = ms
            if self.playback_offset < 0: self.playback_offset = 0
            if self.playback_offset > self.duration_ms: self.playback_offset = self.duration_ms
            
            # Initialize new selection bounds
            self.selection_start_ms = ms
            self.selection_end_ms = ms 
            
        self.draw_overlays()
        self.update_info()

    def on_right_click(self, event):
        """Seeks the playhead to the clicked point without affecting the selection."""
        if not self.audio: return
        ms = self.x_to_ms(event.x)
        
        # Stop playback if running to keep UI/Audio in sync
        if self.is_playing:
            self.stop()
            
        self.playback_offset = max(0, min(self.duration_ms, ms))
        self.draw_overlays()
        self.update_info()

    def on_drag(self, event):
        """Updates the selection range boundaries as the user drags the mouse."""
        if not self.audio: return
        ms = self.x_to_ms(event.x)
        
        # Clamp selection to the audio file boundaries
        if ms < 0: ms = 0
        if ms > self.duration_ms: ms = self.duration_ms

        # Update the correct boundary based on drag mode (start, end, or new)
        if self.drag_mode == "resize_start":
             self.selection_start_ms = ms
        elif self.drag_mode == "resize_end":
             self.selection_end_ms = ms
        else: # drag_mode == "new"
             self.selection_end_ms = ms
        
        self.draw_overlays()
        self.update_info()

    def on_release(self, event):
        """Finalizes the user's manual selection on mouse button release."""
        if not self.audio: return
        # Normalize: ensure start_ms < end_ms
        if self.selection_start_ms is not None and self.selection_end_ms is not None:
            start = min(self.selection_start_ms, self.selection_end_ms)
            end = max(self.selection_start_ms, self.selection_end_ms)
            
            # Discard selection if it's too short (likely a stray click)
            if (end - start) < 100: # 100ms threshold
                self.selection_start_ms = None
                self.selection_end_ms = None
            else:
                self.selection_start_ms = start
                self.selection_end_ms = end
        
        self.draw_overlays()
        self.update_info()

    def on_zoom(self, event):
        """Modifies the horizontal zoom level based on mouse wheel input."""
        if not self.audio: return
        
        # Determine zoom direction: Up/Forward = In, Down/Backward = Out
        if event.num == 5 or event.delta < 0: # Zoom Out
            factor = 0.8
        else: # Zoom In
            factor = 1.25
            
        old_zoom = self.zoom_level
        self.zoom_level *= factor
        
        # Clamp zoom to prevent rendering issues or extreme magnification
        if self.zoom_level < 1: self.zoom_level = 1
        if self.zoom_level > 1000: self.zoom_level = 1000
        
        # Adjust view offset so the zoom feels centered on the current screen middle
        center_x = self.view_width_px / 2
        center_ms = self.x_to_ms(center_x)
        
        new_visible_duration = (self.view_width_px / self.zoom_level) * 1000
        self.view_offset_ms = center_ms - (new_visible_duration / 2)
        
        if self.view_offset_ms < 0: self.view_offset_ms = 0
        
        self.full_redraw()

    def on_scroll(self, *args):
        """Pans the waveform horizontally based on scrollbar interaction."""
        if not self.audio: return
        op = args[0]
        if op == "moveto":
            # Jump-to-location via scrollbar thumb drag
            fraction = float(args[1])
            self.view_offset_ms = fraction * self.duration_ms
        elif op == "scroll":
            # Step-wise scroll via scrollbar arrows
            count = int(args[1])
            visible_duration = (self.view_width_px / self.zoom_level) * 1000
            step = visible_duration * 0.1 # 10% scroll increment
            self.view_offset_ms += count * step
            
        # Bound the horizontal scroll position
        if self.view_offset_ms < 0: self.view_offset_ms = 0
        if self.view_offset_ms > self.duration_ms: self.view_offset_ms = self.duration_ms
        
        self.draw_waveform()
        # Direct scrollbar update for immediate feedback
        self.h_scroll.set(self.view_offset_ms / self.duration_ms, (self.view_offset_ms + ((self.view_width_px / self.zoom_level) * 1000)) / self.duration_ms)

    def update_scroll_view(self):
        """Refreshes the scrollbar position and handle width to match the current view extent."""
        if not self.audio: return
        visible_duration = (self.view_width_px / self.zoom_level) * 1000
        start_frac = self.view_offset_ms / self.duration_ms
        end_frac = min(1.0, (self.view_offset_ms + visible_duration) / self.duration_ms)
        self.h_scroll.set(start_frac, end_frac)

    def update_info(self):
        """Updates time-based labels and enables/disables selection-dependent buttons."""
        # Calculate current position shown on the clock
        ms = self.playback_offset
        if self.is_playing:
            # Interpolate clock between redraws
            ms = self.playback_offset + (time.time() - self.current_playback_start_timestamp) * 1000
            
        self.time_label.config(text=self.format_ms_full(ms))
        
        # Update selection summary details
        if self.selection_start_ms is not None:
             dur = self.selection_end_ms - self.selection_start_ms
             self.sel_label.config(text=f"Selection: {self.format_ms(self.selection_start_ms)} - {self.format_ms(self.selection_end_ms)} ({int(dur)}ms)")
             self.add_sel_btn.config(state="normal")
             self.play_sel_btn.config(state="normal", text=f"Play Sel ({dur/1000:.1f}s)")
        else:
            self.sel_label.config(text="Selection: None")
            self.add_sel_btn.config(state="disabled")
            self.play_sel_btn.config(state="disabled", text="Play Sel")

    def format_ms(self, ms):
        """Helper: Formats milliseconds into canonical MM:SS format."""
        seconds = int(ms / 1000)
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins:02}:{secs:02}"
        
    def format_ms_full(self, ms):
        """Helper: Formats milliseconds into precise MM:SS.mmm format."""
        if ms < 0: ms = 0
        seconds = int(ms / 1000)
        mins = seconds // 60
        secs = seconds % 60
        frac = int(ms % 1000)
        return f"{mins:02}:{secs:02}.{frac:03}"

    # --- Feature Actions ---

    def auto_detect(self):
        """
        Initiates an automated search for non-silent speech segments within the track.
        Results are processed in a separate thread.
        """
        if not self.audio: return
        
        # Display configuration dialog for detection sensitivity
        params = AskAutoParams(self.root)
        self.root.wait_window(params.top)
        if not params.result: return
        
        min_len, thresh_offset = params.result
        
        # Guard against accidental data loss
        if self.segments:
            if not messagebox.askyesno("Confirm Auto-Detect", "This will clear your current segment list. Continue?"):
                return
        
        self.log(f"Auto-detecting (min_len={min_len}ms, thresh={thresh_offset}dB)...")
        self.root.update()
        
        def work():
            try:
                # Calculate silence threshold based on average track loudness
                db_thresh = self.audio.dBFS + thresh_offset
                
                start_time = time.time()
                # Run pydub's detection algorithm
                ranges = detect_nonsilent(
                    self.audio,
                    min_silence_len=int(min_len),
                    silence_thresh=db_thresh,
                    seek_step=5
                )
                dt = time.time() - start_time
                print(f"Detection took {dt:.2f}s")
                
                # Apply changes on the main thread
                self.root.after(0, lambda: self._apply_auto_detect(ranges))
            except Exception as e:
                def show_err():
                    messagebox.showerror("Error", f"Detection failed: {e}")
                    self.log("Detection failed.")
                self.root.after(0, show_err)
        
        threading.Thread(target=work, daemon=True).start()

    # _apply_auto_detect is part of AudioSlicerApp, just fixing indentation of paste above

    def _apply_auto_detect(self, ranges):
        self.segments = []
        self._invalidate_voice_labels()
        self.seg_list.delete(0, tk.END)
        
        count = 0
        pad = 200 # ms padding
        
        for start, end in ranges:
            # Add padding
            start = max(0, start - pad)
            end = min(self.duration_ms, end + pad)
            
            # Avoid short blips
            if (end - start) < 500: continue
            
            self.segments.append((start, end))
            self.seg_list.insert(tk.END, f"{self.format_ms_full(start)} - {self.format_ms_full(end)} | {int(end-start)}ms")
            count += 1
            
        self.log(f"Auto-detected {count} segments.")
        self.full_redraw()
        
    def filter_by_voice(self):
        """
        Filters existing segments based on their similarity to a reference speaker's voice.
        Uses Resemblyzer to compute neural speaker embeddings and compares them.
        """
        # Lazy initialization of numpy
        global np
        if np is None:
            try:
                import numpy as _np
                np = _np
            except ImportError:
                np = None

        # Check for resemblyzer and torch (heavy AI dependencies)
        try:
            from resemblyzer import VoiceEncoder, preprocess_wav
        except ImportError:
            if messagebox.askyesno("Dependency Missing", "Voice filtering requires 'resemblyzer' and 'torch'. Install them now? (This may take a moment)"):
                self.log("Installing dependencies...")
                self.root.update()
                try:
                    # Dynamically install missing packages via pip
                    py_exe = sys.executable.replace("pythonw.exe", "python.exe")
                    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    subprocess.check_call([py_exe, "-m", "pip", "install", "resemblyzer", "torch", "requests", "numpy"], creationflags=flags)
                    messagebox.showinfo("Installed", "Dependencies installed. Please click 'Filter by Voice' again.")
                except Exception as e:
                    messagebox.showerror("Install Failed", str(e))
                self.log("Ready.")
            return

        if np is None:
            # Final check for numpy before proceeding with vector math
            if messagebox.askyesno(
                "Dependency Missing",
                "Voice filtering needs 'numpy' for similarity scoring. Install it now?",
            ):
                self.log("Installing numpy...")
                self.root.update()
                try:
                    py_exe = sys.executable.replace("pythonw.exe", "python.exe")
                    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    subprocess.check_call([py_exe, "-m", "pip", "install", "numpy"], creationflags=flags)
                    import numpy as _np
                    np = _np
                except Exception as e:
                    self.log("Ready.")
                    messagebox.showerror("Install Failed", str(e))
                    return
                self.log("Ready.")
            else:
                return

        if not self.segments:
            messagebox.showinfo("Info", "No segments to filter. Run Auto-Detect or add segments first.")
            return

        ref_path = None
        is_temp_ref = False

        # --- Select Reference Voice ---
        # Option 1: Use the user's current manual selection as the reference sample
        if self.selection_start_ms is not None and self.selection_end_ms is not None:
            s_start = min(self.selection_start_ms, self.selection_end_ms)
            s_end = max(self.selection_start_ms, self.selection_end_ms)
            if (s_end - s_start) > 500: # 0.5s minimum for a valid embedding
                if messagebox.askyesno("Filter using Selection", "Use the currently selected audio region as the target voice reference?"):
                    try:
                        ref_path = "temp_ref_voice.wav"
                        self.audio[int(s_start):int(s_end)].export(ref_path, format="wav")
                        is_temp_ref = True
                    except Exception as e:
                        messagebox.showerror("Error", f"Failed to export selection: {e}")
                        return

        # Option 2: Allow user to browse for a reference WAV file
        if not ref_path:
            ref_path = filedialog.askopenfilename(title="Select Sample Clip of Target Speaker", filetypes=[("Audio", "*.wav *.mp3 *.flac")])
        
        if not ref_path: return

        # Configure filtering mode (Isolate or Exclude) and sensitivity
        mode_params = AskFilterParams(self.root)
        self.root.wait_window(mode_params.top)
        if not mode_params.result: return
        
        threshold, mode = mode_params.result # mode determines if we keep matches or the opposite

        self.log("Initializing AI Model... (first time runs slow)")
        self.root.update()

        def work():
            """Background worker for heavy embedding computations."""
            try:
                encoder = VoiceEncoder()
                
                # Preprocess the reference wav to extract speaker characteristics
                self.log("Processing reference audio...")
                ref_wav = preprocess_wav(ref_path)
                ref_embed = encoder.embed_utterance(ref_wav)
                
                new_segments = []
                kept_count = 0
                total = len(self.segments)
                
                # Intermediate file used to feed individual segments into the encoder
                temp_seg_file = "temp_seg_check.wav"
                
                for i, (start, end) in enumerate(self.segments):
                    # Tracking progress in the status bar
                    self.root.after(0, lambda i=i: self.log(f"Analyzing {i+1}/{total}..."))
                    
                    # Temporarily export this segment to WAV for analysis
                    seg_audio = self.audio[int(start):int(end)]
                    seg_audio.export(temp_seg_file, format="wav")
                    
                    # Extract embedding for the current segment
                    cand_wav = preprocess_wav(temp_seg_file)
                    cand_embed = encoder.embed_utterance(cand_wav)
                    
                    # Compute similarity using the dot product (cosine similarity since embeddings are normalized)
                    sim = self._dot(ref_embed, cand_embed)
                    
                    # Filter logic: does this segment match the speaker?
                    match = sim > threshold
                    keep = False
                    if mode == "keep" and match: keep = True # Isolate this person
                    if mode == "remove" and not match: keep = True # Exclude this person
                    
                    if keep: 
                        new_segments.append((start, end))
                        kept_count += 1
                
                # --- Cleanup Workspace ---
                if os.path.exists(temp_seg_file):
                    try: os.remove(temp_seg_file)
                    except: pass
                if is_temp_ref and ref_path and os.path.exists(ref_path):
                    try: os.remove(ref_path)
                    except: pass
                
                # Update the segment list in the UI on the main thread
                def commit():
                    self.segments = []
                    self.seg_list.delete(0, tk.END)
                    for s, e in new_segments:
                        self.segments.append((s,e))
                        self.seg_list.insert(tk.END, f"{self.format_ms_full(s)} - {self.format_ms_full(e)} | {int(e-s)}ms")
                    self.full_redraw()
                    self.log(f"Filter complete. Kept {kept_count} of {total} segments.")
                    messagebox.showinfo("Filter Complete", f"Kept {kept_count} segments matching the reference voice.")

                self.root.after(0, commit)

            except Exception as e:
                print(e)
                self.root.after(0, lambda: messagebox.showerror("Filter Error", str(e)))
                self.root.after(0, lambda: self.log("Filter failed."))

        # Spawn processing thread
        threading.Thread(target=work, daemon=True).start()

    def split_by_voice_changes(self):
        """
        Splits existing audio segments whenever a change in speaker is detected.
        Utilizes sliding window embeddings to identify boundaries where similarity drops.
        """
        if not self.audio:
            messagebox.showinfo("Info", "Load an audio file first.")
            return

        # Ensure mathematical dependencies are present
        if not self._ensure_numpy():
            return

        # Check for resemblyzer and torch
        try:
            from resemblyzer import VoiceEncoder, preprocess_wav
        except ImportError:
            if messagebox.askyesno(
                "Dependency Missing",
                "Voice splitting requires 'resemblyzer' and 'torch'. Install them now? (This may take a moment)",
            ):
                self.log("Installing dependencies...")
                self.root.update()
                try:
                    py_exe = sys.executable.replace("pythonw.exe", "python.exe")
                    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    subprocess.check_call(
                        [py_exe, "-m", "pip", "install", "resemblyzer", "torch", "requests", "numpy"],
                        creationflags=flags,
                    )
                    messagebox.showinfo("Installed", "Dependencies installed. Please click 'Split by Voice Changes' again.")
                except Exception as e:
                    messagebox.showerror("Install Failed", str(e))
                self.log("Ready.")
            return

        # --- Request User Configuration for Heuristic ---
        # Window size: length of audio to consider for one 'voice fingerprint'
        win_s = simpledialog.askfloat(
            "Split by Voice Changes",
            "Embedding window size (seconds).\n\nTypical: 1.0 to 2.0\nSmaller = faster reactions but noisier.",
            initialvalue=1.5,
            minvalue=0.3,
        )
        if win_s is None:
            return

        # Hop size: distance to slide the window forward between checks
        hop_s = simpledialog.askfloat(
            "Split by Voice Changes",
            "Hop size (seconds) between windows.\n\nTypical: 0.5\nSmaller = more accurate but slower.",
            initialvalue=min(0.5, float(win_s)),
            minvalue=0.1,
        )
        if hop_s is None:
            return

        if hop_s > win_s:
            messagebox.showwarning("Invalid", "Hop size must be <= window size.")
            return

        # Threshold for considering two adjacent windows as the same speaker
        thresh = simpledialog.askfloat(
            "Split by Voice Changes",
            "Similarity threshold (0..1).\n\nLower = fewer splits. Higher = more splits.\nTypical: 0.70 to 0.85",
            initialvalue=0.78,
            minvalue=0.0,
            maxvalue=1.0,
        )
        if thresh is None:
            return

        # Minimum required duration for any resulting sub-segment
        min_seg_s = simpledialog.askfloat(
            "Split by Voice Changes",
            "Minimum segment length (seconds).\nSegments shorter than this will be merged into neighbors.",
            initialvalue=1.0,
            minvalue=0.0,
        )
        if min_seg_s is None:
            return

        # Determine if we are splitting inside already identified segments or the whole file
        base_segments = [(0.0, float(self.duration_ms))]
        if self.segments:
            if messagebox.askyesno(
                "Use Existing Segments?",
                "You already have segments. Split by voice inside those segments (recommended)?\n\nChoose 'No' to split the entire file instead.",
            ):
                base_segments = [(float(s), float(e)) for s, e in self.segments]

        self.log("Initializing AI Model... (first time runs slow)")
        self.root.update()

        def work():
            """Background worker for embedding-based change detection."""
            temp_full = "temp_full_voice_split.wav"
            try:
                encoder = VoiceEncoder()

                # Export full audio once for processing; splits are computed by time indices
                self.root.after(0, lambda: self.log("Preparing audio for voice split..."))
                self.audio.export(temp_full, format="wav")

                # Handle potential Resemblyzer version inconsistencies in silence trimming
                used_trim_silence = None
                try:
                    wav = preprocess_wav(temp_full, trim_silence=False)
                    used_trim_silence = False
                except TypeError:
                    wav = preprocess_wav(temp_full) # Older versions automatically trim
                    used_trim_silence = True

                # Normalized sample rate for VoiceEncoder
                sr = 16000

                # Convert time parameters to sample counts and milliseconds
                win_n = int(float(win_s) * sr)
                hop_n = int(float(hop_s) * sr)
                min_len_ms = float(min_seg_s) * 1000.0

                new_segments = []
                total_base = len(base_segments)

                for seg_i, (seg_start_ms, seg_end_ms) in enumerate(base_segments):
                    # Progress update
                    self.root.after(0, lambda seg_i=seg_i: self.log(f"Voice-splitting {seg_i+1}/{total_base}..."))

                    # Map time range to sample indices
                    start_idx = int((seg_start_ms / 1000.0) * sr)
                    end_idx = int((seg_end_ms / 1000.0) * sr)
                    start_idx = max(0, start_idx)
                    end_idx = min(len(wav), end_idx)
                    if end_idx <= start_idx:
                        continue

                    seg_wav = wav[start_idx:end_idx]
                    if len(seg_wav) < win_n or win_n <= 0 or hop_n <= 0:
                        new_segments.append((seg_start_ms, seg_end_ms))
                        continue

                    # --- Sliding Window Feature Extraction ---
                    embeddings = []
                    centers_ms = []
                    pos = 0
                    while pos + win_n <= len(seg_wav):
                        window = seg_wav[pos:pos + win_n]
                        emb = encoder.embed_utterance(window)
                        embeddings.append(emb)
                        center_ms = seg_start_ms + (((pos + (win_n / 2.0)) / sr) * 1000.0)
                        centers_ms.append(center_ms)
                        pos += hop_n

                    if len(embeddings) < 2:
                        new_segments.append((seg_start_ms, seg_end_ms))
                        continue

                    # --- Identify Split Points ---
                    boundaries = []
                    last_boundary_ms = seg_start_ms
                    for j in range(1, len(embeddings)):
                        # Compare similarity between consecutive windows
                        sim = self._dot(embeddings[j - 1], embeddings[j])
                        t_ms = float(centers_ms[j])
                        
                        # If similarity drops below threshold, assume a new speaker started
                        if sim < float(thresh) and (t_ms - last_boundary_ms) >= min_len_ms:
                            boundaries.append(t_ms)
                            last_boundary_ms = t_ms

                    # Construct segment tuples from identified boundaries
                    points = [float(seg_start_ms)] + boundaries + [float(seg_end_ms)]
                    segs = [(a, b) for a, b in zip(points, points[1:]) if b > a]

                    # Post-processing: Merge segments that are shorter than the configured minimum
                    merged = []
                    for a, b in segs:
                        if not merged:
                            merged.append([a, b])
                            continue
                        if (b - a) < min_len_ms:
                            merged[-1][1] = b # Extension of previous segment
                        else:
                            merged.append([a, b])

                    new_segments.extend([(float(a), float(b)) for a, b in merged if b > a])

                # Cleanup temp file
                try:
                    if os.path.exists(temp_full):
                        os.remove(temp_full)
                except Exception:
                    pass

                # Apply results to the UI
                def commit():
                    self.segments = new_segments
                    self._rebuild_segment_listbox()
                    self.full_redraw()
                    self.log(f"Voice split complete: {len(self.segments)} segments.")
                    if used_trim_silence:
                        messagebox.showwarning(
                            "Note",
                            "Your installed 'resemblyzer' version didn't accept trim_silence=False.\n"
                            "Timing may be slightly off if it trimmed silence.",
                        )

                self.root.after(0, commit)

            except Exception as e:
                try:
                    if os.path.exists(temp_full):
                        os.remove(temp_full)
                except Exception:
                    pass
                self.root.after(0, lambda: messagebox.showerror("Voice Split Error", str(e)))
                self.root.after(0, lambda: self.log("Voice split failed."))

        threading.Thread(target=work, daemon=True).start()

    def categorize_voices(self):
        """
        Automatically clusters segments into different voices (speakers) using neural embeddings and K-Means.
        Assigns a voice ID (V1, V2, etc.) to each segment for easier filtering of multi-speaker source audio.
        """
        if not self.audio:
            messagebox.showinfo("Info", "Load an audio file first.")
            return
        if not self.segments:
            messagebox.showinfo("Info", "No segments to label. Create segments first.")
            return

        if not self._ensure_numpy():
            return

        try:
            from resemblyzer import VoiceEncoder, preprocess_wav
        except ImportError:
            if messagebox.askyesno(
                "Dependency Missing",
                "Voice labeling requires 'resemblyzer' and 'torch'. Install them now? (This may take a moment)",
            ):
                self.log("Installing dependencies...")
                self.root.update()
                try:
                    py_exe = sys.executable.replace("pythonw.exe", "python.exe")
                    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    subprocess.check_call(
                        [py_exe, "-m", "pip", "install", "resemblyzer", "torch", "requests", "numpy"],
                        creationflags=flags,
                    )
                    messagebox.showinfo("Installed", "Dependencies installed. Please click 'Label Voices' again.")
                except Exception as e:
                    messagebox.showerror("Install Failed", str(e))
                self.log("Ready.")
            return

        # Prompt user for the expected number of speakers
        k = simpledialog.askinteger(
            "Label Voices",
            "How many distinct voices to label?\n\nTypical: 2\n(If more than this are present, some will be grouped.)",
            initialvalue=2,
            minvalue=2,
            maxvalue=8,
        )
        if not k:
            return

        # Voice fingerprints require a minimum duration of audio to be reliable
        min_embed_s = 0.6
        min_embed_ms = min_embed_s * 1000.0

        self.log("Initializing AI Model... (first time runs slow)")
        self.root.update()

        def work():
            """Background worker: Clustering segments by speaker characteristics."""
            temp_full = "temp_full_voice_label.wav"
            try:
                encoder = VoiceEncoder()
                self.root.after(0, lambda: self.log("Preparing audio for voice labeling..."))
                self.audio.export(temp_full, format="wav")

                # Handle Resemblyzer silence-trimming behavior differences across versions
                used_trim_silence = None
                try:
                    wav = preprocess_wav(temp_full, trim_silence=False)
                    used_trim_silence = False
                except TypeError:
                    wav = preprocess_wav(temp_full)
                    used_trim_silence = True

                sr = 16000 # Working sample rate for VoiceEncoder

                # Extract fingerprints (embeddings) for all segments long enough to analyze
                embeds = []
                embed_seg_indices = []
                voice_ids = [None] * len(self.segments)

                total = len(self.segments)
                for i, (start_ms, end_ms) in enumerate(self.segments):
                    self.root.after(0, lambda i=i: self.log(f"Labeling {i+1}/{total}..."))

                    if (float(end_ms) - float(start_ms)) < min_embed_ms:
                        continue

                    start_idx = int((float(start_ms) / 1000.0) * sr)
                    end_idx = int((float(end_ms) / 1000.0) * sr)
                    start_idx = max(0, start_idx)
                    end_idx = min(len(wav), end_idx)
                    if end_idx <= start_idx:
                        continue

                    seg_wav = wav[start_idx:end_idx]
                    emb = encoder.embed_utterance(seg_wav)
                    embeds.append(emb)
                    embed_seg_indices.append(i)

                if not embeds:
                    def noemb():
                        messagebox.showwarning(
                            "Too Short",
                            f"All segments are too short for reliable voice labeling (< {min_embed_s:.1f}s).\n"
                            "Try merging segments first or lowering the split sensitivity.",
                        )
                        self.log("Voice labeling skipped.")
                    self.root.after(0, noemb)
                    return

                # Prepare the embedding matrix for clustering
                X = np.array(embeds, dtype=np.float32)
                # Normalize feature vectors for cosine distance calculations
                norms = np.linalg.norm(X, axis=1, keepdims=True) + 1e-8
                X = X / norms

                k_eff = int(min(int(k), X.shape[0]))

                # --- Simple K-Means Clustering on Embeddings ---
                # Deterministic random state for repeatable (though not perfect) results
                rng = np.random.default_rng(0)
                init_idx = rng.choice(X.shape[0], size=k_eff, replace=False)
                C = X[init_idx].copy() # Centroids

                for _ in range(20): # Iterate to convergence
                    sims = X @ C.T  # Similarity score with each cluster center
                    labels = np.argmax(sims, axis=1) # Assign to nearest cluster

                    new_C = np.zeros_like(C)
                    for ci in range(k_eff):
                        mask = labels == ci
                        if not np.any(mask):
                            new_C[ci] = X[rng.integers(0, X.shape[0])]
                        else:
                            v = np.mean(X[mask], axis=0) # Update center point
                            v = v / (np.linalg.norm(v) + 1e-8)
                            new_C[ci] = v
                    if np.allclose(C, new_C, atol=1e-4):
                        C = new_C
                        break
                    C = new_C

                # Map resulting cluster IDs back to their corresponding segments
                for seg_i, lab in zip(embed_seg_indices, labels):
                    voice_ids[seg_i] = int(lab)

                # Heuristic: fill unlabeled gaps (too short for embeddings) using neighboring labels
                last = None
                for i in range(len(voice_ids)):
                    if voice_ids[i] is None:
                        voice_ids[i] = last
                    else:
                        last = voice_ids[i]
                
                # Fill initial gaps from first found label
                first = next((v for v in voice_ids if v is not None), 0)
                voice_ids = [first if v is None else v for v in voice_ids]

                # Canonical indexing: ensure voice #1 is the first speaker encountered in the timeline
                first_pos = {}
                for i, v in enumerate(voice_ids):
                    first_pos.setdefault(v, i)
                order = [v for v, _ in sorted(first_pos.items(), key=lambda t: t[1])]
                remap = {v: idx + 1 for idx, v in enumerate(order)}
                voice_ids = [remap.get(v, 1) for v in voice_ids]

                # Cleanup temp audio
                try:
                    if os.path.exists(temp_full): os.remove(temp_full)
                except Exception: pass

                def commit():
                    # Update internal state and refresh the UI component
                    self.segment_voice_ids = voice_ids
                    self._rebuild_segment_listbox()
                    self.log(f"Voice labeling complete: {max(voice_ids)} voices.")
                    if used_trim_silence:
                        messagebox.showwarning("Note", " Resemblyzer version auto-trimmed silence; timings may be slightly staggered.")

                self.root.after(0, commit)

            except Exception as e:
                # Cleanup if thread crashes
                try:
                    if os.path.exists(temp_full): os.remove(temp_full)
                except Exception: pass
                self.root.after(0, lambda: messagebox.showerror("Voice Label Error", str(e)))
                self.root.after(0, lambda: self.log("Voice labeling failed."))

        threading.Thread(target=work, daemon=True).start()

    def add_selection(self):
        """Commits the current visual selection to the permanent segments list."""
        if self.selection_start_ms is None or self.selection_end_ms is None: return
        # Ensure start is always before end regardless of drag direction
        start = min(self.selection_start_ms, self.selection_end_ms)
        end = max(self.selection_start_ms, self.selection_end_ms)
        
        # Discard zero-length selections
        if end - start < 10: return
        
        self.segments.append((start, end))
        self._invalidate_voice_labels() # Labels must be re-computed if segments change
        self.seg_list.insert(tk.END, f"{self.format_ms_full(start)} - {self.format_ms_full(end)} | {int(end-start)}ms")
        self.seg_list.see(tk.END) # Auto-scroll to show the new entry
        
    def clear_selection(self):
        """Removes the current visual selection highlight without affecting saved segments."""
        self.selection_start_ms = None
        self.selection_end_ms = None
        self.draw_overlays()
        self.update_info()

    def remove_segment_item(self):
        """Deletes the highlighted segment(s) from the listbox and internal storage."""
        sel = self.seg_list.curselection()
        if not sel: return
        # Process removals in reverse to maintain index integrity
        for idx in reversed(sel):
            self.seg_list.delete(idx)
            self.segments.pop(idx)

        self._invalidate_voice_labels()
        self.full_redraw()

    def _normalize_and_merge_by_gap(self, segments, max_gap_ms):
        """Utility: Unites segments that are separated by a silence shorter than max_gap_ms."""
        if not segments:
            return []

        # Sort segments chronologically before merging
        segs = sorted(((float(s), float(e)) for s, e in segments), key=lambda t: (t[0], t[1]))
        merged = []
        cur_s, cur_e = segs[0]
        
        for s, e in segs[1:]:
            if s <= cur_e:
                # Direct overlap: merge into current
                cur_e = max(cur_e, e)
                continue

            gap = s - cur_e
            if gap <= max_gap_ms:
                # Gap is small enough to be considered continuous audio
                cur_e = max(cur_e, e)
            else:
                # Definitive gap: save current segment and start a new one
                merged.append((cur_s, cur_e))
                cur_s, cur_e = s, e

        merged.append((cur_s, cur_e))
        return merged

    def merge_small_gaps_all(self):
        """Bulk action: Merges all segments separated by short silences."""
        if not self.segments:
            messagebox.showinfo("Info", "No segments to merge.")
            return

        default_s = 1.0
        gap_s = simpledialog.askfloat(
            "Merge Small Gaps",
            "Merge segments when the silence/gap between them is <= how many seconds?\n\nExample: 1.0 will merge segments separated by up to 1 second.",
            initialvalue=default_s,
            minvalue=0.0,
        )
        if gap_s is None:
            return

        max_gap_ms = float(gap_s) * 1000.0
        before = len(self.segments)
        self.segments = self._normalize_and_merge_by_gap(self.segments, max_gap_ms=max_gap_ms)
        after = len(self.segments)

        self._invalidate_voice_labels()
        self._rebuild_segment_listbox()
        self.full_redraw()
        self.log(f"Merged small gaps (<= {gap_s:.3g}s). {before} -> {after} segments.")

    def remove_short_segments_all(self):
        """Bulk action: Filters out any segments whose duration falls below a user-defined threshold."""
        if not self.segments:
            messagebox.showinfo("Info", "No segments to filter.")
            return

        default_s = 1.0
        min_s = simpledialog.askfloat(
            "Remove Short Segments",
            "Remove segments shorter than how many seconds?\n\nExample: 1.0 will remove anything < 1 second.",
            initialvalue=default_s,
            minvalue=0.0,
        )
        if min_s is None:
            return

        min_len_ms = float(min_s) * 1000.0
        before = len(self.segments)
        # Retain only segments that meet the duration criteria
        self.segments = [(s, e) for (s, e) in self.segments if (float(e) - float(s)) >= min_len_ms]
        after = len(self.segments)

        self._invalidate_voice_labels()
        removed = before - after
        self._rebuild_segment_listbox()
        self.full_redraw()
        self.log(f"Removed {removed} short segments (< {min_s:.3g}s).")

    def merge_segments_clicked(self):
        """Manual action: Merges the segments currently selected in the listbox into one single range."""
        sel = self.seg_list.curselection()
        if not sel or len(sel) < 2:
            return # Operation requires multiple selection
        
        indices = sorted([int(i) for i in sel])
        
        # Calculate the absolute start and end of the merged range
        start_ms = float('inf')
        end_ms = float('-inf')
        
        for i in indices:
            s, e = self.segments[i]
            if s < start_ms: start_ms = s
            if e > end_ms: end_ms = e
            
        # Clean up the original sub-segments
        for i in reversed(indices):
            self.seg_list.delete(i)
            self.segments.pop(i)

        self._invalidate_voice_labels()
            
        # Insert the combined segment back into the workflow
        insert_idx = indices[0]
        self.segments.insert(insert_idx, (start_ms, end_ms))
        self.seg_list.insert(insert_idx, f"{self.format_ms_full(start_ms)} - {self.format_ms_full(end_ms)} | {int(end_ms-start_ms)}ms")
        self.seg_list.select_set(insert_idx)
        
        self.full_redraw()

    def restore_segment_from_list(self, event):
        """Double-click handler: Highlights a saved segment and jumps the view/playback to its location."""
        sel = self.seg_list.curselection()
        if not sel: return
        idx = sel[0]
        start, end = self.segments[idx]
        
        # Select the range visually
        self.selection_start_ms = start
        self.selection_end_ms = end
        
        # Recenter the waveform view on the selected segment
        center = (start + end) / 2
        visible_duration = (self.view_width_px / self.zoom_level) * 1000
        self.view_offset_ms = center - (visible_duration / 2)
        if self.view_offset_ms < 0: self.view_offset_ms = 0
        
        # Move the playhead to the start of the segment
        self.playback_offset = start
        
        self.full_redraw()
        self.update_info()

    # --- Audio Playback Controls ---

    def toggle_play(self):
        """Switches between playing and stopping audio."""
        if self.is_playing:
            self.stop()
        else:
            self.play()

    def play(self):
        """Begins audio playback from the current seek position (playback_offset)."""
        if not self.audio: return
        self.is_playing = True
        self._play_token += 1
        current_token = self._play_token
        self.current_playback_start_timestamp = time.time()
        
        start_ms = int(self.playback_offset)
        # Load a large chunk into the playback buffer to prevent frequent interrupts
        chunk_len = 5 * 60 * 1000 # 5 minute buffer
        end_ms = min(len(self.audio), start_ms + chunk_len)
        
        segment = self.audio[start_ms:end_ms]
        # Play in a background thread to prevent GUI freezing
        threading.Thread(target=self._play_thread, args=(segment, current_token), daemon=True).start()

    def play_selection(self):
        """Plays only the currently highlighted selection and then stops."""
        if not self.audio or self.selection_start_ms is None: return
        
        if self.is_playing: self.stop()
        
        self.is_playing = True
        self._play_token += 1
        current_token = self._play_token
        self.current_playback_start_timestamp = time.time()
        self.playback_offset = min(self.selection_start_ms, self.selection_end_ms)
        
        segment = self.audio[int(min(self.selection_start_ms, self.selection_end_ms)):int(max(self.selection_start_ms, self.selection_end_ms))]
        threading.Thread(target=self._play_thread, args=(segment, current_token), daemon=True).start()

    def _play_thread(self, segment, token):
        """Background worker: Exports a chunk of audio to a temporary file and plays it via Windows API."""
        # Use a unique temp file name per token to avoid file-in-use errors
        temp_file = os.path.join(tempfile.gettempdir(), f"piper_slicer_playback_{token}.wav")
        segment.export(temp_file, format="wav")
        
        # Guard: If user stopped before export finished, don't play
        if not self.is_playing or self._play_token != token:
            return

        # Cross-platform async playback
        self._playback_process = audio_playback.play_wav_async(temp_file)
        
        # We manually track time to know when the audio has finished playing
        dur = len(segment) / 1000.0
        time.sleep(dur)
        if self.is_playing and self._play_token == token:
            self.stop_silent(token)

    def stop(self):
        """Stops playback immediately and silences audio device."""
        self.stop_silent()
        audio_playback.stop_playback(getattr(self, '_playback_process', None))
        self._playback_process = None

    def stop_silent(self, token=None):
        """Updates internal flags to reflect that audio has stopped, without calling the sound API."""
        # If token provided, only stop if it matches current active session
        if token is not None and token != self._play_token:
            return
            
        if self.is_playing:
            # Capture how much was played and update the seek position
            elapsed = (time.time() - self.current_playback_start_timestamp) * 1000
            self.playback_offset += elapsed
            self.is_playing = False
        self.update_info()
        self.draw_overlays() # Update playhead position

    def update_playback_cursor(self):
        """Main loop helper: Recursively updates the UI clock and playhead while audio is active."""
        if self.is_playing:
            self.draw_overlays()
            self.update_info()
        # Schedule next update at roughly 30 FPS
        self.root.after(30, self.update_playback_cursor)

    def export_segments(self):
        """Prompts for an output folder and saves all defined segments as WAV files."""
        if not self.segments: return
        
        # Determine the default directory for the folder picker
        initial_dir = os.getcwd()
        if self.dataset_dir:
            cand = os.path.abspath(self.dataset_dir)
            if os.path.isdir(cand):
                initial_dir = cand
        
        # [UX IMPROVEMENT] Automatically detect the Dojo's 'dataset' folder.
        # This saves the user from having to manually navigate to the correct 
        # project directory for every export session.
        out_dir = None
        if self.dataset_dir and os.path.isdir(self.dataset_dir):
            if messagebox.askyesno("Export Segments", f"Export {len(self.segments)} segments to {self.dataset_dir}?"):
                out_dir = self.dataset_dir
        
        if not out_dir:
            # Ask user where to save the segments
            out_dir = filedialog.askdirectory(
                title="Export Segments (Select the 'dataset' folder)", 
                initialdir=initial_dir
            )
        
        if not out_dir: return
        
        count = 0
        self.log("Exporting...")
        self.root.update()
        
        # Determine starting index by scanning existing numbered files
        existing_files = [f for f in os.listdir(out_dir) if f.endswith(".wav")]
        max_idx = 0
        for f in existing_files:
            try:
                num = int(Path(f).stem)
                if num > max_idx: max_idx = num
            except: pass
            
        current_idx = max_idx + 1
        
        # Export each segment sequentially
        for start, end in self.segments:
            chunk = self.audio[int(start):int(end)]
            out_name = Path(out_dir) / f"{current_idx}.wav"
            chunk.export(out_name, format="wav")
            current_idx += 1
            count += 1
            
        self.log(f"Exported {count} files.")
        messagebox.showinfo("Success", f"Exported {count} segments to {out_dir}")
        
        # Clear local list after successful export to prevent double-exporting
        self.segments = []
        self.seg_list.delete(0, tk.END)

    def go_to_transcribe(self):
        """
        [STEP 3 -> 4] AUTO-TRAIN FLOW: Launch Transcribe Wizard
        
        Handles the hand-off to the next stage of the voice training pipeline.
        1. Warns if segments are defined but not yet exported.
        2. Locates and launches the transcription sub-process.
        """
        if not self.dataset_dir: return
        
        # Safety check: alert user if they have pending segments in the list
        if self.segments: 
             if messagebox.askyesno("Unsaved Segments", "You have defined segments that haven't been exported yet. Export them first?"):
                self.export_segments()
                # Re-check: if they clicked 'Select Folder' and then cancelled, bits may still be here
                if self.segments: return 

        # Verify existence of the transcription tool
        wizard_script = Path(__file__).parent / "transcribe_wizard.py"
        if not wizard_script.exists():
            messagebox.showerror("Error", "Transcription tool not found.")
            return

        # Prepare the shell command to launch the next GUI (hiding console window on Windows)
        py_exe = sys.executable.replace("pythonw.exe", "python.exe")
        cmd = [py_exe, str(wizard_script), "--dataset_dir", self.dataset_dir]
        if self.voice_name:
            cmd.extend(["--voice_name", self.voice_name])
            
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            subprocess.Popen(cmd, creationflags=flags)
            self.root.destroy() # Close this tool as the next one opens
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch transcriber: {e}")

class AskAutoParams:
    """Dialog window for configuring automated silence detection (Step 3 Automatic)."""
    def __init__(self, parent):
        self.top = tk.Toplevel(parent)
        self.top.title("Auto-Detect Settings")
        self.top.geometry("400x300") # Start slightly larger
        self.top.minsize(350, 200)
        self.result = None
        
        # Add scrollable container
        container = ttk.Frame(self.top)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Sensitivity settings for Pydub's split_on_silence logic
        ttk.Label(scrollable_frame, text="Min Silence Length (ms):").grid(row=0, column=0, padx=5, pady=5)
        self.min_len = ttk.Entry(scrollable_frame)
        self.min_len.insert(0, "300")
        self.min_len.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(scrollable_frame, text="Silence Threshold (dB relative to avg):").grid(row=1, column=0, padx=5, pady=5)
        self.thresh = ttk.Entry(scrollable_frame)
        self.thresh.insert(0, "-16")
        self.thresh.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Button(scrollable_frame, text="Detect", command=self.on_ok).grid(row=2, column=0, columnspan=2, pady=10)
        
    def on_ok(self):
        """Validates input and closes the dialog."""
        try:
            m = int(self.min_len.get())
            t = float(self.thresh.get())
            self.result = (m, t)
            self.top.destroy()
        except ValueError:
            messagebox.showerror("Error", "Invalid numbers")

class AskFilterParams:
    """Dialog window for configuring audio similarity filtering (Step 3 Voice Filter)."""
    def __init__(self, parent):
        self.top = tk.Toplevel(parent)
        self.top.title("Filter by Voice Settings")
        self.top.geometry("500x500") # Start larger to show all options
        self.top.minsize(400, 350)
        self.result = None
        
        # Add scrollable container
        container = ttk.Frame(self.top)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Operating Mode (Keep valid audio vs Filter out noise/other speakers)
        ttk.Label(scrollable_frame, text="Mode:").grid(row=0, column=0, padx=5, pady=5, sticky="ne")
        self.mode_var = tk.StringVar(value="keep")
        
        frame = ttk.Frame(scrollable_frame)
        frame.grid(row=0, column=1, sticky="w", pady=5)
        ttk.Radiobutton(frame, text="Keep Matching (Whitelist)", variable=self.mode_var, value="keep").pack(anchor="w")
        ttk.Label(frame, text="   (Keeps segments that sound LIKE the reference)", font=("Segoe UI", 8), foreground="#666").pack(anchor="w")
        
        ttk.Radiobutton(frame, text="Remove Matching (Blacklist)", variable=self.mode_var, value="remove").pack(anchor="w", pady=(5,0))
        ttk.Label(frame, text="   (Deletes segments that sound LIKE the reference)", font=("Segoe UI", 8), foreground="#666").pack(anchor="w")
        
        # Sensitivity Threshold (Cosine similarity for speaker embeddings)
        ttk.Label(scrollable_frame, text="Similarity Threshold (0.1 - 0.99):").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.thresh = ttk.Entry(scrollable_frame)
        self.thresh.insert(0, "0.70")
        self.thresh.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(scrollable_frame, text="Higher = Stricter matching", foreground="#888").grid(row=3, column=1, sticky="w")
        
        ttk.Button(scrollable_frame, text="Run Filter", command=self.on_ok).grid(row=4, column=0, columnspan=2, pady=10)
        
    def on_ok(self):
        """Validates input and closes the dialog."""
        try:
            t = float(self.thresh.get())
            if not (0.0 < t < 1.0): raise ValueError
            mode = self.mode_var.get()
            self.result = (t, mode)
            self.top.destroy()
        except ValueError:
            messagebox.showerror("Error", "Threshold must be between 0.1 and 0.99")

# Check if main
if __name__ == "__main__":
    try:
        ensure_ffmpeg()
        try:
            from pydub import AudioSegment
        except ImportError:
            try:
                root = tk.Tk()
                root.withdraw()
                if messagebox.askyesno(
                    "Dependency Missing",
                    "pydub is required for the Dataset Slicer.\n\nInstall it now?"
                ):
                    try:
                        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                        subprocess.check_call([sys.executable, "-m", "pip", "install", "pydub"], cwd=os.getcwd(), creationflags=flags)
                        messagebox.showinfo("Installed", "pydub installed successfully. Restarting the slicer...")
                        root.destroy()
                        os.execl(sys.executable, sys.executable, *sys.argv)
                    except Exception as e:
                        messagebox.showerror("Install Failed", f"Failed to install pydub:\n{e}")
                        root.destroy()
                        sys.exit(1)
                else:
                    root.destroy()
                    sys.exit(1)
            except Exception:
                sys.exit(1)

        root = tk.Tk()
        app = AudioSlicerApp(root)
        root.mainloop()
    except Exception as e:
        # Emergency error reporting
        try:
            import tkinter.messagebox as mbox
            r = tk.Tk()
            r.withdraw()
            mbox.showerror("Slicer Error", f"Failed to start Slicer:\n{e}")
            r.destroy()
        except:
            # Last resort log
            with open("slicer_crash_log.txt", "w") as f:
                import traceback
                traceback.print_exc(file=f)

