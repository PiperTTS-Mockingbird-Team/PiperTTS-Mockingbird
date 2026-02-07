/**
 * Advanced Slicer Component for PiperTTS Mockingbird Dashboard
 * Licensed under the MIT License.
 * Copyright (c) 2026 PiperTTS Mockingbird Developers
 */

class AdvancedSlicer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.voiceName = null;
        this.wavesurfer = null;
        this.masterUrl = null;
        this.segments = [];
        this.regions = {}; // Track wavesurfer regions
        this.selectedSegmentIds = new Set();
        this.lastSelectedIndex = null;
        this.activeSegmentId = null;
        this.exportedNames = new Set();
        this.pins = []; // Track manual pins (red lines)

        this.settings = this._loadSettings();
        
        this.init();
        this.setupGlobalShortcuts();
    }

    _defaultSettings() {
        return {
            autoDetect: {
                min_silence_len_ms: 300,
                silence_thresh_offset_db: -16.0,
                pad_ms: 200,
                min_segment_ms: 500,
                clear_existing: true,
            },
            autoSplit: {
                min_silence_len_ms: 600,
                silence_thresh_offset_db: -16.0,
                keep_silence_ms: 250,
            },
            bulk: {
                merge_gap_s: 1.0,
                remove_short_s: 1.0,
            },
        };
    }

    _loadSettings() {
        try {
            const raw = localStorage.getItem('slicer_settings');
            if (!raw) return this._defaultSettings();
            const parsed = JSON.parse(raw);
            return this._mergeSettings(this._defaultSettings(), parsed);
        } catch (e) {
            return this._defaultSettings();
        }
    }

    _mergeSettings(base, override) {
        if (!override || typeof override !== 'object') return base;
        const out = Array.isArray(base) ? base.slice() : { ...base };
        Object.keys(override).forEach((k) => {
            if (override[k] && typeof override[k] === 'object' && !Array.isArray(override[k]) && base[k] && typeof base[k] === 'object') {
                out[k] = this._mergeSettings(base[k], override[k]);
            } else {
                out[k] = override[k];
            }
        });
        return out;
    }

    _saveSettings() {
        try {
            localStorage.setItem('slicer_settings', JSON.stringify(this.settings));
        } catch (e) {
            // ignore
        }
    }

    _numFromInput(id, fallback) {
        const el = document.getElementById(id);
        if (!el) return fallback;
        const v = Number(el.value);
        return Number.isFinite(v) ? v : fallback;
    }

    _boolFromInput(id, fallback) {
        const el = document.getElementById(id);
        if (!el) return fallback;
        return !!el.checked;
    }

    _applySettingsToInputs() {
        const s = this.settings || this._defaultSettings();
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.value = String(val);
        };
        const setChk = (id, val) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.checked = !!val;
        };

        setVal('set-ad-minsil', s.autoDetect.min_silence_len_ms);
        setVal('set-ad-thr', s.autoDetect.silence_thresh_offset_db);
        setVal('set-ad-pad', s.autoDetect.pad_ms);
        setVal('set-ad-minseg', s.autoDetect.min_segment_ms);
        setChk('set-ad-clear', s.autoDetect.clear_existing);

        setVal('set-as-minsil', s.autoSplit.min_silence_len_ms);
        setVal('set-as-thr', s.autoSplit.silence_thresh_offset_db);
        setVal('set-as-keep', s.autoSplit.keep_silence_ms);

        setVal('set-bulk-gap', s.bulk.merge_gap_s);
        setVal('set-bulk-min', s.bulk.remove_short_s);
    }

    _readInputsToSettings() {
        const next = this._mergeSettings(this._defaultSettings(), this.settings || {});
        next.autoDetect.min_silence_len_ms = Math.max(0, Math.floor(this._numFromInput('set-ad-minsil', next.autoDetect.min_silence_len_ms)));
        next.autoDetect.silence_thresh_offset_db = this._numFromInput('set-ad-thr', next.autoDetect.silence_thresh_offset_db);
        next.autoDetect.pad_ms = Math.max(0, Math.floor(this._numFromInput('set-ad-pad', next.autoDetect.pad_ms)));
        next.autoDetect.min_segment_ms = Math.max(0, Math.floor(this._numFromInput('set-ad-minseg', next.autoDetect.min_segment_ms)));
        next.autoDetect.clear_existing = this._boolFromInput('set-ad-clear', next.autoDetect.clear_existing);

        next.autoSplit.min_silence_len_ms = Math.max(0, Math.floor(this._numFromInput('set-as-minsil', next.autoSplit.min_silence_len_ms)));
        next.autoSplit.silence_thresh_offset_db = this._numFromInput('set-as-thr', next.autoSplit.silence_thresh_offset_db);
        next.autoSplit.keep_silence_ms = Math.max(0, Math.floor(this._numFromInput('set-as-keep', next.autoSplit.keep_silence_ms)));

        next.bulk.merge_gap_s = Math.max(0, this._numFromInput('set-bulk-gap', next.bulk.merge_gap_s));
        next.bulk.remove_short_s = Math.max(0, this._numFromInput('set-bulk-min', next.bulk.remove_short_s));

        this.settings = next;
        this._saveSettings();
    }

    init() {
        // We'll initialize wavesurfer when audio is loaded
    }

    setupGlobalShortcuts() {
        document.addEventListener('keydown', (e) => {
            if (!this.wavesurfer || !this.container.offsetParent) return; // Only if slicer is visible
            if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA') return;
            
            if (e.code === 'Space') {
                e.preventDefault();
                this.wavesurfer.playPause();
                const playBtn = document.getElementById('slicer-play-btn');
                if (playBtn) playBtn.innerHTML = this.wavesurfer.isPlaying() ? '<i class="fas fa-pause"></i>' : '<i class="fas fa-play"></i>';
            }
            if (e.code === 'Enter') {
                this.addCurrentSelection();
            }

            if (e.code === 'Delete' || e.code === 'Backspace') {
                if (this.selectedSegmentIds.size > 0) {
                    e.preventDefault();
                    this.removeSelected();
                }
            }

            if (e.code === 'Escape') {
                e.preventDefault();
                this.clearCurrentSelection();
            }
        });
    }

    setupListSelectionBox() {
        const scrollArea = this.container.querySelector('.segments-scroll');
        if (!scrollArea) return;

        let startX, startY;
        let selectionBox = null;
        let isDragging = false;

        const onMouseDown = (e) => {
            // Only start if clicking on the background of the list, or on a segment but not a button/input
            if (e.button !== 0) return; // Left click only
            
            const isButton = e.target.closest('button') || e.target.closest('input') || e.target.closest('.icon-btn-sm');
            if (isButton) return;

            isDragging = false;
            const rect = scrollArea.getBoundingClientRect();
            
            // Client coordinates minus rect gives us position relative to scrollArea, 
            // then add scroll position to get "virtual" document position within the scroll area.
            startX = e.clientX - rect.left + scrollArea.scrollLeft;
            startY = e.clientY - rect.top + scrollArea.scrollTop;

            const onMouseMove = (e) => {
                const currentX = e.clientX - rect.left + scrollArea.scrollLeft;
                const currentY = e.clientY - rect.top + scrollArea.scrollTop;

                const diffX = Math.abs(currentX - startX);
                const diffY = Math.abs(currentY - startY);

                if (!isDragging && (diffX > 5 || diffY > 5)) {
                    isDragging = true;
                    selectionBox = document.createElement('div');
                    selectionBox.className = 'list-selection-box';
                    scrollArea.appendChild(selectionBox);
                    
                    if (!e.shiftKey && !e.ctrlKey && !e.metaKey) {
                        this.selectedSegmentIds.clear();
                    }
                }

                if (isDragging) {
                    const left = Math.min(startX, currentX);
                    const top = Math.min(startY, currentY);
                    const width = Math.abs(startX - currentX);
                    const height = Math.abs(startY - currentY);

                    selectionBox.style.left = `${left}px`;
                    selectionBox.style.top = `${top}px`;
                    selectionBox.style.width = `${width}px`;
                    selectionBox.style.height = `${height}px`;

                    this.updateSelectionFromBox(left, top, width, height, e.shiftKey || e.ctrlKey || e.metaKey);
                }
            };

            const onMouseUp = () => {
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);

                if (selectionBox) {
                    selectionBox.remove();
                    selectionBox = null;
                }
                
                if (isDragging) {
                    this.renderSegments();
                    // Prevent the next click event if we were dragging
                    const preventClick = (e) => {
                        // Only suppress the first post-drag click inside the scroll area.
                        // Otherwise we'd also swallow toolbar button clicks (e.g. Remove Selected).
                        if (scrollArea.contains(e.target)) {
                            e.stopImmediatePropagation();
                        }
                        document.removeEventListener('click', preventClick, true);
                    };
                    document.addEventListener('click', preventClick, true);
                }
                isDragging = false;
            };

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        };

        scrollArea.addEventListener('mousedown', onMouseDown);
    }

    updateSelectionFromBox(left, top, width, height, isAppending) {
        const items = this.container.querySelectorAll('.segment-item');
        const boxRight = left + width;
        const boxBottom = top + height;

        items.forEach((item) => {
            // Find UID – we need a more reliable way than parsing onclick.
            // But for now, let's use the index or a data attribute if we had one.
            // Since we're in the same class, we can find the matching segment.
            const idx = Array.prototype.indexOf.call(item.parentNode.children, item);
            if (idx === -1) return;
            
            // Note: index in combined array... actually, let's tag the items during render.
            // I'll update renderSegments to add data-id.
            const sid = item.getAttribute('data-id');
            if (!sid || item.classList.contains('pin-item')) return;

            const itemTop = item.offsetTop;
            const itemBottom = itemTop + item.offsetHeight;
            const itemLeft = item.offsetLeft;
            const itemRight = itemLeft + item.offsetWidth;

            const isOverlap = !(itemLeft > boxRight || 
                                itemRight < left || 
                                itemTop > boxBottom || 
                                itemBottom < top);

            if (isOverlap) {
                this.selectedSegmentIds.add(sid);
            } else if (!isAppending) {
                this.selectedSegmentIds.delete(sid);
            }
        });

        // Visually update the UI state
        this._updateSelectionUI();
    }

    _updateSelectionUI() {
        const items = this.container.querySelectorAll('.segment-item');
        items.forEach(item => {
            const sid = item.getAttribute('data-id');
            if (sid && !item.classList.contains('pin-item')) {
                if (this.selectedSegmentIds.has(sid)) {
                    item.classList.add('selected');
                } else {
                    item.classList.remove('selected');
                }
            }
        });

        const selectedBadge = document.getElementById('selected-count');
        if (selectedBadge) {
            selectedBadge.textContent = `${this.selectedSegmentIds.size} selected`;
        }

        const btnMerge = document.getElementById('btn-merge-selected');
        const btnRemove = document.getElementById('btn-remove-selected');
        if (btnMerge) btnMerge.disabled = this.selectedSegmentIds.size < 2;
        if (btnRemove) {
            btnRemove.disabled = this.selectedSegmentIds.size < 1;
            btnRemove.style.display = this.selectedSegmentIds.size < 1 ? 'none' : 'block';
        }
    }

    clearCurrentSelection() {
        if (!this.wavesurfer) return;
        const selectionRegion = Object.values(this.wavesurfer.regions.list).find(r => !r.data?.isSegment && !r.data?.isPin);
        if (selectionRegion) {
            try { selectionRegion.remove(); } catch (e) {}
        }

        this.activeSegmentId = null;
        this.renderSegments();

        const startEl = document.getElementById('sel-start');
        const endEl = document.getElementById('sel-end');
        const durEl = document.getElementById('sel-duration');
        if (startEl) startEl.textContent = '--:--.---';
        if (endEl) endEl.textContent = '--:--.---';
        if (durEl) durEl.textContent = '0.000s';

        const addBtn = document.getElementById('btn-add-segment');
        const playBtn = document.getElementById('btn-play-sel');
        const deleteBtn = document.getElementById('btn-delete-sel');
        if (addBtn) {
            addBtn.disabled = true;
            addBtn.innerHTML = '<i class="fas fa-plus"></i> Add Clip';
            addBtn.style.opacity = '1';
            addBtn.classList.remove('btn-secondary');
            addBtn.classList.add('btn-primary');
        }
        if (playBtn) playBtn.disabled = true;
        if (deleteBtn) deleteBtn.disabled = true;
    }

    async loadVoice(voiceName) {
        this.voiceName = voiceName;
        this.segments = [];
        this.pins = []; // Clear pins when switching voices
        this.selectedSegmentIds.clear();
        this.lastSelectedIndex = null;
        this.activeSegmentId = null;
        this.exportedNames = new Set();

        // Immediately clear the UI so we don't see the previous voice's data while waiting for master-info
        if (this.wavesurfer) {
            this.wavesurfer.destroy();
            this.wavesurfer = null;
        }
        this.showUpload(); // Shows a loading/idle state placeholder
        
        // Check if master audio exists
        const res = await fetch(`/api/training/master-info?voice=${voiceName}`);
        
        // Race condition check: if the user switched voices again while fetching, bail.
        if (this.voiceName !== voiceName) return;

        const data = await res.json();
        
        if (data.exists) {
            this.showSlicer(data.path);
            // Keep the UI in sync with what's already exported.
            this.refreshExportedNames();
            this.refreshDepsStatus();
            this.loadExistingSegments();
        } else {
            this.showUpload();
        }
    }

    async refreshDepsStatus() {
        const banner = document.getElementById('deps-banner');
        if (!banner) return;
        try {
            const res = await fetch('/api/training/deps-status');
            if (!res.ok) {
                banner.style.display = 'none';
                return;
            }
            const data = await res.json();

            const missing = (data && data.missing) ? data.missing : [];
            if (!missing || missing.length === 0) {
                banner.style.display = 'none';
                return;
            }

            const parts = [];
            if (missing.includes('ffmpeg')) {
                parts.push('ffmpeg (needed for mp3/m4a uploads)');
            }
            if (missing.includes('torch') || missing.includes('resemblyzer') || missing.includes('numpy')) {
                parts.push('voice tools deps (needed for Label/Filter/Split by Voice)');
            }
            if (missing.includes('pydub')) {
                parts.push('pydub (needed for slicing/export)');
            }

            banner.style.display = 'block';
            banner.innerHTML = `
                <div style="display:flex; gap:0.75rem; align-items:flex-start;">
                    <div style="flex: 1;">
                        <div style="font-weight:700; margin-bottom: 0.25rem;">Optional dependencies missing</div>
                        <div style="color: var(--text-muted); font-size: 0.85rem;">
                            Some slicer features may be disabled: ${parts.join(', ')}.
                            <div style="margin-top:0.25rem;">See <span style="font-family:Consolas,monospace;">requirements.txt</span> / install ffmpeg, then restart the server.</div>
                        </div>
                    </div>
                    <button class="btn btn-sm btn-secondary" id="btn-deps-details" type="button">Details</button>
                </div>
            `;

            const btn = document.getElementById('btn-deps-details');
            if (btn) {
                btn.onclick = () => {
                    alert(
                        `Missing: ${missing.join(', ')}\n\n` +
                        `Install voice tools deps (optional):\n` +
                        `  pip install -r src/requirements.txt\n\n` +
                        `Install ffmpeg (Windows):\n` +
                        `  winget install Gyan.FFmpeg\n\n` +
                        `Restart the server after installing.`
                    );
                };
            }
        } catch (e) {
            banner.style.display = 'none';
        }
    }

    async refreshExportedNames() {
        if (!this.voiceName) return;
        const currentVoice = this.voiceName;

        try {
            const res = await fetch(`/api/training/audio-files?voice=${currentVoice}`);
            if (!res.ok) return;
            
            // Race check
            if (this.voiceName !== currentVoice) return;

            const data = await res.json();
            const names = new Set();
            (data.files || []).forEach(f => {
                if (f && f.name) names.add(String(f.name));
            });
            this.exportedNames = names;
            this.renderSegments();
        } catch (e) {
            // Non-fatal; exported badges are optional.
            console.warn('Failed to refresh exported names:', e);
        }
    }

    showUpload() {
        this.container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-file-audio"></i>
                <h3 title="You need to provide a source audio file before you can start creating training clips.">No Master Audio Loaded</h3>
                <p>Upload a long audio file to begin slicing it into training clips.</p>
                <div style="margin-top: 2rem;">
                    <label for="master-audio-upload" class="btn btn-primary" title="Click here to browse your computer for an audio file (MP3, WAV, etc.) to slice.">
                        <i class="fas fa-upload"></i> Upload Master Audio
                    </label>
                </div>
            </div>
        `;
    }

    showSlicer(audioUrl) {
        this.masterUrl = audioUrl;
        this.container.innerHTML = `
            <div class="slicer-layout">
                <div id="deps-banner" class="card" style="display:none; padding: 0.75rem 1rem; border: 1px solid rgba(245, 158, 11, 0.35); background: rgba(245, 158, 11, 0.06);"></div>
                
                <div class="top-playback-bar">
                    <div class="playback-controls">
                        <button class="btn btn-secondary btn-icon" id="slicer-play-btn" title="Toggle audio playback. You can also press Space."><i class="fas fa-play"></i></button>
                        <div class="time-display" id="slicer-time" title="Current playback position within the audio file.">00:00.000</div>
                        <div class="playback-divider"></div>
                        <div class="speed-selector-wrapper" title="Playback Speed">
                            <i class="fas fa-running"></i>
                            <select id="slicer-speed" title="Select playback speed">
                                <option value="0.5">0.5x</option>
                                <option value="0.75">0.75x</option>
                                <option value="1.0" selected>1.0x</option>
                                <option value="1.25">1.25x</option>
                                <option value="1.5">1.5x</option>
                                <option value="2.0">2x</option>
                            </select>
                        </div>
                        <button class="btn btn-secondary btn-icon" id="btn-add-pin" title="Add a reference pin at the current playback position. Tip: use pins to mark the beginning/end of music so you can quickly find and delete those segments (music is bad for voice training)." style="color: #ef4444; border-color: rgba(239, 68, 68, 0.4);">
                            <i class="fas fa-thumbtack"></i>
                        </button>
                    </div>
                </div>

                <div class="waveform-container">
                    <div id="waveform-loading" class="waveform-loading" style="display: none; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 10; text-align: center; color: var(--text-muted); font-size: 0.9rem;">
                        <i class="fas fa-spinner fa-spin" style="font-size: 1.5rem; margin-bottom: 0.5rem; color: var(--accent);"></i>
                        <div>Loading audio waveform...</div>
                    </div>
                    <div id="waveform"></div>
                    <div id="waveform-timeline"></div>
                    
                    <div class="waveform-controls">
                        <div class="selection-bar-group">
                            <div class="selection-bar-metrics">
                                <div class="sel-bar-item" title="Selection Start">
                                    <span class="label">START</span>
                                    <span class="value" id="sel-start">--:--.---</span>
                                </div>
                                <div class="sel-bar-item" title="Selection End">
                                    <span class="label">END</span>
                                    <span class="value" id="sel-end">--:--.---</span>
                                </div>
                                <div class="sel-bar-item highlighted" title="Total Duration">
                                    <span class="label">DUR</span>
                                    <span class="value" id="sel-duration">0.000s</span>
                                </div>
                            </div>
                            
                            <div class="selection-bar-actions">
                                <button class="btn btn-primary btn-sm" id="btn-add-segment" disabled title="Commit selection to the list (Enter)">
                                    <i class="fas fa-plus"></i> Add Clip
                                </button>
                                <button class="btn btn-secondary btn-sm" id="btn-play-sel" disabled title="Preview selection">
                                    <i class="fas fa-play-circle"></i> Preview
                                </button>
                                <button class="btn btn-danger-soft btn-sm" id="btn-delete-sel" disabled title="Delete current selection or segment (Delete)">
                                    <i class="fas fa-trash"></i> Delete
                                </button>
                            </div>
                        </div>
                        
                        <div class="zoom-controls">
                            <i class="fas fa-search-minus" title="Zoom out"></i>
                            <input type="range" id="slicer-zoom" min="0" max="1000" value="50" title="Adjust waveform zoom">
                            <i class="fas fa-search-plus" title="Zoom in"></i>
                        </div>
                    </div>
                </div>

                <div class="slicer-grid">
                    <div class="tools-card card">
                        <div class="card-header">
                            <div style="display:flex; justify-content: space-between; align-items: center; width: 100%;">
                                <h3><i class="fas fa-tools"></i> Tools & Settings</h3>
                                <div style="display:flex; gap:0.5rem; align-items: center;">
                                    <details class="slicer-settings-dropdown" style="position: relative;">
                                        <summary class="btn btn-sm btn-ghost" style="font-size: 0.7rem; font-weight: 600; padding: 4px 8px; border: 1px solid rgba(255,255,255,0.1);">
                                            <i class="fas fa-sliders-h"></i> <span>Adjust Parameters</span>
                                        </summary>
                                        <div class="slicer-settings-popup card">
                                             <div class="slicer-settings-body">
                                                 <div class="slicer-settings-section">
                                                     <div class="slicer-settings-title">Detection Sensitivity</div>
                                                     <div class="slicer-settings-grid">
                                                         <label title="Minimum Silence duration: How long a pause must be before starting a new clip. If it's cutting in the middle of words, increase this. If it's merging separate sentences, decrease it.">Min sil (ms) <input id="set-ad-minsil" type="number" min="0" step="10" /></label>
                                                         <label title="Silence Threshold: How quiet a part needs to be to count as silence. If background noise is being detected as speech, lower this (e.g. -25). If quiet speech is being missed, raise it.">Thresh (dB) <input id="set-ad-thr" type="number" step="0.5" /></label>
                                                         <label title="Padding: Adds a tiny buffer to the start and end of every clip. This prevents words from sounding cut off and ensures the full word is captured. 200ms is a safe default.">Pad (ms) <input id="set-ad-pad" type="number" min="0" step="10" /></label>
                                                         <label title="Minimum Segment: The shortest allowed clip length. This is a safety net that prevents tiny noises like mouth clicks or taps from becoming their own segments.">Min seg (ms) <input id="set-ad-minseg" type="number" min="0" step="10" /></label>
                                                     </div>
                                                     <label class="slicer-settings-check" title="If checked, running Auto-Detect will delete all existing segments in your list first. Turn this off if you want to run detection multiple times with different settings." style="margin-top: 1rem;">
                                                         <input id="set-ad-clear" type="checkbox" /> Clear list before auto-detect
                                                     </label>
                                                 </div>
                                                 <div class="slicer-settings-actions">
                                                     <button class="btn btn-sm btn-secondary" id="btn-settings-reset">Reset Defaults</button>
                                                 </div>
                                             </div>
                                        </div>
                                    </details>
                                </div>
                            </div>
                        </div>

                        <div class="card-body">
                            <div class="slicer-tools">
                                <div class="toolbox-section" style="margin-bottom: 1rem;">
                                    <div class="toolbox-header" style="margin-bottom: 0.5rem; font-size: 0.75rem; opacity: 0.7;"><i class="fas fa-magic"></i> 1. Generate Segments</div>
                                    <div style="display:grid; grid-template-columns: 1fr; gap: 0.5rem;">
                                         <button class="btn btn-sm btn-secondary" id="btn-auto-detect" title="Scan file for speech segments using silence detection.">
                                             <i class="fas fa-bolt"></i> <span>Auto-Detect (Silence)</span>
                                         </button>
                                    </div>
                                </div>

                                <div class="toolbox-section" style="margin-bottom: 1rem;">
                                    <div class="toolbox-header" style="margin-bottom: 0.5rem; font-size: 0.75rem; opacity: 0.7;"><i class="fas fa-filter"></i> 2. Clean & Filter</div>
                                    <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 0.5rem;">
                                        <button class="btn btn-sm btn-success" id="btn-whitelist-filter" title="Keep segments with similar voices to your selection, delete the rest. Select segments first to use as reference."><i class="fas fa-check"></i> Whitelist Filter</button>
                                        <button class="btn btn-sm btn-warning" id="btn-blacklist-filter" title="Delete segments with similar voices to your selection, keep the rest. Select segments first to use as reference."><i class="fas fa-times"></i> Blacklist Filter</button>
                                        <button class="btn btn-sm btn-danger-soft" style="grid-column: span 2; display: none;" id="btn-remove-selected" disabled title="Delete all currently highlighted segments.">Remove Selected</button>
                                    </div>
                                </div>
                                
                                <div class="toolbox-section" style="margin-bottom: 1rem;">
                                    <div class="toolbox-header" style="margin: 0.5rem 0 0.5rem 0; font-size: 0.75rem; opacity: 0.7;"><i class="fas fa-layer-group"></i> 3. Group & Merge</div>
                                    <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 0.5rem;">
                                        <button class="btn btn-sm btn-secondary" id="btn-merge-gaps" title="Merge small gaps between adjacent segments to prevent silence gaps.">Auto-Merge Gaps</button>
                                        <button class="btn btn-sm btn-secondary" id="btn-merge-selected" disabled title="Join two or more selected clips into one single segment. Best for fixing sentences that were accidentally split by a pause.">Merge Selected</button>
                                    </div>
                                </div>

                                <div class="toolbox-section" style="margin-bottom: 0;">
                                    <div class="toolbox-header" style="margin: 0.5rem 0 0.5rem 0; font-size: 0.75rem; opacity: 0.7;"><i class="fas fa-magic"></i> 4. Refine Dataset</div>
                                    <div style="display:grid; grid-template-columns: 1fr; gap: 0.5rem;">
                                        <button class="btn btn-sm btn-secondary" id="btn-remove-shorts" style="grid-column: span 2" title="Remove segments that are too short to be useful for training (based on your 'Min seg' setting).">
                                            <i class="fas fa-broom"></i> Remove Tiny Segments
                                        </button>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="slicer-export-progress" style="margin-top: 1.5rem; display:none;">
                                <div style="display:flex; justify-content:space-between; font-size: 0.7rem; color: var(--text-muted); margin-bottom: 4px;">
                                    <span id="export-progress-label">Exporting...</span>
                                    <span id="export-progress-count">0 / 0</span>
                                </div>
                                <div class="slicer-export-bar">
                                    <div class="slicer-export-bar-fill" id="export-progress-fill" style="width:0%"></div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="segments-card card">
                        <div class="card-header">
                            <div style="display:flex; justify-content: space-between; align-items: center; width: 100%; padding-right: 0.25rem;">
                                <h3><i class="fas fa-list"></i> Segment List</h3>
                                <div style="display:flex; gap:0.6rem; align-items: center;">
                                    <div class="pin-navigation" style="display:flex; align-items: center; gap: 0.3rem; background: rgba(239, 68, 68, 0.1); padding: 2px 6px; border-radius: 6px; border: 1px solid rgba(239, 68, 68, 0.2);">
                                        <i class="fas fa-thumbtack" style="color: #ef4444; font-size: 0.7rem; opacity: 0.9;"></i>
                                        <span id="pin-counter" style="color: #ef4444; font-size: 0.65rem; font-weight: 800; min-width: 30px; text-align: left; font-family: 'JetBrains Mono', monospace; letter-spacing: -0.5px;">0/0</span>
                                        <div style="display:flex; gap: 0.1rem; border-left: 1px solid rgba(239, 68, 68, 0.2); padding-left: 0.2rem; margin-left: 0.1rem;">
                                            <button class="btn btn-sm btn-ghost btn-icon" id="btn-prev-pin" title="Scroll to previous pin" style="color: #ef4444; height: 22px; width: 22px; padding: 0;">
                                                <i class="fas fa-chevron-up" style="font-size: 0.65rem;"></i>
                                            </button>
                                            <button class="btn btn-sm btn-ghost btn-icon" id="btn-next-pin" title="Scroll to next pin" style="color: #ef4444; height: 22px; width: 22px; padding: 0;">
                                                <i class="fas fa-chevron-down" style="font-size: 0.65rem;"></i>
                                            </button>
                                        </div>
                                    </div>
                                    <span id="selected-count" style="font-size: 0.7rem; color: var(--text-muted); opacity: 0.8;">0 selected</span>
                                    <span class="badge-count" id="segment-count" title="Total count" style="background: rgba(56, 189, 248, 0.2); color: var(--accent); border: 1px solid rgba(56, 189, 248, 0.3);">0</span>
                                    <button class="btn btn-sm btn-secondary btn-icon" id="btn-download-zip" title="Download all segments as a ZIP archive (Back up your clips or use them in other tools)" style="height: 30px; width: 30px; margin-left: 0.25rem; display: flex; align-items: center; justify-content: center;">
                                        <i class="fas fa-file-archive" style="font-size: 0.9rem;"></i>
                                    </button>
                                </div>
                            </div>
                        </div>
                        <div class="card-body">
                            <div class="segments-scroll">
                                <div class="segment-header">
                                    <span>#</span>
                                    <span>Time Span</span>
                                    <span>Duration</span>
                                    <span style="text-align: center;">Flags</span>
                                    <span style="text-align: right;">Actions</span>
                                </div>
                                <div id="segments-container">
                                    <div class="empty-state" style="padding: 2rem">
                                        <i class="fas fa-layer-group"></i>
                                        <p>No segments created yet.</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="slicer-shortcuts-footer">
                    <div class="shortcut-item" title="Press Enter to save the current selection as a segment.">
                        <kbd>Enter</kbd> <span>Add Clip</span>
                    </div>
                    <div class="shortcut-item" title="Press Space to play or pause the audio.">
                        <kbd>Space</kbd> <span>Play/Pause</span>
                    </div>
                    <div class="shortcut-item" title="Press Delete or Backspace to remove the selected segment.">
                        <kbd>Del</kbd> <span>Delete Segment</span>
                    </div>
                    <div class="shortcut-item" title="Hold Shift: waveform clicks ignore segments and move the playhead. Shift+Click in the list selects a range.">
                        <kbd>Shift</kbd> <span>(Seek Mode / Range Select)</span>
                    </div>
                </div>

                <!-- Custom Modal -->
                <div id="slicer-modal-overlay" style="display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.7); z-index:9999; backdrop-filter: blur(4px);">
                    <div id="slicer-modal" style="position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); background:var(--card-bg); border:1px solid var(--border); border-radius:8px; padding:1.25rem; min-width:400px; max-width:480px; box-shadow: 0 20px 60px rgba(0,0,0,0.5);">
                        <h3 id="slicer-modal-title" style="margin:0 0 0.75rem 0; color:var(--text-main); font-size:1rem;"></h3>
                        <div id="slicer-modal-content" style="color:var(--text-muted); line-height:1.5; margin-bottom:1rem;"></div>
                        <div id="slicer-modal-input-wrap" style="display:none; margin-bottom:1rem;">
                            <input type="text" id="slicer-modal-input" style="width:100%; padding:0.5rem; background:var(--bg-dark); border:1px solid var(--border); border-radius:4px; color:var(--text-main); font-size:0.9rem;" />
                        </div>
                        <div style="display:flex; gap:0.6rem; justify-content:flex-end;">
                            <button id="slicer-modal-cancel" class="btn btn-secondary" style="padding:0.45rem 1.1rem;">Cancel</button>
                            <button id="slicer-modal-ok" class="btn btn-primary" style="padding:0.45rem 1.1rem;">OK</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        this.initWavesurfer(audioUrl);
        this.setupEventListeners();
        this._applySettingsToInputs();
    }

    initWavesurfer(url) {
        if (this.wavesurfer) {
            this.wavesurfer.destroy();
        }

        this.wavesurfer = WaveSurfer.create({
            container: '#waveform',
            waveColor: '#4b5563',
            progressColor: '#38bdf8',
            cursorColor: '#38bdf8',
            cursorWidth: 2,
            height: 150,
            barWidth: 2,
            normalize: true,
            backend: 'WebAudio',
            plugins: [
                WaveSurfer.regions.create({}),
                WaveSurfer.timeline.create({ container: '#waveform-timeline', primaryColor: '#a3a3a3', secondaryColor: '#525252', labelColor: '#a3a3a3' })
            ]
        });

        // Show loading indicator
        const loadingEl = document.getElementById('waveform-loading');
        if (loadingEl) loadingEl.style.display = 'flex';

        this.wavesurfer.load(url);

        this.wavesurfer.on('ready', () => {
            console.log('WaveSurfer ready');
            // Hide loading indicator
            if (loadingEl) loadingEl.style.display = 'none';
            this.wavesurfer.zoom(50);

            // Critical for Python-like UX: click+drag highlights a selection.
            // (WaveSurfer Regions plugin requires enableDragSelection to be called.)
            try {
                if (typeof this.wavesurfer.enableDragSelection === 'function') {
                    this.wavesurfer.enableDragSelection({ color: 'rgba(56, 189, 248, 0.2)' });
                }
            } catch (e) {
                console.warn('enableDragSelection unavailable:', e);
            }
        });

        this.wavesurfer.on('audioprocess', () => {
            this.updateTimeDisplay();
        });

        this.wavesurfer.on('seek', () => {
            this.updateTimeDisplay();
        });

        // Click on background clears focus/selection
        this.wavesurfer.on('click', () => {
            this.clearCurrentSelection();
        });

        // Regions integration for selection
        this.wavesurfer.on('region-created', (region) => {
            // If it's a new manual selection (not one we restored)
            if (region.data && (region.data.isSegment || region.data.isPin)) return;

            // Mark this region as the active selection so it's draggable/resizable like the Python slicer.
            try {
                region.data = region.data || {};
                region.data.isSelection = true;
                // Force region to be draggable + resizable regardless of WaveSurfer defaults.
                if (typeof region.update === 'function') {
                    region.update({ drag: true, resize: true });
                } else {
                    region.drag = true;
                    region.resize = true;
                }
            } catch (e) {}

            // Tag for CSS styling (selection highlight)
            try {
                region.element?.classList?.add('selection-region');
            } catch (e) {}
            
            // Clear other active selections if any
            Object.values(this.wavesurfer.regions.list).forEach(r => {
                if (r !== region && !r.data?.isSegment && !r.data?.isPin) r.remove();
            });
            
            this.updateSelectionInfo(region);
        });

        this.wavesurfer.on('region-updated', (region) => {
            this.updateSelectionInfo(region);
        });

        this.wavesurfer.on('region-click', (region, event) => {
            if (event) event.stopPropagation();

            // Shift+Click should allow precise seeking even when clicking on top of a region.
            // Regions otherwise swallow the click, preventing the playhead from moving.
            if (event?.shiftKey) {
                const wrapper = this.wavesurfer?.container || document.querySelector('#waveform');
                if (wrapper && typeof wrapper.getBoundingClientRect === 'function') {
                    const rect = wrapper.getBoundingClientRect();
                    const rawX = event.clientX - rect.left;
                    const x = Math.max(0, Math.min(rect.width, rawX));
                    const progress = rect.width > 0 ? (x / rect.width) : 0;
                    try {
                        this.wavesurfer.seekTo(progress);
                    } catch (e) {
                        // ignore
                    }
                }
            }
            this.updateSelectionInfo(region);
            
            // Sync with list selection visually
            if (region.data?.isSegment || region.data?.isPin) {
                if (region.data?.isSegment) {
                    this.activeSegmentId = region.id;
                }
                
                // For segments, update selection. For pins, we just scroll to it.
                if (region.data?.isSegment) {
                    const isMulti = event && (event.ctrlKey || event.metaKey);
                    if (!isMulti) {
                        this.selectedSegmentIds.clear();
                    }
                    this.selectedSegmentIds.add(region.id);
                    this._updateSelectionUI();
                }

                // Scroll the list to the selected item
                const listContainer = document.querySelector('.segments-scroll');
                const item = document.querySelector(`.segment-item[data-id="${region.id}"]`);
                if (listContainer && item) {
                    const top = item.offsetTop - (listContainer.offsetHeight / 2) + (item.offsetHeight / 2);
                    listContainer.scrollTo({ top, behavior: 'smooth' });
                }

                // If it's a pin, update the counter
                if (region.data?.isPin) {
                    const sortedPins = [...this.pins].sort((a, b) => a.start - b.start);
                    const pin = this.pins.find(p => p.id === region.id);
                    if (pin) {
                        const idx = sortedPins.indexOf(pin) + 1;
                        this.updatePinCounter(idx);
                    }
                }
            }
        });

        this.wavesurfer.on('region-update-end', (region) => {
             if (region.data?.isSegment) {
                 // Update segment times in our list
                 const idx = this.segments.findIndex(s => s.id === region.id);
                 if (idx !== -1) {
                     this.segments[idx].start = region.start;
                     this.segments[idx].end = region.end;
                     this.renderSegments();
                 }
             }
        });
    }

    setupEventListeners() {
        const playBtn = document.getElementById('slicer-play-btn');
        playBtn.addEventListener('click', () => {
            this.wavesurfer.playPause();
            playBtn.innerHTML = this.wavesurfer.isPlaying() ? '<i class="fas fa-pause"></i>' : '<i class="fas fa-play"></i>';
        });

        // Hold Shift to ignore region overlays and allow precise click-to-seek on the waveform.
        // (This makes the playhead movable even when segments cover the waveform.)
        const waveformEl = document.getElementById('waveform');
        if (waveformEl && !this._shiftSeekHandlersInstalled) {
            this._shiftSeekHandlersInstalled = true;
            const enableShiftSeek = () => waveformEl.classList.add('shift-seek-mode');
            const disableShiftSeek = () => waveformEl.classList.remove('shift-seek-mode');

            document.addEventListener('keydown', (e) => {
                if (e.key === 'Shift') enableShiftSeek();
            });
            document.addEventListener('keyup', (e) => {
                if (e.key === 'Shift') disableShiftSeek();
            });
            window.addEventListener('blur', disableShiftSeek);
        }

        // Playback speed selector
        const speedSelect = document.getElementById('slicer-speed');
        if (speedSelect) {
            speedSelect.addEventListener('change', (e) => {
                const speed = parseFloat(e.target.value);
                if (this.wavesurfer) {
                    this.wavesurfer.setPlaybackRate(speed);
                }
            });
        }

        const pinBtn = document.getElementById('btn-add-pin');
        if (pinBtn) {
            pinBtn.addEventListener('click', () => this.addPin());
        }

        const prevPinBtn = document.getElementById('btn-prev-pin');
        if (prevPinBtn) {
            prevPinBtn.onclick = () => this.navigatePins(-1);
        }

        const nextPinBtn = document.getElementById('btn-next-pin');
        if (nextPinBtn) {
            nextPinBtn.onclick = () => this.navigatePins(1);
        }

        const zoomInput = document.getElementById('slicer-zoom');
        zoomInput.addEventListener('input', (e) => {
            this.wavesurfer.zoom(Number(e.target.value));
        });

        // Add segment
        const addBtn = document.getElementById('btn-add-segment');
        addBtn.addEventListener('click', () => this.addCurrentSelection());

        // Download Zip
        const dl = document.getElementById('btn-download-zip');
        if (dl) dl.addEventListener('click', () => this.downloadDatasetZip());

        this.setupListSelectionBox();

        // Segment tools
        const btnMergeSelected = document.getElementById('btn-merge-selected');
        if (btnMergeSelected) {
            btnMergeSelected.onclick = () => this.mergeSelected();
        }

        const btnRemoveSelected = document.getElementById('btn-remove-selected');
        if (btnRemoveSelected) {
            btnRemoveSelected.onclick = () => this.removeSelected();
        }

        const btnMergeGaps = document.getElementById('btn-merge-gaps');
        if (btnMergeGaps) {
            btnMergeGaps.onclick = () => this.mergeSmallGapsAll();
        }

        const btnRemoveShorts = document.getElementById('btn-remove-shorts');
        if (btnRemoveShorts) {
            btnRemoveShorts.onclick = () => this.removeShortSegmentsAll();
        }

        const btnWhitelistFilter = document.getElementById('btn-whitelist-filter');
        if (btnWhitelistFilter) {
            btnWhitelistFilter.onclick = () => this.filterByVoice('keep');
        }

        const btnBlacklistFilter = document.getElementById('btn-blacklist-filter');
        if (btnBlacklistFilter) {
            btnBlacklistFilter.onclick = () => this.filterByVoice('remove');
        }

        // Settings persistence
        const settingsRoot = this.container.querySelector('.slicer-settings');
        if (settingsRoot) {
            settingsRoot.addEventListener('change', () => this._readInputsToSettings());
        }
        const resetBtn = document.getElementById('btn-settings-reset');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                this.settings = this._defaultSettings();
                this._saveSettings();
                this._applySettingsToInputs();
            });
        }
        
        // Auto-detect silence (Python parity): populate segments, don't export.
        document.getElementById('btn-auto-detect').addEventListener('click', async () => {
            this._readInputsToSettings();
            const cfg = this.settings.autoDetect;
            const currentVoice = this.voiceName;

            if (this.segments.length > 0 && cfg.clear_existing) {
                if (!confirm('This will clear your current segment list. Continue?')) return;
            }

            const { 
                min_silence_len_ms, 
                silence_thresh_offset_db, 
                pad_ms, 
                min_segment_ms 
            } = cfg;

            if (!Number.isFinite(min_silence_len_ms) || min_silence_len_ms < 0) { alert('Invalid min silence length.'); return; }
            if (!Number.isFinite(silence_thresh_offset_db)) { alert('Invalid threshold offset.'); return; }
            if (!Number.isFinite(pad_ms) || pad_ms < 0) { alert('Invalid pad ms.'); return; }
            if (!Number.isFinite(min_segment_ms) || min_segment_ms < 0) { alert('Invalid minimum segment length.'); return; }

            const btn = document.getElementById('btn-auto-detect');
            const originalHtml = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Detecting...';
            btn.disabled = true;

            try {
                const res = await fetch('/api/training/detect-nonsilent', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        voice: currentVoice,
                        min_silence_len_ms: Math.floor(min_silence_len_ms),
                        silence_thresh_offset_db,
                        pad_ms: Math.floor(pad_ms),
                        min_segment_ms: Math.floor(min_segment_ms)
                    })
                });

                if (!res.ok) {
                    const msg = await res.text();
                    alert(msg);
                    return;
                }

                // Race check
                if (this.voiceName !== currentVoice) return;

                const data = await res.json();
                if (data.status !== 'ok') {
                    alert('Detection failed. Check server logs.');
                    return;
                }

                const segs = Array.isArray(data.segments) ? data.segments : [];
                const newSegs = segs.map((s, idx) => ({
                    id: 'seg_' + Date.now() + '_' + idx,
                    start: (Number(s.start_ms) / 1000.0),
                    end: (Number(s.end_ms) / 1000.0),
                    name: `segment_${(idx + 1).toString().padStart(3, '0')}.wav`,
                    voice_id: null
                }));

                this.segments = cfg.clear_existing ? newSegs : (this.segments.concat(newSegs));
                this.selectedSegmentIds.clear();
                this.lastSelectedIndex = null;
                this._syncRegions();
                this.renderSegments();
                this._saveState();

                alert(`Auto-detected ${this.segments.length} segments.`);
            } catch (e) {
                console.error(e);
                alert('Auto-detect failed. Check server logs.');
            } finally {
                btn.innerHTML = originalHtml;
                btn.disabled = false;
            }
        });
    }

    async downloadDatasetZip() {
        if (!this.voiceName) return;
        // Plain navigation triggers browser download.
        window.location.href = `/api/training/download-wavs-zip?voice=${encodeURIComponent(this.voiceName)}`;
    }

    updateTimeDisplay() {
        const timeEl = document.getElementById('slicer-time');
        if (!timeEl) return;
        const time = this.wavesurfer.getCurrentTime();
        timeEl.textContent = this.formatTime(time);
    }

    formatTime(seconds) {
        const date = new Date(0);
        date.setSeconds(seconds);
        const ms = Math.floor((seconds % 1) * 1000).toString().padStart(3, '0');
        return date.toISOString().substr(14, 5) + '.' + ms;
    }

    updateSelectionInfo(region) {
        if (!region) return;

        // Ignore accidental tiny drags for selection (blue) only
        if (!region.data?.isSegment && Math.abs(region.end - region.start) < 0.05) {
            try { region.remove(); } catch (e) {}
            this.clearCurrentSelection();
            return;
        }

        const isExisting = !!region.data?.isSegment;
        
        const startEl = document.getElementById('sel-start');
        const endEl = document.getElementById('sel-end');
        const durEl = document.getElementById('sel-duration');
        const addBtn = document.getElementById('btn-add-segment');
        const previewBtn = document.getElementById('btn-play-sel');
        const deleteBtn = document.getElementById('btn-delete-sel');
        
        if (startEl) startEl.textContent = this.formatTime(region.start);
        if (endEl) endEl.textContent = this.formatTime(region.end);
        if (durEl) durEl.textContent = (region.end - region.start).toFixed(3) + 's';
        
        if (addBtn) {
            addBtn.disabled = isExisting;
            addBtn.innerHTML = isExisting ? '<i class="fas fa-check"></i> Already Saved' : '<i class="fas fa-plus"></i> Add Clip';
            
            if (isExisting) {
                addBtn.classList.remove('btn-primary');
                addBtn.classList.add('btn-secondary');
                addBtn.style.opacity = '0.4';
                addBtn.style.cursor = 'not-allowed';
            } else {
                addBtn.classList.add('btn-primary');
                addBtn.classList.remove('btn-secondary');
                addBtn.style.opacity = '1';
                addBtn.style.cursor = 'pointer';
            }
        }

        if (previewBtn) {
            previewBtn.disabled = false;
            previewBtn.onclick = (e) => {
                if (e) e.stopPropagation();
                region.play();
            };
        }

        if (deleteBtn) {
            deleteBtn.disabled = false;
            deleteBtn.onclick = (e) => {
                if (e) e.stopPropagation();
                if (isExisting) {
                    this.removeSegment(region.id);
                } else {
                    region.remove();
                    this.clearCurrentSelection();
                }
            };
        }
    }

    addCurrentSelection() {
        const selectionRegion = Object.values(this.wavesurfer.regions.list).find(r => !r.data?.isSegment && !r.data?.isPin);
        if (!selectionRegion) return;

        const start = selectionRegion.start;
        const end = selectionRegion.end;
        
        const id = 'seg_' + Date.now();
        const segment = {
            id: id,
            start: start,
            end: end,
            name: `segment_${(this.segments.length + 1).toString().padStart(3, '0')}.wav`,
            voice_id: null
        };

        this.segments.push(segment);
        
        // Convert to a permanent region
        selectionRegion.remove();
        const region = this.addSegmentRegion(segment);
        if (region) this.updateSelectionInfo(region);
        
        this.renderSegments();
        this._saveState();
    }

    addPin() {
        if (!this.wavesurfer) return;
        const time = this.wavesurfer.getCurrentTime();
        const id = 'pin_' + Date.now();
        const pin = {
            id: id,
            start: time, // use start for easy sorting
            time: time,
            nickname: '',
            isPin: true
        };
        this.pins.push(pin);
        
        // Add visual line
        this.addPinRegion(pin);

        this.renderSegments();
        this._saveState();
    }

    addPinRegion(pin) {
        const region = this.wavesurfer.addRegion({
            id: pin.id,
            start: pin.time,
            end: pin.time + 0.05,
            color: 'transparent',
            drag: false,
            resize: false,
            data: { isPin: true }
        });

        // Tag for CSS styling
        if (region.element) {
            region.element.classList.add('pin-region');
        }
        return region;
    }

    removePin(id, event) {
        if (event) event.stopPropagation();
        this.pins = this.pins.filter(p => p.id !== id);
        const region = this.wavesurfer.regions.list[id];
        if (region) region.remove();
        this.renderSegments();
        this._saveState();
    }

    updatePinNickname(id, nickname) {
        const pin = this.pins.find(p => p.id === id);
        if (pin) pin.nickname = nickname;
        this._saveState();
    }

    navigatePins(direction) {
        if (this.pins.length === 0) return;
        
        const scrollArea = this.container.querySelector('.segments-scroll');
        if (!scrollArea) return;

        // Get sorted pins (they should already be sorted from render)
        const sortedPins = [...this.pins].sort((a, b) => a.start - b.start);
        
        // Find current "active" pin by checking scroll height or just stepping through
        // If we want to be smart, we find the first pin that's currently visible
        const currentScroll = scrollArea.scrollTop;
        const viewportMiddle = currentScroll + (scrollArea.offsetHeight / 2);

        let targetPin = null;

        if (direction > 0) {
            // Find first pin below the current viewport middle
            targetPin = sortedPins.find(p => {
                const el = scrollArea.querySelector(`.segment-item[data-id="${p.id}"]`);
                return el && (el.offsetTop > currentScroll + 50); // small buffer
            });
            // If none found below, loop to first
            if (!targetPin) targetPin = sortedPins[0];
        } else {
            // Find last pin above the current viewport middle
            const reversed = [...sortedPins].reverse();
            targetPin = reversed.find(p => {
                const el = scrollArea.querySelector(`.segment-item[data-id="${p.id}"]`);
                return el && (el.offsetTop < currentScroll - 50);
            });
            // If none found above, loop to last
            if (!targetPin) targetPin = sortedPins[sortedPins.length - 1];
        }

        if (targetPin) {
            const item = scrollArea.querySelector(`.segment-item[data-id="${targetPin.id}"]`);
            if (item) {
                const top = item.offsetTop - (scrollArea.offsetHeight / 2) + (item.offsetHeight / 2);
                scrollArea.scrollTo({ top, behavior: 'smooth' });
                
                // Update counter
                const targetIdx = sortedPins.indexOf(targetPin) + 1;
                this.updatePinCounter(targetIdx);
            }
        }
    }

    updatePinCounter(current = 0) {
        const counter = document.getElementById('pin-counter');
        if (counter) {
            counter.textContent = `${current}/${this.pins.length}`;
        }
    }

    addSegmentRegion(segment) {
        const region = this.wavesurfer.addRegion({
            id: segment.id,
            start: segment.start,
            end: segment.end,
            color: 'rgba(34, 197, 94, 0.14)',
            drag: true,
            resize: true,
            data: { isSegment: true }
        });

        // Tag for CSS styling
        if (region.element) {
            region.element.classList.add('segment-region');
        }
        return region;
    }

    renderSegments() {
        const container = document.getElementById('segments-container');
        const countBadge = document.getElementById('segment-count');
        const selectedBadge = document.getElementById('selected-count');
        const btnMerge = document.getElementById('btn-merge-selected');
        const btnRemove = document.getElementById('btn-remove-selected');
        
        if (!container) return; // UI not currently visible or rendered as slicer

        // Keep segments sorted by time for stable UX.
        this.segments.sort((a, b) => (a.start - b.start) || (a.end - b.end));
        this.pins.sort((a, b) => a.start - b.start);

        const combined = [...this.segments, ...this.pins].sort((a, b) => {
            const startDiff = a.start - b.start;
            if (startDiff !== 0) return startDiff;
            // If timestamps match, favor pins appearing after segments starting at the same time
            if (a.isPin && !b.isPin) return 1;
            if (!a.isPin && b.isPin) return -1;
            return (a.end || a.start) - (b.end || b.start);
        });

        if (countBadge) countBadge.textContent = this.segments.length;
        this.updatePinCounter();
        if (selectedBadge) {
            selectedBadge.textContent = `${this.selectedSegmentIds.size} selected`;
        }
        if (btnMerge) btnMerge.disabled = this.selectedSegmentIds.size < 2;
        if (btnRemove) btnRemove.disabled = this.selectedSegmentIds.size < 1;
        
        if (combined.length === 0) {
            container.innerHTML = '<div class="empty-state" style="padding: 1rem"><p class="text-xs">No segments added yet.</p></div>';
            return;
        }

        container.innerHTML = combined.map((item, idx) => {
            if (item.isPin) {
                return `
                <div class="segment-item pin-item" data-id="${item.id}" onclick="slicer.onPinClick('${item.id}', event)">
                    <span class="segment-index"><i class="fas fa-thumbtack" style="color:#ef4444; font-size: 0.8rem;"></i></span>
                    <div class="segment-times" style="color: #ef4444; font-weight: 600;">
                        ${this.formatTime(item.start)}
                    </div>
                    <div class="pin-nickname-container">
                        <input type="text" class="pin-nickname-input" placeholder="Pin nickname..." value="${item.nickname || ''}" 
                               onchange="slicer.updatePinNickname('${item.id}', this.value)"
                               title="Enter a nickname for this pin">
                    </div>
                    <div class="segment-actions">
                        <button class="icon-btn-sm text-danger" onclick="slicer.removePin('${item.id}', event)" title="Delete Pin"><i class="fas fa-times"></i></button>
                    </div>
                </div>
                `;
            }

            const seg = item;
            const durMs = Math.max(0, Math.round((seg.end - seg.start) * 1000));
            const isSelected = this.selectedSegmentIds.has(seg.id);
            const isActive = this.activeSegmentId === seg.id;
            const rowIndex = (this.segments.indexOf(seg) + 1);
            const isExported = this.exportedNames && this.exportedNames.has(seg.name);
            const isTooShort = durMs > 0 && durMs < 500;
            const totalDur = this.wavesurfer ? this.wavesurfer.getDuration() : 0;
            const isOutOfBounds = totalDur > 1 && seg.start >= totalDur;
            
            return `
            <div class="segment-item ${isSelected ? 'selected' : ''} ${isActive ? 'active' : ''} ${isOutOfBounds ? 'out-of-bounds' : ''}" 
                 data-id="${seg.id}"
                 onclick="slicer.onSegmentClick('${seg.id}', event)" 
                 ondblclick="slicer.onSegmentDoubleClick('${seg.id}', event)" 
                 title="${isOutOfBounds ? 'This segment is outside the current audio duration. It may have been created for a different file.' : 'Click to select. Double-click to focus.'}">
                
                <span class="segment-index">#${rowIndex.toString().padStart(3, '0')}</span>
                
                <div class="segment-times">
                    ${this.formatTime(seg.start)} - ${this.formatTime(seg.end)}
                </div>

                <div class="segment-duration">
                    ${durMs}ms
                </div>

                <div class="segment-meta">
                    ${seg.voice_id ? `<span class='segment-voice' title='Speaker ID'>V${seg.voice_id}</span>` : ''} 
                    ${isExported ? `<span class='segment-exported' title='Exported'>R</span>` : ''} 
                    ${isTooShort ? `<span class='segment-warning' title='Short'>S</span>` : ''}
                    ${isOutOfBounds ? `<span class='segment-warning' title='Out of bounds (beyond audio length)'>OOB</span>` : ''}
                </div>

                <div class="segment-actions">
                    <button class="icon-btn-sm" onclick="slicer.playSegment('${seg.id}', event)" title="Play" ${isOutOfBounds ? 'disabled' : ''}><i class="fas fa-play"></i></button>
                    <button class="icon-btn-sm text-success" onclick="slicer.whitelistSegment('${seg.id}', event)" title="Whitelist (Keep matching voice)" ${isOutOfBounds ? 'disabled' : ''}><i class="fas fa-check"></i></button>
                    <button class="icon-btn-sm text-warning" onclick="slicer.blacklistSegment('${seg.id}', event)" title="Blacklist (Remove matching voice)" ${isOutOfBounds ? 'disabled' : ''}><i class="fas fa-times"></i></button>
                    <button class="icon-btn-sm text-danger" onclick="slicer.removeSegment('${seg.id}', event)" title="Delete"><i class="fas fa-trash"></i></button>
                </div>
            </div>
        `;
        }).join('');
    }

    onPinClick(id, event) {
        event.stopPropagation();
        const pin = this.pins.find(p => p.id === id);
        if (!pin) return;

        // Seek the wavesurfer to the pin
        this.wavesurfer.seekTo(pin.start / this.wavesurfer.getDuration());

        // Update counter
        const sortedPins = [...this.pins].sort((a, b) => a.start - b.start);
        const idx = sortedPins.indexOf(pin) + 1;
        this.updatePinCounter(idx);
    }

    onSegmentClick(id, event) {
        event.stopPropagation();
        const idx = this.segments.findIndex(s => s.id === id);
        if (idx === -1) return;

        const isMulti = event.ctrlKey || event.metaKey;
        const isRange = event.shiftKey;

        if (!isMulti && !isRange) {
            this.selectedSegmentIds.clear();
            this.selectedSegmentIds.add(id);
            this.lastSelectedIndex = idx;
            
            // Focus on the waveform region too
            const region = this.wavesurfer.regions.list[id];
            if (region) {
                this.updateSelectionInfo(region);
                // Highlight the region on the waveform (optional: could temporarily change color)
                
                // Seek wavesurfer to the start of the clicked segment
                this.wavesurfer.seekTo(region.start / this.wavesurfer.getDuration());
            }
            
            this._updateSelectionUI();
            return;
        }

        if (isRange && this.lastSelectedIndex !== null) {
            const a = Math.min(this.lastSelectedIndex, idx);
            const b = Math.max(this.lastSelectedIndex, idx);
            for (let i = a; i <= b; i++) {
                this.selectedSegmentIds.add(this.segments[i].id);
            }
        } else {
            if (this.selectedSegmentIds.has(id)) {
                this.selectedSegmentIds.delete(id);
            } else {
                this.selectedSegmentIds.add(id);
            }
            this.lastSelectedIndex = idx;
        }

        this._updateSelectionUI();
    }

    onSegmentDoubleClick(id, event) {
        event.stopPropagation();
        this.seekTo(id);
    }

    seekTo(id) {
        const region = this.wavesurfer.regions.list[id];
        if (region) {
            this.wavesurfer.seekTo(region.start / this.wavesurfer.getDuration());
            this.activeSegmentId = id;
            this.renderSegments();
        }
    }

    playSegment(id, event) {
        if (event) event.stopPropagation();
        const region = this.wavesurfer.regions.list[id];
        if (region) {
            this.activeSegmentId = id;
            this.renderSegments();
            region.play();
        }
    }

    removeSegment(id, event) {
        if (event) event.stopPropagation();
        this.segments = this.segments.filter(s => s.id !== id);
        this.selectedSegmentIds.delete(id);
        if (this.activeSegmentId === id) {
            this.activeSegmentId = null;
            this.clearCurrentSelection();
        }
        if (this.wavesurfer.regions.list[id]) {
            this.wavesurfer.regions.list[id].remove();
        }
        this.renderSegments();
        this._saveState();
    }

    async whitelistSegment(id, event) {
        if (event) event.stopPropagation();
        
        const segment = this.segments.find(s => s.id === id);
        if (!segment) return;

        await this._filterBySegment(segment, 'keep');
    }

    async blacklistSegment(id, event) {
        if (event) event.stopPropagation();
        
        const segment = this.segments.find(s => s.id === id);
        if (!segment) return;

        await this._filterBySegment(segment, 'remove');
    }

    async _filterBySegment(segment, mode) {
        const totalDur = this.wavesurfer ? this.wavesurfer.getDuration() : 0;
        if (totalDur > 1 && segment.start >= totalDur) {
            alert('This segment is outside the current audio duration and cannot be used as a reference.');
            return;
        }

        const action = mode === 'whitelist' || mode === 'keep' ? 'KEEP' : 'REMOVE';
        const modeWord = mode === 'whitelist' || mode === 'keep' ? 'Whitelist (keep)' : 'Blacklist (remove)';
        const isWhitelist = mode === 'whitelist' || mode === 'keep';
        
        // Different explanations for whitelist vs blacklist
        let explanation, higherMeans, lowerMeans;
        if (isWhitelist) {
            explanation = `This will <strong>KEEP</strong> segments with voices similar to #${segment.id} and <strong>DELETE</strong> the rest.`;
            higherMeans = 'stricter matching → <strong>fewer</strong> segments kept (only very similar voices)';
            lowerMeans = 'looser matching → <strong>more</strong> segments kept (includes somewhat similar voices)';
        } else {
            explanation = `This will <strong>DELETE</strong> segments with voices similar to #${segment.id} and <strong>KEEP</strong> the rest.`;
            higherMeans = 'stricter matching → <strong>more</strong> segments kept (only removes very similar voices)';
            lowerMeans = 'looser matching → <strong>fewer</strong> segments kept (removes somewhat similar voices too)';
        }
        
        const content = `<div style="font-size:0.9rem;">
            <p style="margin:0 0 0.75rem 0; color:var(--text-main);">${explanation}</p>
            
            <div style="background:var(--bg-dark); padding:0.6rem; border-radius:4px; margin-bottom:0.6rem;">
                <div style="color:var(--text-main); font-weight:500; margin-bottom:0.4rem; font-size:0.85rem;">Typical values:</div>
                <div style="color:var(--text-muted); line-height:1.5; font-size:0.85rem;">
                    <div>• <strong style="color:#10b981;">0.70</strong> - Loose (${isWhitelist ? 'more segments kept' : 'fewer segments kept'})</div>
                    <div>• <strong style="color:#38bdf8;">0.78</strong> - Balanced (recommended)</div>
                    <div>• <strong style="color:#f59e0b;">0.85</strong> - Strict (${isWhitelist ? 'fewer segments kept' : 'more segments kept'})</div>
                </div>
            </div>
            
            <div style="font-size:0.8rem; color:var(--text-muted); background:var(--bg-darker); padding:0.5rem; border-radius:4px; line-height:1.5;">
                <div><strong style="color:var(--text-main);">Higher value (0.85):</strong> ${higherMeans}</div>
                <div style="margin-top:0.3rem;"><strong style="color:var(--text-main);">Lower value (0.70):</strong> ${lowerMeans}</div>
            </div>
        </div>`;
        
        const thresholdStr = await this._showModal(
            modeWord + ' matching voice?',
            content,
            true,
            '0.78'
        );
        if (thresholdStr === null) return;
        
        const threshold = Number(thresholdStr);
        if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1) {
            alert('Invalid threshold. Must be between 0 and 1.');
            return;
        }

        const key = (s, e) => `${s}-${e}`;
        const byKey = new Map(this.segments.map(seg => [key(Math.floor(seg.start*1000), Math.floor(seg.end*1000)), seg]));

        // Show progress UI
        this._showFilterProgress();
        
        // Start polling for progress
        const pollInterval = setInterval(async () => {
            try {
                const progRes = await fetch(`/api/training/segments/voice-filter/progress?voice=${encodeURIComponent(this.voiceName)}`);
                if (progRes.ok) {
                    const prog = await progRes.json();
                    if (prog.total > 0) {
                        this._updateFilterProgress(prog.current, prog.total);
                    }
                }
            } catch (e) {
                console.warn('Progress poll failed:', e);
            }
        }, 100);

        try {
            const res = await fetch('/api/training/segments/voice-filter', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    voice: this.voiceName,
                    threshold,
                    mode,
                    ref_start_ms: Math.floor(segment.start * 1000),
                    ref_end_ms: Math.floor(segment.end * 1000),
                    segments: this.segments.map(s => ({start_ms: Math.floor(s.start * 1000), end_ms: Math.floor(s.end * 1000)}))
                })
            });
            
            clearInterval(pollInterval);
            this._hideFilterProgress();
            
            if (!res.ok) {
                const msg = await res.text();
                alert(msg);
                return;
            }
            
            const data = await res.json();

            if (!data || data.status !== 'ok') {
                alert('Voice filter failed. Check server logs.');
                return;
            }

            if (data.used_trim_silence) {
                alert("Note: your resemblyzer version may have trimmed silence; timings may be slightly off.");
            }

            const keptSegments = (data.segments || [])
                .map(s => byKey.get(key(Math.floor(s.start_ms), Math.floor(s.end_ms))))
                .filter(Boolean);

            this.segments = keptSegments;
            this.selectedSegmentIds.clear();
            this.lastSelectedIndex = null;
            this._syncRegions();
            this.renderSegments();
            this._saveState();
            
            const action = mode === 'keep' ? 'Whitelisted' : 'Blacklisted';
            alert(`${action} complete. Kept ${data.kept} of ${data.total} segments.`);
        } catch (e) {
            clearInterval(pollInterval);
            this._hideFilterProgress();
            console.error(e);
            alert('Voice filter failed. Check server logs.');
        }
    }

    _getSelectedSegments() {
        return this.segments.filter(s => this.selectedSegmentIds.has(s.id));
    }

    _syncRegions() {
        if (!this.wavesurfer) return;
        // Remove old segment and pin regions
        Object.values(this.wavesurfer.regions.list).forEach(r => {
            if (r.data?.isSegment || r.data?.isPin) r.remove();
        });
        // Add current
        this.segments.forEach(seg => this.addSegmentRegion(seg));
        this.pins.forEach(pin => this.addPinRegion(pin));
    }

    mergeSelected() {
        const selected = this._getSelectedSegments();
        if (selected.length < 2) {
            alert('Select at least 2 segments to join (Ctrl/Click or drag-select).');
            return;
        }

        const sorted = selected.slice().sort((a, b) => (a.start - b.start) || (a.end - b.end));
        const start = Math.min(...sorted.map(s => s.start));
        const end = Math.max(...sorted.map(s => s.end));

        // Check for "hidden" segments between the selection to prevent messy overlaps
        const collisionCount = this.segments.filter(s => 
            !this.selectedSegmentIds.has(s.id) && 
            s.start >= start && 
            s.end <= end
        ).length;

        if (collisionCount > 0) {
            if (!confirm(`Warning: There are ${collisionCount} other segments inside this range that you haven't selected. Joining will overlap them. Proceed anyway?`)) {
                return;
            }
        }

        const keepName = sorted[0].name;
        const mergedId = 'seg_' + Date.now();
        const merged = {
            id: mergedId,
            start,
            end,
            name: keepName,
            voice_id: null
        };

        const removeIds = new Set(sorted.map(s => s.id));
        this.segments = this.segments.filter(s => !removeIds.has(s.id));
        this.segments.push(merged);

        this.selectedSegmentIds.clear();
        this.selectedSegmentIds.add(mergedId);
        this.lastSelectedIndex = this.segments.findIndex(s => s.id === mergedId);

        this._syncRegions();
        this.renderSegments();
        this._saveState();
    }

    removeSelected() {
        const selected = this._getSelectedSegments();
        if (selected.length === 0) {
            alert('No segments selected.');
            return;
        }
        if (!confirm(`Delete ${selected.length} selected segment(s)?`)) return;

        const removeIds = new Set(selected.map(s => s.id));
        this.segments = this.segments.filter(s => !removeIds.has(s.id));
        this.selectedSegmentIds.clear();
        this.lastSelectedIndex = null;

        // Remove regions
        removeIds.forEach(id => {
            if (this.wavesurfer.regions.list[id]) this.wavesurfer.regions.list[id].remove();
        });

        this.renderSegments();
        this._saveState();
    }

    mergeSmallGapsAll() {
        if (this.segments.length === 0) {
            alert('No segments to merge.');
            return;
        }

        this._readInputsToSettings();
        const gapS = Number(this.settings.bulk.merge_gap_s);
        if (!Number.isFinite(gapS) || gapS < 0) {
            alert('Invalid gap seconds.');
            return;
        }
        const maxGap = gapS;

        const segs = this.segments
            .map(s => ({...s}))
            .sort((a, b) => (a.start - b.start) || (a.end - b.end));

        const merged = [];
        let cur = segs[0];
        for (let i = 1; i < segs.length; i++) {
            const s = segs[i];
            if (s.start <= cur.end) {
                cur.end = Math.max(cur.end, s.end);
                cur.voice_id = null;
                continue;
            }
            const gap = s.start - cur.end;
            if (gap <= maxGap) {
                cur.end = Math.max(cur.end, s.end);
                cur.voice_id = null;
            } else {
                merged.push(cur);
                cur = s;
            }
        }
        merged.push(cur);

        // Re-id to avoid WaveSurfer region collisions
        this.segments = merged.map((s, idx) => ({
            id: 'seg_' + Date.now() + '_' + idx,
            start: s.start,
            end: s.end,
            name: `segment_${(idx + 1).toString().padStart(3, '0')}.wav`,
            voice_id: null
        }));

        this.selectedSegmentIds.clear();
        this.lastSelectedIndex = null;
        this._syncRegions();
        this.renderSegments();
        this._saveState();
        alert(`Merged small gaps (<= ${gapS}s). Now ${this.segments.length} segments.`);
    }

    removeShortSegmentsAll() {
        if (this.segments.length === 0) {
            alert('No segments to filter.');
            return;
        }

        this._readInputsToSettings();
        const minS = Number(this.settings.bulk.remove_short_s);
        if (!Number.isFinite(minS) || minS < 0) {
            alert('Invalid seconds.');
            return;
        }

        const before = this.segments.length;
        this.segments = this.segments.filter(s => (s.end - s.start) >= minS);
        const removed = before - this.segments.length;

        this.selectedSegmentIds.clear();
        this.lastSelectedIndex = null;
        this._syncRegions();
        this.renderSegments();
        this._saveState();
        alert(`Removed ${removed} short segments (< ${minS}s).`);
    }

    _getSelectionRegion() {
        return Object.values(this.wavesurfer.regions.list).find(r => !r.data?.isSegment);
    }

    async labelVoices() {
        if (this.segments.length === 0) {
            alert('No segments to label.');
            return;
        }
        const kStr = prompt('How many distinct voices to label? (2-8)', '2');
        if (kStr === null) return;
        const k = Number(kStr);
        if (!Number.isFinite(k) || k < 2 || k > 8) {
            alert('Invalid k.');
            return;
        }

        try {
            const res = await fetch('/api/training/segments/voice-label', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    voice: this.voiceName,
                    k: Math.floor(k),
                    segments: this.segments.map(s => ({start_ms: Math.floor(s.start * 1000), end_ms: Math.floor(s.end * 1000)}))
                })
            });

            if (!res.ok) {
                const msg = await res.text();
                alert(msg);
                return;
            }
            const data = await res.json();
            if (data.used_trim_silence) {
                alert("Note: your resemblyzer version may have trimmed silence; timings may be slightly off.");
            }
            // Apply voice ids in order
            data.segments.forEach((s, i) => {
                if (this.segments[i]) this.segments[i].voice_id = s.voice_id;
            });
            this.renderSegments();
            this._saveState();
        } catch (e) {
            console.error(e);
            alert('Voice labeling failed. Check server logs.');
        }
    }

    async filterByVoice(mode) {
        if (this.segments.length === 0) {
            alert('No segments to filter.');
            return;
        }

        // Check for selected segments
        const totalDur = this.wavesurfer ? this.wavesurfer.getDuration() : 0;
        const selectedSegments = this.segments.filter(seg => 
            this.selectedSegmentIds.has(seg.id) && 
            (totalDur <= 1 || seg.start < totalDur)
        );
        
        if (selectedSegments.length === 0) {
            alert('Please select one or more valid segments to use as voice reference.\n\nNote: Segments beyond the audio duration (OOB) cannot be used as references.');
            return;
        }

        // Use the improved threshold dialog
        const isWhitelist = mode === 'keep';
        let explanation, higherMeans, lowerMeans;
        if (isWhitelist) {
            explanation = `This will <strong>KEEP</strong> segments with voices similar to your selection and <strong>DELETE</strong> the rest.`;
            higherMeans = 'stricter matching → <strong>fewer</strong> segments kept (only very similar voices)';
            lowerMeans = 'looser matching → <strong>more</strong> segments kept (includes somewhat similar voices)';
        } else {
            explanation = `This will <strong>DELETE</strong> segments with voices similar to your selection and <strong>KEEP</strong> the rest.`;
            higherMeans = 'stricter matching → <strong>more</strong> segments kept (only removes very similar voices)';
            lowerMeans = 'looser matching → <strong>fewer</strong> segments kept (removes somewhat similar voices too)';
        }
        
        const content = `<div style="font-size:0.9rem;">
            <p style="margin:0 0 0.75rem 0; color:var(--text-main);">${explanation}</p>
            
            <div style="background:var(--bg-dark); padding:0.6rem; border-radius:4px; margin-bottom:0.6rem;">
                <div style="color:var(--text-main); font-weight:500; margin-bottom:0.4rem; font-size:0.85rem;">Typical values:</div>
                <div style="color:var(--text-muted); line-height:1.5; font-size:0.85rem;">
                    <div>• <strong style="color:#10b981;">0.70</strong> - Loose (${isWhitelist ? 'more segments kept' : 'fewer segments kept'})</div>
                    <div>• <strong style="color:#38bdf8;">0.78</strong> - Balanced (recommended)</div>
                    <div>• <strong style="color:#f59e0b;">0.85</strong> - Strict (${isWhitelist ? 'fewer segments kept' : 'more segments kept'})</div>
                </div>
            </div>
            
            <div style="font-size:0.8rem; color:var(--text-muted); background:var(--bg-darker); padding:0.5rem; border-radius:4px; line-height:1.5;">
                <div><strong style="color:var(--text-main);">Higher value (0.85):</strong> ${higherMeans}</div>
                <div style="margin-top:0.3rem;"><strong style="color:var(--text-main);">Lower value (0.70):</strong> ${lowerMeans}</div>
            </div>
        </div>`;
        
        const thresholdStr = await this._showModal(
            isWhitelist ? 'Whitelist (keep) matching voice?' : 'Blacklist (remove) matching voice?',
            content,
            true,
            '0.78'
        );
        if (thresholdStr === null) return;
        
        const threshold = Number(thresholdStr);
        if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1) {
            alert('Invalid threshold. Must be between 0 and 1.');
            return;
        }

        const key = (s, e) => `${s}-${e}`;
        const byKey = new Map(this.segments.map(seg => [key(Math.floor(seg.start*1000), Math.floor(seg.end*1000)), seg]));

        // Show progress UI
        this._showFilterProgress();
        
        // Start polling for progress
        const pollInterval = setInterval(async () => {
            try {
                const progRes = await fetch(`/api/training/segments/voice-filter/progress?voice=${encodeURIComponent(this.voiceName)}`);
                if (progRes.ok) {
                    const prog = await progRes.json();
                    if (prog.total > 0) {
                        this._updateFilterProgress(prog.current, prog.total);
                    }
                }
            } catch (e) {
                console.warn('Progress poll failed:', e);
            }
        }, 100);

        try {
            // Process each selected segment and combine results
            let allKept = new Set();
            let totalProcessed = 0;
            
            for (const refSegment of selectedSegments) {
                const res = await fetch('/api/training/segments/voice-filter', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        voice: this.voiceName,
                        threshold,
                        mode,
                        ref_start_ms: Math.floor(refSegment.start * 1000),
                        ref_end_ms: Math.floor(refSegment.end * 1000),
                        segments: this.segments.map(s => ({start_ms: Math.floor(s.start * 1000), end_ms: Math.floor(s.end * 1000)}))
                    })
                });
                if (!res.ok) {
                    clearInterval(pollInterval);
                    this._hideFilterProgress();
                    const msg = await res.text();
                    alert(msg);
                    return;
                }
                const data = await res.json();
                
                if (!data || data.status !== 'ok') {
                    clearInterval(pollInterval);
                    this._hideFilterProgress();
                    alert('Voice filter failed. Check server logs.');
                    return;
                }
                
                // For whitelist mode, accumulate matching segments (union)
                // For blacklist mode, accumulate segments to remove (union)
                if (mode === 'keep') {
                    // Union: add all segments that matched this reference
                    (data.segments || []).forEach(s => {
                        const k = key(Math.floor(s.start_ms), Math.floor(s.end_ms));
                        allKept.add(k);
                    });
                } else {
                    // For blacklist, we need to track what to remove
                    // First iteration: initialize with all segments
                    if (totalProcessed === 0) {
                        this.segments.forEach(seg => {
                            const k = key(Math.floor(seg.start * 1000), Math.floor(seg.end * 1000));
                            allKept.add(k);
                        });
                    }
                    // Remove segments that matched this reference
                    (data.segments || []).forEach(s => {
                        const k = key(Math.floor(s.start_ms), Math.floor(s.end_ms));
                        allKept.delete(k);
                    });
                }
                
                totalProcessed++;
            }

            clearInterval(pollInterval);
            this._hideFilterProgress();

            // Build final segment list from accumulated keys
            const keptSegments = Array.from(allKept)
                .map(k => byKey.get(k))
                .filter(Boolean)
                .sort((a, b) => a.start - b.start);

            const originalCount = this.segments.length;
            this.segments = keptSegments;
            this.selectedSegmentIds.clear();
            this.lastSelectedIndex = null;
            this._syncRegions();
            this.renderSegments();
            this._saveState();
            
            const modeText = mode === 'keep' ? 'whitelist' : 'blacklist';
            alert(`${modeText.charAt(0).toUpperCase() + modeText.slice(1)} filter complete using ${selectedSegments.length} reference segment(s).\n\nKept ${this.segments.length} of ${originalCount} segments.`);
        } catch (e) {
            clearInterval(pollInterval);
            this._hideFilterProgress();
            console.error(e);
            alert('Voice filter failed. Check server logs.');
        }
    }

    async splitByVoiceChanges() {
        const winStr = prompt('Embedding window size (seconds). Typical: 1.0 to 2.0', '1.5');
        if (winStr === null) return;
        const win_s = Number(winStr);
        if (!Number.isFinite(win_s) || win_s < 0.3) {
            alert('Invalid window size.');
            return;
        }

        const hopStr = prompt('Hop size (seconds) between windows. Typical: 0.5', String(Math.min(0.5, win_s)));
        if (hopStr === null) return;
        const hop_s = Number(hopStr);
        if (!Number.isFinite(hop_s) || hop_s < 0.1 || hop_s > win_s) {
            alert('Invalid hop size (must be <= window size).');
            return;
        }

        const thrStr = prompt('Similarity threshold (0..1). Typical: 0.70 to 0.85', '0.78');
        if (thrStr === null) return;
        const thresh = Number(thrStr);
        if (!Number.isFinite(thresh) || thresh < 0 || thresh > 1) {
            alert('Invalid threshold.');
            return;
        }

        const minStr = prompt('Minimum segment length (seconds). Shorter segments are merged into neighbors.', '1.0');
        if (minStr === null) return;
        const min_seg_s = Number(minStr);
        if (!Number.isFinite(min_seg_s) || min_seg_s < 0) {
            alert('Invalid min segment length.');
            return;
        }

        let base_segments = null;
        if (this.segments.length > 0) {
            const useExisting = confirm('You already have segments. OK = split within existing segments (recommended). Cancel = split the entire file.');
            if (useExisting) {
                base_segments = this.segments.map(s => ({start_ms: Math.floor(s.start * 1000), end_ms: Math.floor(s.end * 1000)}));
            }
        }

        try {
            const res = await fetch('/api/training/segments/voice-split', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    voice: this.voiceName,
                    base_segments,
                    win_s,
                    hop_s,
                    thresh,
                    min_seg_s
                })
            });
            if (!res.ok) {
                const msg = await res.text();
                alert(msg);
                return;
            }
            const data = await res.json();
            if (data.used_trim_silence) {
                alert("Note: your resemblyzer version may have trimmed silence; timings may be slightly off.");
            }

            // Replace segments
            this.segments = data.segments.map((s, idx) => ({
                id: 'seg_' + Date.now() + '_' + idx,
                start: (s.start_ms / 1000.0),
                end: (s.end_ms / 1000.0),
                name: `segment_${(idx + 1).toString().padStart(3, '0')}.wav`,
                voice_id: null
            }));
            this.selectedSegmentIds.clear();
            this.lastSelectedIndex = null;
            this._syncRegions();
            this.renderSegments();
            this._saveState();
            alert(`Voice split complete: ${this.segments.length} segments.`);
        } catch (e) {
            console.error(e);
            alert('Voice split failed. Check server logs.');
        }
    }

    async exportAll() {
        if (this.segments.length === 0) {
            // No segments is fine, just means nothing to export
            return true;
        }
        
        const progressWrap = this.container.querySelector('.slicer-export-progress');
        const progressFill = document.getElementById('export-progress-fill');
        const progressCount = document.getElementById('export-progress-count');
        const progressLabel = document.getElementById('export-progress-label');

        if (progressWrap) progressWrap.style.display = 'block';
        if (progressLabel) progressLabel.textContent = 'Exporting clips to dataset/wav';
        if (progressCount) progressCount.textContent = `0 / ${this.segments.length}`;
        if (progressFill) progressFill.style.width = '0%';

        let successCount = 0;
        for (let i = 0; i < this.segments.length; i++) {
            const seg = this.segments[i];
            if (progressCount) progressCount.textContent = `${i + 1} / ${this.segments.length}`;
            if (progressFill) progressFill.style.width = `${Math.round(((i + 1) / this.segments.length) * 100)}%`;
            
            try {
                const res = await fetch('/api/training/export-segment', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        voice: this.voiceName,
                        start_ms: Math.floor(seg.start * 1000),
                        end_ms: Math.floor(seg.end * 1000),
                        // Match Python slicer naming: 1.wav, 2.wav, ...
                        naming_mode: 'numeric'
                    })
                });
                if (res.ok) {
                    successCount++;
                    try {
                        const data = await res.json();
                        if (data && data.path) {
                            // Server may rename to avoid overwrites; keep UI consistent.
                            seg.name = String(data.path);
                            this.exportedNames.add(seg.name);
                        }
                    } catch (e) {
                        // Ignore JSON parse issues; export still succeeded.
                    }
                }
            } catch (e) { console.error(e); }
        }

        if (progressWrap) {
            // Wait a moment so user sees 100%
            setTimeout(() => {
                progressWrap.style.display = 'none';
            }, 1000);
        }
        
        // Match Python slicer UX: clear local segment list after successful export.
        if (successCount === this.segments.length) {
            this.segments = [];
            this.pins = []; // Also clear pins after export if they were part of the session
            this.selectedSegmentIds.clear();
            this.lastSelectedIndex = null;
            try {
                localStorage.removeItem(`slicer_state_${this.voiceName}`);
            } catch (e) {}
            this._syncRegions();
            this.renderSegments();
            this.clearCurrentSelection();
        } else {
            this.renderSegments();
        }

        return true;
    }

    _saveState() {
        // Save to localStorage so you don't lose work on refresh
        const state = {
            segments: this.segments,
            pins: this.pins
        };
        localStorage.setItem(`slicer_state_${this.voiceName}`, JSON.stringify(state));
    }

    loadExistingSegments() {
        const saved = localStorage.getItem(`slicer_state_${this.voiceName}`);
        if (saved) {
            const data = JSON.parse(saved);
            
            // Support both old array-only format and new object format
            if (Array.isArray(data)) {
                this.segments = data;
                this.pins = [];
            } else {
                this.segments = data.segments || [];
                this.pins = data.pins || [];
            }

            this.selectedSegmentIds.clear();
            this.lastSelectedIndex = null;
            setTimeout(() => {
                this._syncRegions();
                this.renderSegments();
            }, 1000); // Wait for wavesurfer to load
        }
    }

    _showFilterProgress() {
        const progressContainer = document.querySelector('.slicer-export-progress');
        const progressLabel = document.getElementById('export-progress-label');
        const progressCount = document.getElementById('export-progress-count');
        const progressFill = document.getElementById('export-progress-fill');
        
        if (progressContainer && progressLabel && progressCount && progressFill) {
            progressLabel.textContent = 'Filtering voice...';
            progressCount.textContent = '0 / 0';
            progressFill.style.width = '0%';
            progressContainer.style.display = 'block';
        }
    }

    _updateFilterProgress(current, total) {
        const progressCount = document.getElementById('export-progress-count');
        const progressFill = document.getElementById('export-progress-fill');
        
        if (progressCount && progressFill) {
            progressCount.textContent = `${current} / ${total}`;
            const percent = total > 0 ? (current / total) * 100 : 0;
            progressFill.style.width = `${percent}%`;
        }
    }

    _hideFilterProgress() {
        const progressContainer = document.querySelector('.slicer-export-progress');
        if (progressContainer) {
            progressContainer.style.display = 'none';
        }
    }

    /**
     * Show custom modal dialog
     * @param {string} title - Modal title
     * @param {string} content - Modal content/message
     * @param {boolean} showInput - Whether to show input field
     * @param {string} defaultValue - Default input value
     * @returns {Promise<string|null>} - Input value or null if cancelled
     */
    _showModal(title, content, showInput = false, defaultValue = '') {
        return new Promise((resolve) => {
            const overlay = document.getElementById('slicer-modal-overlay');
            const modal = document.getElementById('slicer-modal');
            const titleEl = document.getElementById('slicer-modal-title');
            const contentEl = document.getElementById('slicer-modal-content');
            const inputWrap = document.getElementById('slicer-modal-input-wrap');
            const input = document.getElementById('slicer-modal-input');
            const okBtn = document.getElementById('slicer-modal-ok');
            const cancelBtn = document.getElementById('slicer-modal-cancel');

            titleEl.textContent = title;
            contentEl.innerHTML = content;
            
            if (showInput) {
                inputWrap.style.display = 'block';
                input.value = defaultValue;
                setTimeout(() => {
                    input.focus();
                    input.select();
                }, 100);
            } else {
                inputWrap.style.display = 'none';
            }

            overlay.style.display = 'block';

            const cleanup = () => {
                overlay.style.display = 'none';
                okBtn.onclick = null;
                cancelBtn.onclick = null;
                input.onkeydown = null;
            };

            okBtn.onclick = () => {
                const value = showInput ? input.value : 'OK';
                cleanup();
                resolve(value);
            };

            cancelBtn.onclick = () => {
                cleanup();
                resolve(null);
            };

            if (showInput) {
                input.onkeydown = (e) => {
                    if (e.key === 'Enter') {
                        okBtn.click();
                    } else if (e.key === 'Escape') {
                        cancelBtn.click();
                    }
                };
            }

            // Close on overlay click
            overlay.onclick = (e) => {
                if (e.target === overlay) {
                    cancelBtn.click();
                }
            };
        });
    }
}
