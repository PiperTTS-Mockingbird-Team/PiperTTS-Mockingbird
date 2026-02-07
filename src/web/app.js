/**
 * PiperTTS Mockingbird Dashboard - Main Application Module
 * Licensed under the MIT License.
 * Copyright (c) 2026 PiperTTS Mockingbird Developers
 */

/**
 * This script initializes and manages the overall dashboard UI, including:
 * - Tab navigation and content switching.
 * - Real-time TTS (Text-to-Speech) generation and playback.
 * - Voice inventory management and nickname updates.
 * - Voice Dojo (project) creation and launching the multi-step training wizard.
 * - System monitoring (logs, GPU stats, server status).
 * - Storage management and cleanup.
 */

/**
 * Global UI Element Cache.
 * Minimizes DOM lookups in high-frequency update loops.
 */
const ui = {
    // Telemetry & GPU
    gpuContainer: null,
    gpuUtilText: null,
    gpuUtilBar: null,
    gpuVramText: null,
    gpuTempText: null,
    trainStep: null,
    logPreview: null,
    
    // Status Indicators
    statusDots: [],
    statusText: [],
    overviewTab: null,
    
    // Voice Stats
    voicesCountStat: null,
    voicesActiveStat: null,
    currentVoiceHeader: null,
    voiceCountBadge: null,
    activeTrainingBtn: null
};

/**
 * Simplified preprocessing state tracking
 */
let preprocessState = {
    isManualStart: false,
    lastKnownRunning: false,
    pollInterval: null
};

document.addEventListener('DOMContentLoaded', () => {
    // Populate UI Cache
    ui.gpuContainer = document.getElementById('gpu-stats-container');
    ui.gpuUtilText = document.getElementById('gpu-util-text');
    ui.gpuUtilBar = document.getElementById('gpu-util-bar');
    ui.gpuVramText = document.getElementById('gpu-vram-text');
    ui.gpuTempText = document.getElementById('gpu-temp-text');
    ui.trainStep = document.getElementById('step-train');
    ui.logPreview = document.getElementById('log-preview');
    ui.statusDots = document.querySelectorAll('.status-indicator .dot');
    ui.statusText = document.querySelectorAll('.status-indicator');
    ui.overviewTab = document.querySelector('.nav-links li[data-tab="overview"]');
    ui.voicesCountStat = document.getElementById('voices-count-stat');
    ui.voicesActiveStat = document.getElementById('voices-active-stat');
    ui.currentVoiceHeader = document.getElementById('current-voice-name');
    ui.voiceCountBadge = document.getElementById('voice-count');
    ui.activeTrainingBtn = document.getElementById('active-training-btn');

    const navLinks = document.querySelectorAll('.nav-links li');
    const tabContents = document.querySelectorAll('.tab-content');
    const tabTitle = document.getElementById('tab-title');

    // Header shortcut to the active Training Cockpit when training is active
    if (ui.activeTrainingBtn) {
        ui.activeTrainingBtn.addEventListener('click', async () => {
            try {
                const tRes = await fetch('/api/training/active');
                if (tRes.ok) {
                    const tData = await tRes.json();
                    const voices = Array.isArray(tData.voices) ? tData.voices : [];
                    const activeVoice = voices[0];

                    // If we know which dojo is training, jump directly into its cockpit.
                    if (activeVoice && typeof window.openVoiceEditor === 'function') {
                        window.openVoiceEditor(activeVoice, 'train');
                        return;
                    }
                }
            } catch (e) {
                /* fall through */
            }

            // Fallback: open Voice Studio tab.
            const trainingTabLink = document.querySelector('.nav-links li[data-tab="training"]');
            if (trainingTabLink) trainingTabLink.click();
        });
    }

    /**
     * Initialize the Advanced Slicer component.
     * Accessible globally via window.slicer for interactions within other scripts.
     */
    window.slicer = new AdvancedSlicer('advanced-slicer-root');

    /**
     * Global Tab Switching Logic
     * Handles updating the active link, visible content, and triggering context-aware refreshes.
     */
    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            const targetTab = link.getAttribute('data-tab');
            
            navLinks.forEach(l => l.classList.remove('active'));
            link.classList.add('active');

            tabContents.forEach(content => {
                content.style.display = content.id === `tab-${targetTab}` ? 'block' : 'none';
            });

            tabTitle.textContent = link.querySelector('span').textContent;

            // Trigger specific tab refreshes to ensure data is fresh when the user switches view
            if (targetTab === 'training') fetchDojos();
            if (targetTab === 'logs') fetchLogs();
            if (targetTab === 'settings') fetchSettings();
            if (targetTab === 'storage') refreshStorage();
            if (targetTab === 'integrations' && window.haIntegration) {
                window.haIntegration.refreshVoiceList();
                window.haIntegration.checkWyomingStatus();
            }
        });
    });

    /**
     * Storage Sub-tab switching
     * Manages nested navigation within the Storage management screen.
     */
    const subSidebarItems = document.querySelectorAll('.sub-sidebar-item');
    const storageSubtabs = document.querySelectorAll('.storage-subtab');

    subSidebarItems.forEach(item => {
        item.addEventListener('click', () => {
            const target = item.getAttribute('data-subtab');
            
            subSidebarItems.forEach(i => i.classList.remove('active'));
            item.classList.add('active');

            storageSubtabs.forEach(tab => {
                tab.style.display = tab.id === target ? 'block' : 'none';
            });
        });
    });

    // TTS Control Elements
    const speakBtn = document.getElementById('speak-btn');
    const ttsInput = document.getElementById('tts-input');
    const voiceSelect = document.getElementById('voice-select');
    
    // Auto-save voice selection to server config when changed
    if (voiceSelect) {
        voiceSelect.addEventListener('change', async () => {
             const voiceName = voiceSelect.value;
             if (!voiceName) return;

             // Update header and stats immediately for better UX
             const selectedOption = voiceSelect.options[voiceSelect.selectedIndex];
             const displayName = selectedOption ? selectedOption.textContent.split(' (')[0] : voiceName;
             
             if (ui.currentVoiceHeader) ui.currentVoiceHeader.textContent = displayName;
             if (ui.voicesActiveStat) ui.voicesActiveStat.textContent = displayName;

             try {
                 console.log(`Setting default voice to: ${voiceName}`);
                 await fetch('/api/config', {
                     method: 'POST',
                     headers: { 'Content-Type': 'application/json' },
                     body: JSON.stringify({ "voice_model": voiceName })
                 });
                 
                 // Sync with the inventory table (refresh "Active" badge)
                 if (typeof fetchVoices === 'function') fetchVoices();
             } catch (err) {
                 console.error('Failed to save default voice:', err);
             }
        });
    }

    const playerContainer = document.getElementById('player-container');
    const audioPlayer = document.getElementById('audio-player');
    const synthesisTimeLabel = document.getElementById('synthesis-time');

    /**
     * Curated list of varied sentences for testing voice prosody and character.
     */
    const randomSentences = [
        "Hey there! I'm Piper, your friendly text-to-speech assistant!",
        "Testing one two three! Sounds great, doesn't it?",
        "Hello! I can speak anything you type. Pretty cool, right?",
        "Beep boop! Just kidding, I'm much better than a robot!",
        "Ready to chat? I'm all ears... well, actually all voice!"
    ];

    /**
     * Populates the TTS input with a random sentence from the list.
     */
    function getRandomSentence() {
        return randomSentences[Math.floor(Math.random() * randomSentences.length)];
    }

    // Speed Control State
    let currentTtsSpeed = 1.0;
    const speedBtns = document.querySelectorAll('.speed-btn');
    speedBtns.forEach(btn => {
        btn.addEventListener('click', () => {
             speedBtns.forEach(b => {
                 b.classList.remove('active', 'btn-primary');
                 b.classList.add('btn-ghost');
             });
             btn.classList.remove('btn-ghost');
             btn.classList.add('active', 'btn-primary');
             currentTtsSpeed = parseFloat(btn.getAttribute('data-speed'));
             const lbl = document.getElementById('speed-label-val');
             if(lbl) lbl.textContent = currentTtsSpeed + 'x';
             
             // Update active player immediately so speed changes in real-time
             if (audioPlayer) {
                 audioPlayer.playbackRate = currentTtsSpeed;
             }
        });
    });

    // Stop Button
    const stopTestBtn = document.getElementById('stop-test-btn');
    if (stopTestBtn) {
        stopTestBtn.addEventListener('click', async () => {
            if (audioPlayer) {
                audioPlayer.pause();
                audioPlayer.currentTime = 0;
            }
            try {
                await fetch('/api/cancel', { method: 'POST' });
            } catch(e) { console.error(e); }
        });
    }

    // Handles legacy buttons if present, or new UI logic specific initialization
    const randomChk = document.getElementById('random-checkbox');
    // Pre-fill if empty
    if (!ttsInput.value && !randomChk) {
         ttsInput.value = getRandomSentence();
    }

    // Initialize Server Connectivity Features
    initializeServerConnectivity();
    
    /**
     * Initialize Server Connectivity UI and event handlers
     */
    function initializeServerConnectivity() {
        // Get server URL and display it
        const serverUrlDisplay = document.getElementById('server-url-display');
        const serverHostDisplay = document.getElementById('server-host-display');
        const serverPortDisplay = document.getElementById('server-port-display');
        
        if (serverUrlDisplay) {
            const port = window.location.port || '5002';
            const hostname = window.location.hostname || '127.0.0.1';
            serverUrlDisplay.value = `http://${hostname}:${port}`;
            
            // Update host and port displays
            if (serverHostDisplay) {
                serverHostDisplay.value = hostname;
            }
            if (serverPortDisplay) {
                serverPortDisplay.value = port;
            }
        }

        // Copy URL button
        const copyUrlBtn = document.getElementById('copy-url-btn');
        if (copyUrlBtn) {
            copyUrlBtn.addEventListener('click', async () => {
                const url = serverUrlDisplay.value;
                try {
                    await navigator.clipboard.writeText(url);
                    const originalHTML = copyUrlBtn.innerHTML;
                    copyUrlBtn.innerHTML = '✓ Copied!';
                    setTimeout(() => {
                        copyUrlBtn.innerHTML = originalHTML;
                    }, 2000);
                } catch (err) {
                    console.error('Failed to copy:', err);
                }
            });
        }

        // Startup checkbox
        const startupCheckbox = document.getElementById('startup-checkbox');
        if (startupCheckbox) {
            // Load current startup state
            fetch('/api/startup-status').then(r => r.json()).then(data => {
                startupCheckbox.checked = data.enabled || false;
            }).catch(e => console.error('Failed to load startup status:', e));

            startupCheckbox.addEventListener('change', async () => {
                try {
                    const response = await fetch('/api/set-startup', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ enabled: startupCheckbox.checked })
                    });
                    const result = await response.json();
                    if (!result.success) {
                        alert('Failed to update startup setting: ' + (result.error || 'Unknown error'));
                        startupCheckbox.checked = !startupCheckbox.checked;
                    }
                } catch (err) {
                    console.error('Failed to set startup:', err);
                    alert('Failed to update startup setting.');
                    startupCheckbox.checked = !startupCheckbox.checked;
                }
            });
        }

        // Desktop shortcut buttons
        const createShortcutBtn = document.getElementById('create-desktop-shortcut-btn');
        const removeShortcutBtn = document.getElementById('remove-desktop-shortcut-btn');
        
        if (createShortcutBtn) {
            createShortcutBtn.addEventListener('click', async () => {
                try {
                    const response = await fetch('/api/create-desktop-shortcut', { method: 'POST' });
                    const result = await response.json();
                    if (result.success) {
                        alert('Desktop shortcut created successfully!');
                    } else {
                        alert('Failed to create shortcut: ' + (result.error || 'Unknown error'));
                    }
                } catch (err) {
                    console.error('Failed to create shortcut:', err);
                    alert('Failed to create desktop shortcut.');
                }
            });
        }

        // Desktop shortcut checkbox
        const desktopShortcutCheckbox = document.getElementById('desktop-shortcut-checkbox');
        if (desktopShortcutCheckbox) {
            // Load current shortcut state
            fetch('/api/desktop-shortcut-status').then(r => r.json()).then(data => {
                desktopShortcutCheckbox.checked = data.exists || false;
            }).catch(e => console.error('Failed to load shortcut status:', e));

            desktopShortcutCheckbox.addEventListener('change', async () => {
                try {
                    if (desktopShortcutCheckbox.checked) {
                        const response = await fetch('/api/create-desktop-shortcut', { method: 'POST' });
                        const result = await response.json();
                        if (!result.success) {
                            alert('Failed to create shortcut: ' + (result.error || 'Unknown error'));
                            desktopShortcutCheckbox.checked = false;
                        }
                    } else {
                        const response = await fetch('/api/remove-desktop-shortcut', { method: 'POST' });
                        const result = await response.json();
                        if (!result.success) {
                            alert('Failed to remove shortcut: ' + (result.error || 'Unknown error'));
                            desktopShortcutCheckbox.checked = true;
                        }
                    }
                } catch (err) {
                    console.error('Failed to toggle shortcut:', err);
                    alert('Failed to update desktop shortcut.');
                    desktopShortcutCheckbox.checked = !desktopShortcutCheckbox.checked;
                }
            });
        }

        if (removeShortcutBtn) {
            removeShortcutBtn.addEventListener('click', async () => {
                try {
                    const response = await fetch('/api/remove-desktop-shortcut', { method: 'POST' });
                    const result = await response.json();
                    if (result.success) {
                        alert('Desktop shortcut removed successfully!');
                        // Update checkbox if it exists
                        if (desktopShortcutCheckbox) {
                            desktopShortcutCheckbox.checked = false;
                        }
                    } else {
                        alert('Failed to remove shortcut: ' + (result.error || 'Unknown error'));
                    }
                } catch (err) {
                    console.error('Failed to remove shortcut:', err);
                    alert('Failed to remove desktop shortcut.');
                }
            });
        }

        // Open logs folder button
        const openLogsFolderBtn = document.getElementById('open-logs-folder-btn');
        if (openLogsFolderBtn) {
            openLogsFolderBtn.addEventListener('click', async () => {
                try {
                    await fetch('/api/open-logs-folder', { method: 'POST' });
                } catch (err) {
                    console.error('Failed to open logs folder:', err);
                }
            });
        }

        // Open Python dashboard button
        const openPythonDashboardBtn = document.getElementById('open-python-dashboard-btn');
        if (openPythonDashboardBtn) {
            openPythonDashboardBtn.addEventListener('click', async () => {
                try {
                    const response = await fetch('/api/open-python-dashboard', { method: 'POST' });
                    const result = await response.json();
                    if (!result.success) {
                        alert('Failed to open Python dashboard: ' + (result.error || 'Unknown error'));
                    }
                } catch (err) {
                    console.error('Failed to open Python dashboard:', err);
                    alert('Failed to open Python dashboard.');
                }
            });
        }

        // Open Web UI Guide button
        const openWebuiGuideBtn = document.getElementById('open-webui-guide-btn');
        if (openWebuiGuideBtn) {
            openWebuiGuideBtn.addEventListener('click', async () => {
                try {
                    const response = await fetch('/api/open-webui-guide');
                    const result = await response.json();
                    if (!result.success) {
                        alert('Failed to open Web UI guide: ' + (result.error || 'Unknown error'));
                    }
                } catch (err) {
                    console.error('Failed to open Web UI guide:', err);
                    alert('Failed to open Web UI guide.');
                }
            });
        }

        // Open Add Voices Guide button
        const openAddVoicesGuideBtn = document.getElementById('open-add-voices-guide-btn');
        if (openAddVoicesGuideBtn) {
            openAddVoicesGuideBtn.addEventListener('click', async () => {
                try {
                    const response = await fetch('/api/open-add-voices-guide');
                    const result = await response.json();
                    if (!result.success) {
                        alert('Failed to open Add Voices guide: ' + (result.error || 'Unknown error'));
                    }
                } catch (err) {
                    console.error('Failed to open Add Voices guide:', err);
                    alert('Failed to open Add Voices guide.');
                }
            });
        }

        // System Health Diagnostic
        const runDiagnosticBtn = document.getElementById('run-diagnostic-btn');
        const diagnosticOutput = document.getElementById('diagnostic-output');
        const healthStatus = document.getElementById('health-status');
        
        if (runDiagnosticBtn) {
            runDiagnosticBtn.addEventListener('click', async () => {
                runDiagnosticBtn.disabled = true;
                runDiagnosticBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Running...';
                diagnosticOutput.style.display = 'block';
                diagnosticOutput.innerHTML = 'Running diagnostic checks...';
                
                try {
                    const response = await fetch('/api/run-diagnostic');
                    const result = await response.json();
                    
                    let output = '';
                    result.checks.forEach(check => {
                        const icon = check.passed ? '✓' : '✗';
                        const color = check.passed ? 'var(--success)' : 'var(--danger)';
                        output += `<div style="color:${color}; margin-bottom:0.5rem;">${icon} ${check.name}: ${check.message}</div>`;
                    });
                    
                    diagnosticOutput.innerHTML = output;
                    
                    // Update health status
                    const allPassed = result.checks.every(c => c.passed);
                    if (allPassed) {
                        healthStatus.innerHTML = '<span class="dot" style="width:10px; height:10px;"></span><span>All Healthy</span>';
                        healthStatus.style.color = 'var(--success)';
                    } else {
                        healthStatus.innerHTML = '<span class="dot" style="width:10px; height:10px; background-color:var(--danger); box-shadow:0 0 10px var(--danger);"></span><span>Issues Detected</span>';
                        healthStatus.style.color = 'var(--danger)';
                    }
                } catch (err) {
                    console.error('Failed to run diagnostic:', err);
                    diagnosticOutput.innerHTML = '<div style="color:var(--danger);">Failed to run diagnostic test.</div>';
                } finally {
                    runDiagnosticBtn.disabled = false;
                    runDiagnosticBtn.innerHTML = '<i class="fas fa-stethoscope"></i> Run Diagnostic Test';
                }
            });
        }
    }

    /**
     * Synchronizes the UI with the server's voice inventory.
     * Triggers a filesystem reload on the backend to pick up newly exported voices.
     */
    let lastVoiceInventory = [];
    let lastActiveVoice = null;
    async function fetchVoices() {
        try {
            // First, trigger a reload to ensure we see new files
            await fetch('/api/reload-voices', { method: 'POST' });
            
            const response = await fetch('/health');
            const data = await response.json();
            
            if (data.available_voices) {
                const currentVal = voiceSelect.value;
                voiceSelect.innerHTML = '';
                
                // Sort voices numerically by name for predictable grouping (e.g. female_01, female_02)
                data.available_voices.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }));

                // Update dropdowns with nicknames if available
                data.available_voices.forEach(voice => {
                    const option = document.createElement('option');
                    option.value = voice.name;
                    option.textContent = voice.nickname ? `${voice.nickname} (${voice.name})` : voice.name;
                    voiceSelect.appendChild(option);
                });
                if (currentVal) voiceSelect.value = currentVal;

                // Strip paths from model name for simple display
                const activeModelName = data.model ? data.model.split(/[\\\/]/).pop() : 'Unknown';
                
                // If it's the first load (no current selection), set it to the active model
                if (!currentVal && activeModelName !== 'Unknown') {
                    voiceSelect.value = activeModelName;
                }
                
                // Find active voice object to get its nickname
                const activeVoiceObj = data.available_voices.find(v => v.name === activeModelName);
                const activeDisplayName = activeVoiceObj && activeVoiceObj.nickname ? activeVoiceObj.nickname : activeModelName;

                if (ui.currentVoiceHeader) ui.currentVoiceHeader.textContent = activeDisplayName;
                if (ui.voiceCountBadge) ui.voiceCountBadge.textContent = `${data.available_voices.length} Loaded`;
                
                // Update global dashboard stats via cache
                if (ui.voicesCountStat) ui.voicesCountStat.textContent = `${data.available_voices.length} Loaded`;
                if (ui.voicesActiveStat) ui.voicesActiveStat.textContent = activeDisplayName;

                // Sync the settings voice selector
                const settingsSelect = document.getElementById('settings-voice-select');
                if (settingsSelect) {
                    settingsSelect.innerHTML = voiceSelect.innerHTML;
                    settingsSelect.value = voiceSelect.value;
                }

                // Update the detailed voice inventory table
                const activeVoice = data.model ? data.model.split(/[\\\/]/).pop() : null;
                lastVoiceInventory = data.available_voices;
                lastActiveVoice = activeVoice;
                updateVoiceTable(data.available_voices, activeVoice);
            }
        } catch (error) {
            console.error('Error fetching voices:', error);
        }
    }

    /**
     * Renders the voice inventory table with management actions (Test, Folder, Load).
     * @param {Array} voices - List of voice objects from server.
     * @param {string} activeVoice - Currently loaded model filename.
     */
    function updateVoiceTable(voices, activeVoice) {
        const tbody = document.querySelector('#voice-table tbody');
        if (!tbody) return;
        
        // Sort voices numerically by name for predictable grouping (e.g. female_01, female_02)
        voices.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }));

        tbody.innerHTML = '';
        voices.forEach(voice => {
            const isActive = activeVoice && voice.name === activeVoice;
            const isDefault = voiceSelect && voiceSelect.value === voice.name;
            const tr = document.createElement('tr');
            if (isActive) tr.classList.add('active-row');
            
            tr.innerHTML = `
                <td>
                    <div class="nickname-container">
                        <i class="fas fa-tag text-dim" style="font-size: 0.8rem;"></i>
                        <input type="text" 
                               class="nickname-input" 
                               placeholder="Set nickname..." 
                               value="${voice.nickname || ''}" 
                               onchange="updateNickname('${voice.name}', this.value)"
                               onclick="event.stopPropagation()">
                    </div>
                </td>
                <td>
                    <div class="d-flex align-center gap-2">
                        <div class="voice-icon-placeholder ${isActive ? 'active' : ''}">
                            <i class="fas fa-file-audio"></i>
                        </div>
                        <div class="voice-name-group">
                             <span class="voice-fn text-sm">${voice.name}</span>
                             ${isActive ? '<span class="badge-mini">Active</span>' : ''}
                        </div>
                    </div>
                </td>
                <td><span class="text-mono text-dim text-sm">${(voice.size / 1024 / 1024).toFixed(1)} MB</span></td>
                <td><span class="badge badge-dim">ONNX</span></td>
                <td>
                    <div class="voice-actions">
                        <button class="btn btn-sm btn-test" onclick="testSubpartVoice('${voice.name}', this)" title="Test this voice">
                             <i class="fas fa-play"></i>
                        </button>
                        <button class="btn btn-sm btn-ghost" onclick="openFolder('voices')" title="Open Folder">
                            <i class="fas fa-folder-open"></i>
                        </button>
                        <button class="btn btn-sm ${isDefault ? 'btn-primary' : 'btn-secondary'}" onclick="loadVoiceFromTable('${voice.name}', this); event.stopPropagation();" ${isDefault ? 'disabled' : ''} style="min-width: 90px;">
                            <i class="fas ${isDefault ? 'fa-check-circle' : 'fa-play'}"></i> ${isDefault ? 'Loaded' : 'Load'}
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    /**
     * Load button handler for the Voices table.
     * Sets the selected voice as the default voice (no tab navigation).
     * Also best-effort warms the model to reduce cold-start latency.
     */
    window.loadVoiceFromTable = async (voiceName, btn) => {
        if (!voiceName) return;
        if (!voiceSelect) return;
        if (voiceSelect.value === voiceName) return;

        // Update UI immediately (so the button flips to "Loaded")
        voiceSelect.value = voiceName;
        try { updateVoiceTable(lastVoiceInventory, lastActiveVoice); } catch (e) { /* ignore */ }

        // Trigger the existing change handler to persist config + refresh voices
        voiceSelect.dispatchEvent(new Event('change'));

        // Best-effort warmup; backend requires a text field, even though warmup ignores it.
        const originalBtnContent = btn ? btn.innerHTML : null;
        try {
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading';
            }
            await fetch('/api/warmup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: 'warmup', voice_model: voiceName })
            });
        } catch (e) {
            // Warmup is optional; default voice still updates via /api/config
            console.warn('Warmup failed:', e);
        } finally {
            // Always re-enable button and refresh table to show "Loaded" state
            if (btn && originalBtnContent) {
                btn.disabled = false;
                btn.innerHTML = originalBtnContent;
            }
            // Refresh the table to reflect the new default
            try { updateVoiceTable(lastVoiceInventory, lastActiveVoice); } catch (e) { /* ignore */ }
        }
    };

    /**
     * Primary Speech Synthesis Trigger
     * Sends current text to the backend and handles the audio response.
     */
    speakBtn.addEventListener('click', async () => {
        // Handle Random Logic
        const randomChk = document.getElementById('random-checkbox');
        let text = ttsInput.value.trim();
        
        if ((randomChk && randomChk.checked) || !text) {
             text = getRandomSentence();
             ttsInput.value = text;
        }

        speakBtn.disabled = true;
        const originalContent = speakBtn.innerHTML;
        speakBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        const startTime = performance.now();

        try {
            // Speed control is now handled by the client-side player (audioPlayer.playbackRate)
            // This provides higher quality audio and instant updates without regenerating.
            // We always request 1.0 (normal speed) from the server.
            const lengthScale = 1.0;

            const response = await fetch('/api/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: text,
                    voice_model: voiceSelect.value,
                    length_scale: lengthScale
                })
            });

            if (response.ok) {
                const endTime = performance.now();
                const duration = ((endTime - startTime) / 1000).toFixed(2);
                if(synthesisTimeLabel) synthesisTimeLabel.textContent = `${duration}s`;

                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                audioPlayer.src = url;
                
                // Apply current speed immediately
                audioPlayer.playbackRate = currentTtsSpeed;
                
                // Show player result box
                if (playerContainer.classList.contains('audio-result-wrapper')) {
                    playerContainer.style.display = 'flex';
                } else {
                    playerContainer.style.display = 'block';
                    playerContainer.style.height = 'auto'; // fix hidden
                    playerContainer.style.overflow = 'visible';
                }
                
                audioPlayer.play();

                // Generate a predictable filename for downloads based on content
                const dlBtn = document.getElementById('download-audio-btn');
                if (dlBtn) {
                    dlBtn.href = url;
                    const cleanText = text.substring(0, 20).replace(/[^a-z0-9]/gi, '_');
                    dlBtn.download = `piper_${cleanText}.wav`;
                    // Enable button
                    dlBtn.style.pointerEvents = 'auto';
                    dlBtn.style.opacity = '1';
                }
            } else {
                const err = await response.text();
                alert('Error: ' + err);
            }
        } catch (error) {
            console.error('TTS Error:', error);
            alert('Failed to connect to server');
        } finally {
            speakBtn.disabled = false;
            speakBtn.innerHTML = originalContent;
        }
    });

    /**
     * Fetches the global application configuration and populates the settings form.
     */
    async function fetchSettings() {
        try {
            const response = await fetch('/api/config');
            const data = await response.json();
            const form = document.getElementById('settings-form');
            
            // Map JSON keys to form input names
            for (const key in data) {
                const input = form.elements[key];
                if (input) {
                    if (input.type === 'checkbox') {
                        input.checked = data[key];
                    } else {
                        input.value = data[key];
                    }
                }
            }
        } catch (e) { console.error(e); }
    }

    /**
     * Serializes the settings form and pushes updates to the server.
     */
    document.getElementById('save-settings-btn').addEventListener('click', async () => {
        const form = document.getElementById('settings-form');
        const formData = new FormData(form);
        const config = {};
        
        formData.forEach((value, key) => {
            const input = form.elements[key];
            if (input.type === 'checkbox') {
                config[key] = input.checked;
            } else if (input.type === 'number') {
                config[key] = parseFloat(value);
            } else {
                config[key] = value;
            }
        });

        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            if (response.ok) {
                alert('Settings saved successfully!');
            } else {
                alert('Failed to save settings');
            }
        } catch (e) { alert('Error: ' + e); }
    });

    /**
     * Discovers all 'Voice Dojos' (training projects) and renders status cards.
     */
    async function fetchDojos() {
        try {
            const response = await fetch('/api/dojos');
            const data = await response.json();
            const container = document.getElementById('dojo-list');
            if (!container) return;

            // Sort projects by name numerically (e.g. MyVoice_1, MyVoice_10)
            data.dojos.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }));

            container.innerHTML = '';
            if (data.dojos.length === 0) {
                container.innerHTML = '<p class="placeholder-text">No voice projects found. Start by creating one.</p>';
                return;
            }

            data.dojos.forEach(dojo => {
                const card = document.createElement('div');
                card.className = 'dojo-card card';
                const sizeMB = (dojo.dataset_size / 1024 / 1024).toFixed(1);
                const totalSizeMB = dojo.total_size ? (dojo.total_size / 1024 / 1024).toFixed(1) : sizeMB;
                card.innerHTML = `
                    <button class="btn btn-ghost btn-sm" onclick="deleteDojoFromStudio('${dojo.name}')" title="Delete this voice project" style="position:absolute; top:0.5rem; right:0.5rem; opacity:0.5; padding:0.25rem 0.5rem; font-size:0.9rem;">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                    <div class="card-info">
                        <h3 style="color:var(--accent)">${dojo.name}</h3>
                        <p style="font-size:0.8rem; color:var(--text-muted)">Quality: ${dojo.quality}</p>
                        <p style="font-size:0.8rem; color:var(--text-muted)">Dataset: ${sizeMB} MB</p>
                        <p style="font-size:0.8rem; color:var(--text-muted)">Storage: ${totalSizeMB} MB</p>
                    </div>
                    <div class="card-actions" style="margin-top:1rem; display:flex; flex-direction:column; gap:0.5rem">
                        <button class="btn btn-sm btn-primary" onclick="openVoiceEditor('${dojo.name}', 'setup')" title="Verify settings and dataset readiness before starting training.">Launch Training</button>
                        <div style="display:flex; gap:0.5rem">
                            <button class="btn btn-sm btn-secondary" style="flex:1" onclick="openVoiceEditor('${dojo.name}', 'slicer')" title="Open the audio slicer tool to prepare your dataset.">Clip Audio</button>
                            <button class="btn btn-sm btn-secondary" style="flex:1" onclick="openVoiceEditor('${dojo.name}', 'transcribe')" title="Run the automated setup wizard for this voice.">Transcribe</button>
                        </div>
                        <div style="display:flex; gap:0.5rem">
                            <button class="btn btn-sm btn-secondary" style="flex:1" onclick="openFolder('dojo', '${dojo.name}')" title="Open the project folder on your computer.">
                                <i class="fas fa-folder-open"></i> Folder
                            </button>
                            <button class="btn btn-sm btn-secondary" style="flex:1" onclick="launchTool('slicer', '${dojo.name}')" title="Open the original Python Dataset Slicer tool.">
                                <i class="fas fa-external-link-alt"></i> Legacy Slicer
                            </button>
                        </div>
                    </div>
                `;
                container.appendChild(card);
            });
        } catch (e) { console.error(e); }
    }

    /**
     * Deletes a dojo from the Voice Studio view.
     * Uses the same backend delete API as the Data Management tab.
     */
    window.deleteDojoFromStudio = async (dojoName) => {
        const confirmMsg = `Are you sure you want to permanently delete "${dojoName}"?\n\nThis will remove all training data, checkpoints, and audio files. This action cannot be undone.`;
        if (!confirm(confirmMsg)) {
            return;
        }

        try {
            const response = await fetch(`/api/storage/delete?type=dojo&name=${encodeURIComponent(dojoName)}`, {
                method: 'DELETE'
            });
            const result = await response.json();
            
            if (result.status === 'success') {
                // Refresh the dojo list
                await fetchDojos();
            } else {
                alert('Error deleting dojo: ' + (result.message || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to delete dojo:', error);
            alert('Failed to delete dojo. Check console for details.');
        }
    };

    /**
     * Timestamp for filtering logs (set when "Clear View" is clicked).
     * Only logs after this timestamp will be displayed.
     */
    let logClearTimestamp = null;

    /**
     * Fetches and formats system logs for the 'Logs' tab.
     * Implements smart auto-scrolling and log level color coding.
     */
    async function fetchLogs() {
        try {
            const response = await fetch('/api/logs');
            const data = await response.json();
            const container = document.getElementById('log-output');
            if (!container || !data.logs) return;

            // Filter logs based on clear timestamp if set
            let logsToDisplay = data.logs;
            if (logClearTimestamp) {
                logsToDisplay = data.logs.filter(line => {
                    // Extract timestamp from log line (format: YYYY-MM-DD HH:MM:SS,mmm)
                    const timestampMatch = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})/);
                    if (timestampMatch) {
                        const logTime = timestampMatch[1];
                        return logTime > logClearTimestamp;
                    }
                    // Include lines without timestamps (e.g., stack traces)
                    return true;
                });
            }

            // If no logs pass the filter, show a message
            if (logsToDisplay.length === 0 && logClearTimestamp) {
                container.innerHTML = '<div class="log-line"><i class="fas fa-info-circle"></i> Waiting for new logs...</div>';
                return;
            }

            container.innerHTML = logsToDisplay.map(line => {
                let className = 'log-line';
                let content = line;

                // Detect log levels for visual grouping
                if (line.includes('[ERROR]') || line.startsWith('Traceback') || line.includes('Error:')) {
                    className += ' log-error';
                } else if (line.includes('[WARNING]')) {
                    className += ' log-warning';
                } else if (line.includes('[INFO]')) {
                    className += ' log-info';
                }

                // Identify stack trace lines for specialized styling
                if (line.trim().startsWith('File "') || line.trim().startsWith('self.') || line.includes('line ')) {
                    className += ' log-traceback';
                }

                // Enhanced line formatting with structured badges (Level, Message)
                const logRegex = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+\[(\w+)\]\s+(.*)$/;
                const match = line.match(logRegex);

                if (match) {
                    const [_, timestamp, level, message] = match;
                    const levelClass = level.toLowerCase();
                    content = `<span class="log-timestamp">${timestamp}</span><span class="log-badge log-badge-${levelClass}">${level}</span><span class="log-msg">${message}</span>`;
                }

                return `<div class="${className}">${content}</div>`;
            }).join('');
            
            /**
             * Smart scroll: Only auto-scroll if the user is already near the bottom.
             * This prevents snapping the scroll if the user is currently reading an error higher up.
             */
            const isAtBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 50;
            if (isAtBottom) {
                container.scrollTop = container.scrollHeight;
            }
        } catch (e) { console.error(e); }
    }

    /**
     * Live Log Polling
     * Refreshes the log stream every 3 seconds while the Logs tab is active.
     */
    setInterval(() => {
        const logsTab = document.querySelector('.nav-links li[data-tab="logs"]');
        if (logsTab && logsTab.classList.contains('active')) {
            fetchLogs();
        }
    }, 3000);

    // --- Voice Studio Editor & Wizard Logic ---

    /**
     * Central entry point for managing a specific voice project.
     * Transitions the main application UI into the 'Voice Studio' mode.
     * 
     * @param {string} voiceName - Name of the voice dojo folder (e.g., "Cori").
     * @param {string} [step='slicer'] - Initial wizard step to show.
     */
    window.openVoiceEditor = (voiceName, step = 'slicer') => {
        // Clear active states in navigation
        const navLinks = document.querySelectorAll('.nav-links li');
        const tabContents = document.querySelectorAll('.tab-content');
        const tabTitle = document.getElementById('tab-title');

        navLinks.forEach(l => l.classList.remove('active'));
        tabContents.forEach(c => c.style.display = 'none');
        
        // Show the editor and set high-level context
        document.getElementById('tab-training-editor').style.display = 'block';
        document.getElementById('editor-voice-name').textContent = voiceName;
        tabTitle.textContent = "Voice Studio Editor";

        // Route to the requested sub-step
        switchEditorStep(step);
    };

    /**
     * Navigates between the internal steps of the Voice Studio (Wizard).
     * Handles UI visibility and triggers data loading for each step.
     * 
     * @param {string} stepName - Target step identifier ('slicer', 'transcribe', 'setup', 'train').
     */
    window.switchEditorStep = (stepName) => {
        const stepContents = document.querySelectorAll('.editor-step-content');
        const stepIndicators = document.querySelectorAll('.wizard-steps-indicator .step');

        // Reset sub-UI state
        stepContents.forEach(c => c.style.display = 'none');
        stepIndicators.forEach(i => i.classList.remove('active'));

        const targetContent = document.getElementById(`step-${stepName}`);
        if (targetContent) targetContent.style.display = 'block';
        
        const targetIndicator = document.querySelector(`.wizard-steps-indicator .step[data-step="${stepName}"]`);
        if (targetIndicator) targetIndicator.classList.add('active');

        // Cleanup any active pollers from previous steps
        stopPreprocessPolling();
        if (trainingPollInterval) {
            clearInterval(trainingPollInterval);
            trainingPollInterval = null;
        }

        // Context-aware initialization: Only load data when the user enters the step
        if (stepName === 'slicer') loadSlicerData();
        if (stepName === 'transcribe') {
            loadTranscriptionData();
            // Auto-start transcription if metadata doesn't exist
            setTimeout(async () => {
                const voiceName = document.getElementById('editor-voice-name')?.textContent;
                if (!voiceName) return;
                try {
                    const check = await fetch(`/api/training/metadata?voice=${voiceName}`);
                    if (!check.ok || check.status === 404) {
                        // No metadata exists, auto-start transcription
                        console.log("No metadata found, auto-starting transcription...");
                        window.runTranscription();
                        return;
                    }
                    const data = await check.json();
                    if (!data.entries || data.entries.length === 0) {
                        // Metadata exists but is empty, auto-start transcription
                        console.log("Empty metadata, auto-starting transcription...");
                        window.runTranscription();
                    }
                } catch (e) {
                    console.error("Auto-transcribe check failed:", e);
                    // If there's an error checking metadata, try to start transcription anyway
                    console.log("Error checking metadata, attempting to start transcription...");
                    window.runTranscription();
                }
            }, 300);
        }
        if (stepName === 'setup') loadSetupData(true);
        if (stepName === 'train') loadTrainingData();
    };

    /**
     * Initializes the Waveform Slicer for the currently active voice.
     * Connects the global 'AdvancedSlicer' instance to the dojo dataset.
     */
    window.loadSlicerData = async () => {
        const voiceName = document.getElementById('editor-voice-name').textContent;
        if (window.slicer) {
            window.slicer.loadVoice(voiceName);
        }
    };

    /**
     * Fetches metadata.csv (transcriptions) and populates the Step 2 review table.
     * Implements numerical sorting to ensure IDs like 'wav_2' appear before 'wav_10'.
     */
    window.loadTranscriptionData = async () => {
        const voiceName = document.getElementById('editor-voice-name').textContent;
        const tableBody = document.querySelector('#metadata-table tbody');
        const placeholder = document.getElementById('metadata-placeholder');

        try {
            const response = await fetch(`/api/training/metadata?voice=${voiceName}`);
            const data = await response.json();

            // Handle empty datasets gracefully
            if (!data.entries || data.entries.length === 0) {
                tableBody.innerHTML = '';
                placeholder.style.display = 'block';
                return;
            }

            // Natural sorting for UX: 1, 2, 3... 10 instead of 1, 10, 11... 2
            data.entries.sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true, sensitivity: 'base' }));

            placeholder.style.display = 'none';
            tableBody.innerHTML = '';

            // Render table rows with integrated audio playback and inline editing hooks
            data.entries.forEach(entry => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${entry.id}</td>
                    <td>
                        <div class="metadata-edit-wrapper">
                            <input type="text" class="metadata-input" data-id="${entry.id}" value="${entry.text || ''}" 
                                   onchange="updateMetadataRow('${voiceName}', '${entry.id}', this.value)">
                        </div>
                    </td>
                    <td style="text-align: center;">
                        <button class="btn btn-sm btn-secondary" onclick="playClip('${voiceName}', '${entry.id}')">
                            <i class="fas fa-play"></i>
                        </button>
                    </td>
                `;
                tableBody.appendChild(tr);
            });
        } catch (error) {
            console.error('Failed to load metadata:', error);
        }
    };

    /**
     * Plays a specific audio clip from the voice project's dataset.
     * Handles file extension normalization and logs debug info for missing assets.
     * 
     * @param {string} voiceName - The voice project ID.
     * @param {string} filename - The base filename or ID of the clip.
     */
    window.playClip = async (voiceName, filename) => {
        try {
            const fname = filename.toLowerCase().endsWith('.wav') ? filename : `${filename}.wav`;
            const url = `/dojo_data/${voiceName}_dojo/dataset/wav/${fname}`;
            
            console.log(`[Playback] Attempting to play: ${url}`);
            
            const audio = new Audio(url);
            audio.onerror = (e) => {
                console.error(`[Playback] Audio Load Error for ${url}:`, e);
                // Note: If this fails, verify that the 'dojo_data' static route is correctly mounted in the backend.
            };

            await audio.play();
        } catch (e) {
            console.error("[Playback] Interaction required (click first) or IO Error:", e);
        }
    };

    /**
     * Tracking hook for transcription edits before they are batch-saved to disk.
     */
    window.updateMetadataRow = async (voice, filename, newText) => {
        console.log(`[Metadata] Buffering update for ${filename}: "${newText}"`);
    };

    /**
     * Cache for original settings to allow for "Reset" or "Modified" detection.
     */
    let originalDojoSettings = {};

    /**
     * Loads Step 3 (Setup Review) info, including dataset stats and GPU requirements.
     * Simplified version - cleaner state management, no flickering prevention hacks.
     * @param {boolean} isInitial - If true, may trigger auto-tasks like preprocessing.
     */
    window.loadSetupData = async (isInitial = false) => {
        const voiceName = document.getElementById('editor-voice-name').textContent;
        
        // Populate display fields
        document.getElementById('setup-review-voice-name').textContent = voiceName;
        const gSelect = document.getElementById('setup-gender-select');
        const qSelect = document.getElementById('setup-quality-select');
        const lInput = document.getElementById('setup-language-input');
        
        try {
            // Fetch all required data in parallel
            const [statusResponse, metadataResponse, statsResponse] = await Promise.all([
                fetch(`/api/training/status?voice=${voiceName}`),
                fetch(`/api/training/metadata?voice=${voiceName}`),
                fetch(`/api/training/dataset-stats?voice=${voiceName}`)
            ]);
            
            const data = await statusResponse.json();
            const metadata = await metadataResponse.json();
            const stats = await statsResponse.json();
            
            // Sync form values with backend configuration
            const gender = data.gender || 'Female';
            const quality = data.quality || 'Medium';
            const language = data.language || 'en-us';

            gSelect.value = gender;
            qSelect.value = quality;
            lInput.value = language;

            // Store for comparison
            originalDojoSettings = { gender, quality, language };
            checkSetupSettingsChanged();
            
            // ========== CHECKLIST 1: Dataset Linked ==========
            updateDatasetCheck(metadata);
            
            // ========== CHECKLIST 2: Session Data ==========
            updateSessionCheck(data);
            
            // ========== CHECKLIST 3: Preprocessing ==========
            updatePreprocessingCheck(voiceName, data, stats, isInitial);

        } catch (error) {
            console.error('Failed to load setup data:', error);
        }
    };

    /**
     * Updates the Dataset Linked checklist item
     */
    function updateDatasetCheck(metadata) {
        const checkDataset = document.getElementById('check-dataset');
        const count = metadata.entries ? metadata.entries.length : 0;
        
        if (count > 0) {
            checkDataset.querySelector('.check-status').innerHTML = '<i class="fas fa-check-circle text-success"></i>';
            checkDataset.querySelector('.check-desc').textContent = `${count} samples connected and ready.`;
        } else {
            checkDataset.querySelector('.check-status').innerHTML = '<i class="fas fa-exclamation-triangle text-warning"></i>';
            checkDataset.querySelector('.check-desc').textContent = 'No audio samples found in project.';
        }
    }

    /**
     * Updates the Session Data checklist item
     */
    function updateSessionCheck(data) {
        const checkSession = document.getElementById('check-checkpoints');
        
        if (data.is_training) {
            checkSession.querySelector('.check-status').innerHTML = '<i class="fas fa-sync fa-spin text-info"></i>';
            checkSession.querySelector('.check-desc').textContent = 'Training is active or resuming...';
        } else {
            checkSession.querySelector('.check-status').innerHTML = '<i class="fas fa-check-circle text-success"></i>';
            checkSession.querySelector('.check-desc').textContent = 'Project directory is clean/idle.';
        }
    }

    /**
     * Updates the Preprocessing checklist item with simplified state logic
     */
    function updatePreprocessingCheck(voiceName, trainingData, stats, isInitial) {
        const checkPre = document.getElementById('check-preprocessing');
        const btnLaunch = document.getElementById('btn-launch-training');
        const btnConfirm = document.getElementById('btn-confirm-setup');
        
        const isRunning = trainingData.is_running;
        const needsPrep = !stats.is_preprocessed || stats.is_stale;
        
        // Update running state tracking
        if (isRunning && !preprocessState.lastKnownRunning) {
            // Just started running - begin polling
            startPreprocessPolling();
        } else if (!isRunning && preprocessState.lastKnownRunning) {
            // Just finished running - stop polling
            stopPreprocessPolling();
        }
        preprocessState.lastKnownRunning = isRunning;
        
        // Determine UI state based on current status
        if (isRunning) {
            // Currently preprocessing - show progress
            showPreprocessingProgress(checkPre, stats);
            disableButtons(btnLaunch, btnConfirm);
            
        } else if (stats.is_preprocessed) {
            // Preprocessing complete and up to date
            showPreprocessingComplete(checkPre, stats);
            enableButtons(btnLaunch, btnConfirm);
            
        } else if (needsPrep) {
            // Needs preprocessing
            if (isInitial && !preprocessState.isManualStart) {
                // Auto-start on initial load
                console.log("Auto-starting preprocessing...");
                window.runManualPreprocess(true);
            } else {
                // Show button to manually trigger
                showPreprocessingNeeded(checkPre, stats);
                disableButtons(btnLaunch, btnConfirm);
            }
            
        } else {
            // No data to preprocess
            showNoPreprocessingData(checkPre);
            disableButtons(btnLaunch, btnConfirm);
        }
    }

    /**
     * Shows preprocessing in progress with live count
     */
    function showPreprocessingProgress(checkPre, stats) {
        const pct = stats.meta_count > 0 ? (stats.preprocessed_count / stats.meta_count * 100) : 0;
        
        checkPre.querySelector('.check-status').innerHTML = '<i class="fas fa-spinner fa-spin text-primary"></i>';
        checkPre.querySelector('.check-desc').innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
                <span style="font-size: 0.9em;">Preprocessing... (${stats.preprocessed_count}/${stats.meta_count})</span>
                <span style="font-weight: bold; color: var(--primary-color); font-size: 0.9em;">${pct.toFixed(0)}%</span>
            </div>
            <div style="height: 4px; background: rgba(0,0,0,0.1); border-radius: 2px; overflow: hidden; width: 100%;">
                <div style="width: ${pct}%; height: 100%; background: var(--primary-color); transition: width 0.3s ease;"></div>
            </div>
        `;
    }

    /**
     * Shows preprocessing completed successfully
     */
    function showPreprocessingComplete(checkPre, stats) {
        checkPre.querySelector('.check-status').innerHTML = '<i class="fas fa-check-circle text-success"></i>';
        checkPre.querySelector('.check-desc').textContent = `${stats.preprocessed_count} features extracted. Ready.`;
    }

    /**
     * Shows preprocessing is needed with action button
     */
    function showPreprocessingNeeded(checkPre, stats) {
        const isStale = stats.is_stale;
        const message = isStale 
            ? `Data changed (${stats.preprocessed_count}/${stats.meta_count}). Re-prep needed.`
            : 'No features extracted.';
        const buttonClass = isStale ? 'btn-outline-warning' : 'btn-primary';
        const buttonText = isStale ? '<i class="fas fa-hammer"></i> Update Preprocessing' : '<i class="fas fa-play"></i> Run Preprocessing';
        
        checkPre.querySelector('.check-status').innerHTML = isStale 
            ? '<i class="fas fa-sync text-warning"></i>' 
            : '<i class="fas fa-times-circle text-danger"></i>';
        checkPre.querySelector('.check-desc').innerHTML = `
            <div class="d-flex align-items-center justify-content-between">
                <span>${message}</span>
                <button class="btn btn-sm ${buttonClass} ms-2" onclick="runManualPreprocess()">
                    ${buttonText}
                </button>
            </div>`;
    }

    /**
     * Shows no preprocessing data available
     */
    function showNoPreprocessingData(checkPre) {
        checkPre.querySelector('.check-status').innerHTML = '<i class="fas fa-times-circle text-danger"></i>';
        checkPre.querySelector('.check-desc').textContent = 'No audio data available.';
    }

    /**
     * Helper to disable training buttons
     */
    function disableButtons(...buttons) {
        buttons.forEach(btn => {
            if (btn) btn.disabled = true;
        });
    }

    /**
     * Helper to enable training buttons
     */
    function enableButtons(...buttons) {
        buttons.forEach(btn => {
            if (btn) btn.disabled = false;
        });
    }

    /**
     * Start polling for preprocessing progress
     */
    function startPreprocessPolling() {
        if (!preprocessState.pollInterval) {
            preprocessState.pollInterval = setInterval(() => {
                loadSetupData(false);
            }, 2000);
            console.log("Started preprocessing polling");
        }
    }

    /**
     * Stop polling for preprocessing progress
     */
    function stopPreprocessPolling() {
        if (preprocessState.pollInterval) {
            clearInterval(preprocessState.pollInterval);
            preprocessState.pollInterval = null;
            console.log("Stopped preprocessing polling");
        }
    }

    /**
     * Manually trigger preprocessing
     * Simplified version - just start it and let polling handle the rest
     */
    window.runManualPreprocess = async (stayOnPage = true) => {
        if (preprocessState.isManualStart) {
            console.log("Preprocessing already starting, ignoring duplicate request");
            return;
        }
        
        preprocessState.isManualStart = true;
        const voiceName = document.getElementById('editor-voice-name').textContent;
        const checkPre = document.getElementById('check-preprocessing');
        
        // Show immediate feedback
        if (checkPre) {
            checkPre.querySelector('.check-status').innerHTML = '<i class="fas fa-spinner fa-spin text-primary"></i>';
            checkPre.querySelector('.check-desc').textContent = 'Starting preprocessing...';
        }

        try {
            const response = await fetch(`/api/training/preprocess?voice=${voiceName}`, { method: 'POST' });
            
            if (response.ok) {
                // Success - start polling
                prepareTerminalForTask('Starting Piper preprocessing pipeline...');
                startPreprocessPolling();
                
                if (!stayOnPage) {
                    // Switch to training page to show logs
                    switchEditorStep('train');
                    loadTrainingData();
                }
                
            } else {
                // Error - show message
                const data = await response.json();
                if (!data.error?.includes("already active")) {
                    alert(`Error: ${data.error || 'Failed to start preprocessing'}`);
                }
            }
            
        } catch (error) {
            console.error('Preprocessing request failed:', error);
            alert('Network error while starting preprocessing');
        } finally {
            // Clear manual start flag and refresh
            setTimeout(() => {
                preprocessState.isManualStart = false;
                loadSetupData(false);
            }, 1000);
        }
    };

    window.loadTrainingData = async () => {
        const voiceName = document.getElementById('editor-voice-name').textContent;
        updateTrainingStatus(voiceName);

        if (trainingPollInterval) clearInterval(trainingPollInterval);
        trainingPollInterval = setInterval(() => updateTrainingStatus(voiceName), 5000);
    };

    // --- Console/Log Utilities ---
    const ansiToHtml = (text) => {
        // First escape HTML characters to prevent breaking the UI (e.g. <Enter>)
        let escaped = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");

        // Basic ANSI to HTML conversion (colors and bold)
        let result = escaped
            .replace(/\x1b\[1;31m/g, '<span style="color: #ef4444; font-weight: bold;">') // Red
            .replace(/\x1b\[1;32m/g, '<span style="color: #22c55e; font-weight: bold;">') // Green
            .replace(/\x1b\[1;33m/g, '<span style="color: #f59e0b; font-weight: bold;">') // Yellow
            .replace(/\x1b\[1;36m/g, '<span style="color: #06b6d4; font-weight: bold;">') // Cyan
            .replace(/\x1b\[1;37m/g, '<span style="color: #ffffff; font-weight: bold;">') // White
            .replace(/\x1b\[0;32m/g, '<span style="color: #22c55e;">') // Green (normal)
            .replace(/\x1b\[0;33m/g, '<span style="color: #f59e0b;">') // Yellow (normal)
            .replace(/\x1b\[0;36m/g, '<span style="color: #06b6d4;">') // Cyan (normal)
            .replace(/\x1b\[31m/g, '<span style="color: #ef4444;">')
            .replace(/\x1b\[32m/g, '<span style="color: #22c55e;">')
            .replace(/\x1b\[33m/g, '<span style="color: #f59e0b;">')
            .replace(/\x1b\[34m/g, '<span style="color: #3b82f6;">')
            .replace(/\x1b\[35m/g, '<span style="color: #a855f7;">')
            .replace(/\x1b\[36m/g, '<span style="color: #06b6d4;">')
            .replace(/\x1b\[0m|\x1b\[m/g, '</span>')
            .replace(/\x1b\[H\x1b\[2J\x1b\[3J/g, '') // Clear screen codes
            .replace(/\x1b\[[0-9;]*[mK]/g, ''); // Strip remaining unknown ANSI sequences
        return result;
    };

    window.logToTerminal = (id, message, className = "text-info") => {
        const el = document.getElementById(id);
        if (!el) return;
        
        const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
        
        const line = document.createElement("div");
        line.className = "log-line " + className;
        
        // Use HTML to render ANSI colors
        line.innerHTML = `<span class="prompt">></span> ${ansiToHtml(message)}`;
        el.appendChild(line);
        
        if (isNearBottom) {
            el.scrollTop = el.scrollHeight;
        }
    };

    // Strategy selector
    document.querySelectorAll('.strategy-card').forEach(card => {
        card.addEventListener('click', () => {
            document.querySelectorAll('.strategy-card').forEach(c => c.classList.remove('active'));
            card.classList.add('active');
            console.log("Selected strategy:", card.getAttribute('data-mode'));
        });
    });

    // Terminal Input Handling
    const terminalForm = document.getElementById('terminal-form');
    const terminalInput = document.getElementById('terminal-input-field');
    const terminalEnterBtn = document.getElementById('terminal-enter-key-btn');

    if (terminalForm) {
        const sendInput = async (text) => {
            const voiceName = document.getElementById('editor-voice-name').textContent;
            if (!voiceName) return;

            // Log the command locally immediately
            window.logToTerminal('training-terminal', text === '' ? '<Enter>' : text, 'text-success');
            
            try {
                const response = await fetch('/api/training/input', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ voice: voiceName, text: text })
                });
                const result = await response.json();
                if (!result.ok) {
                    window.logToTerminal('training-terminal', `Error: ${result.error}`, 'text-error');
                }
            } catch (err) {
                console.error('Failed to send terminal input:', err);
            }
        };

        terminalForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = (terminalInput.value ?? '').replace(/\r/g, '');
            terminalInput.value = '';
            await sendInput(text);
        });

        if (terminalEnterBtn) {
            terminalEnterBtn.addEventListener('click', async () => {
                await sendInput('');
            });
        }
    }

    const showTrainingErrorBanner = (err) => {
        const banner = document.getElementById('train-error-banner');
        const title = document.getElementById('train-error-title');
        const msg = document.getElementById('train-error-message');
        const fix = document.getElementById('train-error-fix');
        if (!banner || !title || !msg || !fix) return;

        if (!err) {
            banner.style.display = 'none';
            title.textContent = '';
            msg.textContent = '';
            fix.textContent = '';
            return;
        }

        banner.style.display = 'flex';
        title.textContent = err.title || 'Training error';
        msg.textContent = err.message || '';
        fix.textContent = err.fix || '';
    };

    /**
     * Resets terminal and task progress state before a new operation (training or preprocessing)
     */
    const prepareTerminalForTask = (initialMessage = 'Initializing task...') => {
        // [MODIFIED] Setup tab log
        const setupTerm = document.getElementById('setup-terminal');
        const setupLog = document.getElementById('setup-auto-log-container');
        if (setupTerm && setupLog && setupLog.style.display !== 'none') {
             setupTerm.innerHTML = `<div class="log-line text-info">> ${initialMessage}</div>`;
        }
        
        const terminal = document.getElementById('training-terminal');
        const progressBox = document.getElementById('training-task-progress-box');
        const taskName = document.getElementById('training-current-task-name');
        const taskDetail = document.getElementById('training-current-task-detail');
        const taskIcon = document.getElementById('training-current-task-icon');

        if (terminal) {
            terminal.innerHTML = `<div class="log-line text-info">> ${initialMessage}</div>`;
        }

        if (progressBox && taskName && taskDetail) {
            progressBox.style.display = 'flex';
            taskName.textContent = 'Preparing...';
            taskDetail.textContent = 'Waiting for process to start';
            if (taskIcon) taskIcon.className = 'spinner-border spinner-border-sm text-primary';
        }

        // Reset tracking vars
        lastSeenLogLine = '';
    };

    // --- Audio Slicer & Transcribe Triggers ---

    window.runAutoSplit = async () => {
        const voiceName = document.getElementById('editor-voice-name').textContent;
        const btn = document.getElementById('btn-run-slicer');
        const logsContainer = document.getElementById('slicer-logs-container');
        
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Slicing...';
        if (logsContainer) logsContainer.style.display = 'block';
        
        const terminalId = "slicer-terminal";
        const terminal = document.getElementById(terminalId);
        if (terminal) terminal.innerHTML = ''; // Clear old logs

        logToTerminal(terminalId, "Initializing Auto-Splitter...", "text-info");
        logToTerminal(terminalId, `Process ID: ${Math.floor(Math.random()*10000)}`, "text-dim");

        try {
            const response = await fetch('/api/training/run-slicer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ voice: voiceName })
            });
            const data = await response.json();
            if (data.status === 'ok') {
                logToTerminal(terminalId, `Success: Generated ${data.count || '?'} clips.`, "text-success");
                logToTerminal(terminalId, "Dataset updated. Proceed to Step 2.", "text-success");
                await loadSlicerData();
            } else {
                logToTerminal(terminalId, "Error: " + (data.detail || 'Unknown error'), "text-error");
                alert('Slicing failed: ' + data.detail);
            }
        } catch (e) {
            logToTerminal(terminalId, "Connection Failed: " + e.message, "text-error");
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-scissors"></i> Run Auto-Splitter';
        }
    };

    window.runTranscription = async () => {
        const voiceName = document.getElementById('editor-voice-name').textContent;
        const btn = document.getElementById('btn-run-whisper');
        const placeholderBtn = document.getElementById('btn-start-transcribe-placeholder');
        const nextBtn = document.getElementById('btn-to-setup');
        const logsContainer = document.getElementById('transcribe-logs-container');
        const statusBanner = document.getElementById('transcribe-status');
        const progressBar = document.getElementById('transcribe-progress-bar');
        const progressPercent = document.getElementById('transcribe-percent');
        const currentFileText = document.getElementById('transcribe-current-file');
        const terminalId = "transcribe-terminal";
        const terminal = document.getElementById(terminalId);

        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> AI Thinking...';
        }
        if (placeholderBtn) {
            placeholderBtn.disabled = true;
            placeholderBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> AI Working...';
        }
        if (nextBtn) {
            nextBtn.disabled = true;
        }
        
        if (statusBanner) statusBanner.style.display = 'flex';
        // Note: logsContainer visibility is now handled by the user toggle, 
        // but we'll still clear the terminal for fresh output.
        if (terminal) terminal.innerHTML = '';

        logToTerminal(terminalId, "Powering up AI Transcription Engine (Whisper)...", "text-info");
        logToTerminal(terminalId, "Checking CUDA compatibility...", "text-dim");

        // Set up polling for progress
        let pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`/api/training/transcribe/progress?voice=${voiceName}`);
                const progress = await res.json();
                
                if (progress.active) {
                    const percent = Math.round((progress.current / progress.total) * 100);
                    if (progressBar) progressBar.style.width = `${percent}%`;
                    if (progressPercent) progressPercent.textContent = `${percent}%`;
                    if (currentFileText) currentFileText.textContent = `${progress.status} (${progress.current}/${progress.total})`;
                }
            } catch (e) {
                console.error("Polling error:", e);
            }
        }, 1000);

        try {
            const response = await fetch(`/api/training/transcribe?voice=${voiceName}`, {
                method: 'POST'
            });
            let data = null;
            const contentType = (response.headers.get('content-type') || '').toLowerCase();
            try {
                if (contentType.includes('application/json')) {
                    data = await response.json();
                } else {
                    const text = await response.text();
                    data = { ok: response.ok, error: text };
                }
            } catch (parseErr) {
                const text = await response.text().catch(() => '');
                data = { ok: response.ok, error: text || String(parseErr) };
            }
            
            clearInterval(pollInterval);

            if (data.ok || data.status === 'ok') {
                if (progressBar) progressBar.style.width = '100%';
                if (progressPercent) progressPercent.textContent = '100%';
                logToTerminal(terminalId, "AI Task complete. Generating metadata.csv...", "text-success");
                await window.loadTranscriptionData();
            } else {
                logToTerminal(terminalId, "Failed to start: " + (data.error || data.detail || response.statusText || "Unknown"), "text-error");
            }
        } catch (e) {
            clearInterval(pollInterval);
            logToTerminal(terminalId, "AI Engine Error: " + (e?.message || String(e)), "text-error");
        } finally {
            if (statusBanner) {
                setTimeout(() => {
                    statusBanner.style.display = 'none';
                }, 2000);
            }
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-robot"></i> Run AI Transcription (Whisper)';
            }
            if (placeholderBtn) {
                placeholderBtn.disabled = false;
                placeholderBtn.innerHTML = '<i class="fas fa-magic"></i> Start AI Transcription';
            }
            if (nextBtn) {
                nextBtn.disabled = false;
            }
        }
    };

    const parseClipIdFromTranscribeStatus = () => {
        const el = document.getElementById('transcribe-current-file');
        const t = (el && el.textContent) ? String(el.textContent) : '';
        if (!t) return null;

        // Prefer extracting something that looks like "123.wav" or "abc_01.wav"
        const matches = Array.from(t.matchAll(/([A-Za-z0-9_\-]+)\.wav/gi));
        if (matches.length > 0) return matches[matches.length - 1][1];

        // Fallback: "Transcribing 123" (no extension)
        const m2 = t.match(/Transcribing\s+([A-Za-z0-9_\-]+)/i);
        if (m2 && m2[1]) return m2[1];
        return null;
    };

    const ignoreOrDeleteCurrentClip = async (deleteFiles) => {
        const voiceName = document.getElementById('editor-voice-name').textContent;
        const clipId = parseClipIdFromTranscribeStatus();
        if (!clipId) {
            alert('Could not detect the current clip ID. Open the console and ensure a clip is actively being transcribed.');
            return;
        }

        const action = deleteFiles ? 'delete' : 'ignore';
        if (!confirm(`Are you sure you want to ${action} clip "${clipId}"?`)) return;

        try {
            const resp = await fetch('/api/training/ignore-wavs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ voice: voiceName, ids: [clipId], delete_files: !!deleteFiles })
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok || !data.ok) {
                const msg = (data && (data.error || data.detail)) ? (data.error || data.detail) : resp.statusText;
                alert(`Failed to ${action} clip: ${msg}`);
                return;
            }

            const terminalId = 'transcribe-terminal';
            logToTerminal(terminalId, `[OK] ${deleteFiles ? 'Deleted' : 'Ignored'} clip ${clipId}`, 'text-success');
            if (deleteFiles) {
                logToTerminal(terminalId, 'Tip: re-run Whisper to continue with remaining clips.', 'text-dim');
            } else {
                logToTerminal(terminalId, 'Tip: click Go to Cockpit again; preflight will skip ignored clips.', 'text-dim');
            }

            // Refresh UI tables so the clip disappears if deleted and metadata stays in sync
            await window.loadTranscriptionData();
            await loadTrainingData();
        } catch (e) {
            console.error(e);
            alert(`Network error while trying to ${action} the clip.`);
        }
    };

    document.getElementById('btn-ignore-current-clip')?.addEventListener('click', async () => {
        await ignoreOrDeleteCurrentClip(false);
    });
    document.getElementById('btn-delete-current-clip')?.addEventListener('click', async () => {
        await ignoreOrDeleteCurrentClip(true);
    });

    window.uploadMasterAudio = async (fileOverride = null) => {
        const voiceName = document.getElementById('editor-voice-name').textContent;
        const fileInput = document.getElementById('master-audio-upload');
        const file = fileOverride || (fileInput && fileInput.files && fileInput.files[0]);
        if (!file) return;

        // IMPORTANT: Clear the input so selecting the same file again will still fire a change event.
        // This also avoids the need for a hard refresh when reusing the same master audio across voices.
        if (fileInput) fileInput.value = '';

        // Warning for master audio change
        if (window.slicer && (window.slicer.segments.length > 0 || window.slicer.pins.length > 0)) {
            const confirmed = confirm("WARNING: Uploading a new master audio will clear your current unsaved segment list.\n\nHave you already EXPORTED your current clips? If not, click Cancel and use the 'Export All' button first.");
            if (!confirmed) return;
            
            // Clear slicer segments to prevent desync with new audio
            window.slicer.segments = [];
            window.slicer.pins = [];
            window.slicer.selectedSegmentIds.clear();
            window.slicer._syncRegions();
            window.slicer.renderSegments();
            window.slicer._saveState();
        }

        const statusBanner = document.getElementById('slicer-status');
        const statusText = document.getElementById('slicer-status-text');

        if (statusBanner) statusBanner.style.display = 'flex';
        if (statusText) statusText.textContent = `Uploading and Slicing ${file.name}...`;

        const formData = new FormData();
        formData.append('file', file);
        formData.append('voice', voiceName);

        try {
            const response = await fetch(`/api/training/upload-audio?voice=${voiceName}`, {
                method: 'POST',
                body: formData
            });

            if (response.ok) {
                // Reload slicer to reflect new master
                if (window.slicer) await window.slicer.loadVoice(voiceName);
                if (statusText) statusText.textContent = 'Upload and processing complete!';
                setTimeout(() => { if (statusBanner) statusBanner.style.display = 'none'; }, 3000);
            } else {
                const msg = await response.text();
                alert('Upload failed: ' + msg);
                if (statusBanner) statusBanner.style.display = 'none';
            }
        } catch (e) { 
            console.error(e);
            alert('Upload failed. Check server logs.');
            if (statusBanner) statusBanner.style.display = 'none';
        }
    };

    // --- Training Cockpit ---
    let trainingPollInterval = null;

    window.selectTesterModel = (name, path) => {
        const testerCard = document.getElementById('voice-tester-card');
        const testerModelName = document.getElementById('tester-model-name');
        const speakBtn = document.getElementById('btn-tester-speak');
        if (testerCard && testerModelName) {
            testerModelName.textContent = name;
            testerModelName.dataset.path = path;
            
            // Enable the speak button now that a checkpoint exists
            if (speakBtn) {
                speakBtn.disabled = false;
                speakBtn.title = 'Test this checkpoint';
            }
            
            // Highlight in list
            document.querySelectorAll('.ckpt-history-item').forEach(el => {
                el.classList.toggle('active', el.textContent.includes(name) || el.onclick.toString().includes(name));
            });
        }
    };

    // --- Loss Graphs Logic ---
    const LOSS_HISTORY_LIMIT = 1200; // ~1 hour history at 3s polling
    const lossHistory = {
        mel: [],
        gen: [],
        disc: []
    };
    
    // Interactive Graph State
    const activeHover = {
        mel: null,
        gen: null,
        disc: null
    };

    /**
     * Renders a specialized loss graph using the HTML5 Canvas API.
     * Features auto-scaling, trend shading, and time-context labels.
     * 
     * @param {string} canvasId - The ID of the canvas element.
     * @param {number[]} data - Array of loss values.
     * @param {string} colorHex - The color for the line.
     * @param {number|null} [hoverIdx=null] - Index to highlight (for tooltips).
     */
    const drawLossGraph = (canvasId, data, colorHex, hoverIdx = null) => {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width;
        canvas.height = rect.height;
        
        const ctx = canvas.getContext('2d');
        const w = canvas.width;
        // Reserve bottom space for timeline labels
        const bottomMargin = 20;
        const graphH = canvas.height - bottomMargin;
        
        if (data.length < 2) {
             ctx.fillStyle = 'rgba(255,255,255,0.3)';
             ctx.font = '12px sans-serif';
             ctx.fillText('Waiting for telemetry metrics...', 10, graphH/2);
             return;
        }

        /** @section Auto-Scaling */
        let min = Math.min(...data);
        let max = Math.max(...data);
        let range = max - min;
        if (range === 0) range = 1;
        
        // Vertical padding to prevent the line from touching the edges
        const paddingY = range * 0.15; 
        min -= paddingY;
        max += paddingY;
        const scaleY = graphH / (max - min);

        // Background Guide Lines
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, graphH * 0.25); ctx.lineTo(w, graphH * 0.25);
        ctx.moveTo(0, graphH * 0.75); ctx.lineTo(w, graphH * 0.75);
        ctx.stroke();

        /** @section Line Plotting */
        ctx.beginPath();
        ctx.strokeStyle = colorHex;
        ctx.lineWidth = 2;
        ctx.lineJoin = 'round';

        const stepX = w / (data.length - 1);

        data.forEach((val, i) => {
            const x = i * stepX;
            const y = graphH - ((val - min) * scaleY);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();

        /** @section Area Fill */
        ctx.lineTo(w, graphH);
        ctx.lineTo(0, graphH);
        ctx.closePath();
        ctx.fillStyle = colorHex + '20'; // Subtle translucent fill
        ctx.fill();
        
        /** @section Time Markers */
        ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText('Now', w - 4, canvas.height - 6);
        
        ctx.textAlign = 'left';
        const totalTimeMin = Math.round((data.length * 5) / 60); // Assuming 5s poll interval
        if (totalTimeMin > 0) {
            ctx.fillText(`${totalTimeMin}m ago`, 4, canvas.height - 6);
        } else {
            ctx.fillText('Start', 4, canvas.height - 6);
        }

        /** @section Interactive Tooltips (Hover) */
        if (hoverIdx !== null && hoverIdx >= 0 && hoverIdx < data.length) {
            const val = data[hoverIdx];
            const x = hoverIdx * stepX;
            const y = graphH - ((val - min) * scaleY);
            
            // Vertical Guide Line
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, canvas.height);
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
            ctx.lineWidth = 1;
            ctx.setLineDash([2, 2]);
            ctx.stroke();
            ctx.setLineDash([]);
            
            // Data Point Dot
            ctx.beginPath();
            ctx.arc(x, y, 4, 0, 2 * Math.PI);
            ctx.fillStyle = '#fff';
            ctx.fill();
            
            // Tooltip Label Logic
            const secondsAgo = (data.length - 1 - hoverIdx) * 5;
            let timeLabel = 'Just now';
            if (secondsAgo > 60) timeLabel = `${Math.round(secondsAgo/60)}m ago`;
            else if (secondsAgo > 10) timeLabel = `${secondsAgo}s ago`;

            const valTxt = `Value: ${val.toFixed(4)}`;
            const timeTxt = timeLabel;
            
            ctx.font = 'bold 11px sans-serif';
            const valWidth = ctx.measureText(valTxt).width;
            ctx.font = '10px sans-serif';
            const timeWidth = ctx.measureText(timeTxt).width;
            
            const boxWidth = Math.max(valWidth, timeWidth) + 16;
            const boxHeight = 34;
            
            let tx = x + 10;
            let ty = y - 10;
            
            // Boundary detection
            if (tx + boxWidth > w) tx = x - boxWidth - 10;
            if (ty - boxHeight < 0) ty = y + 10;

            // Tooltip Background
            ctx.fillStyle = 'rgba(20, 20, 30, 0.9)';
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            if (ctx.roundRect) {
                ctx.roundRect(tx, ty, boxWidth, boxHeight, 4);
            } else {
                ctx.rect(tx, ty, boxWidth, boxHeight); // Fallback for older browsers
            }
            ctx.fill();
            ctx.stroke();
            
            // Tooltip Content
            ctx.fillStyle = '#fff';
            ctx.textAlign = 'left';
            ctx.font = 'bold 11px sans-serif';
            ctx.fillText(valTxt, tx + 8, ty + 14);
            
            ctx.fillStyle = '#ccc';
            ctx.font = '10px sans-serif';
            ctx.fillText(timeTxt, tx + 8, ty + 27);
        }
    };
    
    /**
     * Attaches mouse event listeners to a graph canvas to handle interactivity.
     */
    const initGraphInteraction = (key, canvasId, color) => {
        const canvas = document.getElementById(canvasId);
        if (!canvas || canvas.dataset.hasListener) return;
        
        canvas.dataset.hasListener = 'true';
        
        canvas.addEventListener('mousemove', (e) => {
            const data = lossHistory[key];
            if (!data || data.length < 2) return;
            
            const rect = canvas.getBoundingClientRect();
            const w = rect.width;
            const x = e.clientX - rect.left;
            
            // Calculate hover index based on mouse X position
            const ratio = Math.max(0, Math.min(1, x / w));
            const idx = Math.round(ratio * (data.length - 1));
            
            activeHover[key] = idx;
            drawLossGraph(canvasId, data, color, idx);
        });
        
        canvas.addEventListener('mouseleave', () => {
            activeHover[key] = null;
            if (lossHistory[key]) {
                drawLossGraph(canvasId, lossHistory[key], color, null);
            }
        });
    };

    let lastSeenLogLine = '';
    let lastSeenPipelineLine = '';
    let lastSeenPipelinePhase = '';
    let currentPollingVoice = '';

    /**
     * Periodic status poller for the training cockpit.
     * Synchronizes UI state with backend training progress, Docker metrics, 
     * and auto-pipeline progression.
     * 
     * @param {string} voiceName - The active voice project to monitor.
     */
    const updateTrainingStatus = async (voiceName) => {
        try {
            /** @section Context Switching */
            if (voiceName !== currentPollingVoice) {
                currentPollingVoice = voiceName;
                // Reset local state when switching projects
                lastSeenLogLine = '';
                lastSeenPipelineLine = '';
                lastSeenPipelinePhase = '';
                const terminal = document.getElementById('training-terminal');
                if (terminal) terminal.innerHTML = '<div class="log-line text-muted">Initialising connection...</div>';
            }

            const response = await fetch(`/api/training/status?voice=${voiceName}`);
            const data = await response.json();
            
            // DOM References
            const statusText = document.getElementById('train-status-text');
            const epochText = document.getElementById('train-epoch');
            const stepText = document.getElementById('train-step');
            const terminal = document.getElementById('training-terminal');
            const startBtn = document.getElementById('btn-launch-training');
            const stopBtn = document.getElementById('btn-stop-training');
            const saveBtn = document.getElementById('btn-manual-save-header');
            const statusBadge = document.getElementById('train-status-badge');

            // --- Update Settings Badges ---
            const settingGender = document.getElementById('train-setting-gender');
            const settingQuality = document.getElementById('train-setting-quality');
            if (settingGender) settingGender.textContent = data.gender || '-';
            if (settingQuality) settingQuality.textContent = data.quality || '-';

            /** @section Pipeline (Transcription -> Training) UI logic */
            const pipeline = data.auto_pipeline;
            let pipelineErrorBanner = null;
            if (pipeline && pipeline.phase && pipeline.phase !== 'done') {
                if (pipeline.phase === 'transcribing') {
                    statusText.textContent = 'Transcribing (Whisper)';
                    statusText.style.color = 'var(--info)';
                    if (statusBadge) statusBadge.className = 'badge badge-dim';
                    if (startBtn) startBtn.style.display = 'none';
                    if (stopBtn) stopBtn.style.display = 'none';
                    if (saveBtn) saveBtn.style.display = 'none';
                } else if (pipeline.phase === 'starting_training') {
                    statusText.textContent = 'Starting Training';
                    statusText.style.color = 'var(--info)';
                    if (statusBadge) statusBadge.className = 'badge badge-dim';
                    if (startBtn) startBtn.style.display = 'none';
                    if (stopBtn) stopBtn.style.display = 'none';
                    if (saveBtn) saveBtn.style.display = 'none';
                } else if (pipeline.phase === 'failed') {
                    statusText.textContent = 'Error';
                    statusText.style.color = 'var(--danger)';
                    if (pipeline.error || pipeline.message) {
                        pipelineErrorBanner = {
                            title: 'Pipeline Failed',
                            message: pipeline.error || pipeline.message || 'Unknown error during transcription pipeline',
                            fix: pipeline.details ? JSON.stringify(pipeline.details, null, 2) : 'Check the logs for more details.'
                        };
                    }
                }
            }
            
            /** @section Active Training Status */
            const isTrainingActive = Boolean(data.is_running || data.container_running);
            if (isTrainingActive) {
                statusText.textContent = 'Training Active';
                if (statusBadge) {
                    statusBadge.className = 'badge badge-success';
                }
                // Single-button transport: show Stop state on the main button.
                if (startBtn) {
                    startBtn.style.display = 'inline-flex';
                    startBtn.dataset.mode = 'stop';
                    startBtn.classList.remove('btn-success');
                    startBtn.classList.add('btn-danger');
                    startBtn.innerHTML = '<i class="fas fa-stop"></i> Stop Training';
                }
                if (stopBtn) stopBtn.style.display = 'none';
                if (saveBtn) saveBtn.style.display = 'inline-flex';
            } else {
                statusText.textContent = 'Idle';
                if (statusBadge) {
                    statusBadge.className = 'badge badge-dim';
                }
                if (startBtn) {
                    startBtn.style.display = 'inline-flex';
                    startBtn.dataset.mode = 'start';
                    startBtn.classList.remove('btn-danger');
                    startBtn.classList.add('btn-success');
                    startBtn.innerHTML = '<i class="fas fa-play"></i> Start Training';
                }
                if (stopBtn) stopBtn.style.display = 'none';
                if (saveBtn) saveBtn.style.display = 'none';
            }

            /** @section Failure & Safety Notifications */
            if (data.thermal_tripped) {
                statusText.textContent = 'Thermal Protection';
                statusText.style.color = 'var(--danger)';
                showTrainingErrorBanner({
                    title: 'GPU Overheating',
                    message: `Training was stopped because your GPU reached the safety limit of 85°C.`,
                    fix: 'Allow your computer to cool down and ensure fans are working before starting again.'
                });
            } else if (data.early_stopped) {
                statusText.textContent = 'Early Stopping';
                statusText.style.color = 'var(--success)';
                
                const banner = document.getElementById('train-error-banner');
                if (banner) {
                    banner.style.display = 'flex';
                    banner.className = 'status-banner success';
                    document.getElementById('train-error-title').textContent = 'Training Completed (Early Stopping)';
                    document.getElementById('train-error-message').textContent = 'The model has stopped improving over the last 30 minutes.';
                    document.getElementById('train-error-fix').textContent = 'This usually means the voice sounds as good as it\'s going to get. Time to test it!';
                    
                    const icon = banner.querySelector('i');
                    if (icon) icon.className = 'fas fa-check-circle';
                }
            } else if (pipelineErrorBanner) {
                statusText.textContent = 'Error';
                statusText.style.color = 'var(--danger)';
                showTrainingErrorBanner(pipelineErrorBanner);
            } else if (data.last_error) {
                statusText.textContent = 'Error';
                statusText.style.color = 'var(--danger)';
                showTrainingErrorBanner(data.last_error);
            } else {
                showTrainingErrorBanner(null);
            }
            
            // Update global metrics
            epochText.textContent = data.last_epoch !== null ? data.last_epoch : '-';
            stepText.textContent = data.last_step !== null ? data.last_step : '-';

            const sessionStartText = document.getElementById('train-session-start');
            if (sessionStartText && data.session_stats) {
                sessionStartText.textContent = data.session_stats.start_epoch !== null ? `Epoch ${data.session_stats.start_epoch}` : '-';
            }

            /** @section Checkpoint & History Management */
            const lastSavedText = document.getElementById('train-last-saved');
            const historyList = document.getElementById('ckpt-history-list');

            if (data.available_models && data.available_models.length > 0) {
                const latest = data.available_models[0];
                const match = latest.name.match(/_(\d+)-/);
                
                if (lastSavedText) {
                    lastSavedText.textContent = match ? `Epoch ${match[1]}` : 'Ready';
                }

                if (historyList) {
                    const bestCheckpoint = data.best_checkpoint;
                    historyList.innerHTML = data.available_models.map(m => {
                        const m_match = m.name.match(/_(\d+)-/);
                        const ep = m_match ? `Epoch ${m_match[1]}` : m.name;
                        const isCurrentTester = document.getElementById('tester-model-name').textContent === m.name;
                        const isBest = bestCheckpoint && m.name === bestCheckpoint.name;
                        
                        const safePath = m.path.replace(/\\/g, '/');
                        const melLossDisplay = m.mel_loss !== null && m.mel_loss !== undefined ? 
                            `<span class="text-xs" style="color: var(--text-dim); margin-left: auto; font-family: monospace;">${m.mel_loss.toFixed(4)}</span>` : '';
                        const bestBadge = isBest ? '<i class="fas fa-crown text-xs" style="color: #fbbf24; margin-left: 0.25rem;"></i>' : '';
                        
                        return `
                            <div class="ckpt-history-item ${isCurrentTester ? 'active' : ''}" 
                                 onclick="selectTesterModel('${m.name}', '${safePath}')">
                                <span style="display: flex; align-items: center; gap: 0.25rem;">${ep}${bestBadge}</span>
                                ${melLossDisplay}
                                <i class="fas fa-chevron-right text-xs"></i>
                            </div>
                        `;
                    }).join('');
                }
                
                // Update best checkpoint indicator
                const bestIndicator = document.getElementById('best-checkpoint-indicator');
                const bestInfo = document.getElementById('best-checkpoint-info');
                if (bestIndicator && bestInfo && data.best_checkpoint) {
                    const match = data.best_checkpoint.name.match(/_(\d+)-/);
                    const epochNum = match ? match[1] : '?';
                    bestInfo.textContent = `Epoch ${epochNum} (Mel Loss: ${data.best_checkpoint.mel_loss.toFixed(4)})`;
                    bestIndicator.style.display = 'block';
                } else if (bestIndicator) {
                    bestIndicator.style.display = 'none';
                }

                // Auto-sync tester with newest model if none is manually selected
                const testerModelName = document.getElementById('tester-model-name');
                const currentPath = testerModelName?.dataset.path?.replace(/\\/g, '/');
                const hasValidSelection = currentPath && data.available_models.find(am => {
                    const normalizedPath = am.path.replace(/\\/g, '/');
                    return normalizedPath === currentPath;
                });
                
                if (testerModelName && !hasValidSelection) {
                    window.selectTesterModel(latest.name, latest.path.replace(/\\/g, '/'));
                }
            } else {
                if (lastSavedText) lastSavedText.textContent = '-';
                if (historyList) historyList.innerHTML = '<div class="text-muted text-xs">Waiting for first save...</div>';
                const testerModelName = document.getElementById('tester-model-name');
                const speakBtn = document.getElementById('btn-tester-speak');
                if (testerModelName) testerModelName.textContent = '-';
                if (speakBtn) {
                    speakBtn.disabled = true;
                    speakBtn.title = 'Waiting for first checkpoint...';
                }
            }

            /** @section Hardware & Speed Telemetry */
            const qualityVal = document.getElementById('train-quality-val');
            if (qualityVal) qualityVal.textContent = data.quality || '-';

            const freeSpace = document.getElementById('train-free-space');
            if (freeSpace) freeSpace.textContent = `${data.free_space_gb || 0} GB`;

            const speedText = document.getElementById('train-speed');
            if (speedText && data.session_stats) {
                const avg = data.session_stats.avg_epoch_time;
                if (avg > 0) {
                    if (avg < 60) {
                        speedText.textContent = `${avg.toFixed(1)}s / epoch`;
                    } else {
                        speedText.textContent = `${(avg / 60).toFixed(1)}m / epoch`;
                    }
                } else {
                    speedText.textContent = 'Calculating...';
                }
            }

            const ckptCountText = document.getElementById('train-ckpt-count');
            if (ckptCountText && data.session_stats) {
                ckptCountText.textContent = data.session_stats.ckpts_seen || 0;
            }

            /** @section Setting Visualizers */
            const epochStepText = document.getElementById('settings-epoch-step');
            if (epochStepText && data.dojo_settings) {
                epochStepText.textContent = data.dojo_settings.PIPER_SAVE_CHECKPOINT_EVERY_N_EPOCHS || 5;
            }

            const limitCountText = document.getElementById('settings-limit-count');
            if (limitCountText && data.dojo_settings) {
                limitCountText.textContent = data.dojo_settings.LIMIT_SAVES_COUNT || 3;
            }

            const thermalLimitText = document.getElementById('settings-thermal-limit');
            if (thermalLimitText && data.dojo_settings) {
                thermalLimitText.textContent = data.dojo_settings.GPU_THERMAL_LIMIT_CELSIUS || 85;
            }

            const minDiskText = document.getElementById('settings-min-disk');
            if (minDiskText && data.dojo_settings) {
                minDiskText.textContent = data.dojo_settings.MIN_FREE_SPACE_GB || 2;
            }

            /** @section Live Graph Integration */
            if (data.is_running && data.metrics) {
                const { loss_mel, loss_gen, loss_disc } = data.metrics;

                const updateMetric = (key, val, textId, graphId, color) => {
                    const el = document.getElementById(textId);
                    if (val !== null) {
                        if (activeHover[key] === null && el) el.textContent = val.toFixed(4);
                        
                        if (lossHistory[key]) {
                            lossHistory[key].push(val);
                            if (lossHistory[key].length > LOSS_HISTORY_LIMIT) lossHistory[key].shift();
                            
                            initGraphInteraction(key, graphId, color);
                            drawLossGraph(graphId, lossHistory[key], color, activeHover[key]);
                        }
                    } else {
                        if (el) el.textContent = '-';
                    }
                };

                // Divide mel loss by c_mel constant (45) to show actual unscaled mel loss
                const unscaled_mel_loss = loss_mel !== null ? loss_mel / 45.0 : null;
                updateMetric('mel', unscaled_mel_loss, 'live-val-mel', 'graph-mel', '#38bdf8');
                updateMetric('disc', loss_disc, 'live-val-disc', 'graph-disc', '#36d399');
            }

            /** @section Terminal Log Management */
            if (data.logs && data.logs.length > 0) {
                if (terminal) {
                    const isNearBottom = terminal.scrollHeight - terminal.scrollTop - terminal.clientHeight < 100;
                    
                    let newLines = data.logs;
                    if (lastSeenLogLine) {
                        const idx = newLines.lastIndexOf(lastSeenLogLine);
                        if (idx !== -1) {
                            newLines = newLines.slice(idx + 1);
                        }
                    } else {
                        terminal.innerHTML = '';
                    }

                    if (newLines.length > 0) {
                        newLines.forEach(line => {
                            const div = document.createElement('div');
                            div.className = 'log-line';
                            div.innerHTML = ansiToHtml(line);
                            terminal.appendChild(div);

                            // Update the Task Progress Box based on log content
                            const progressBox = document.getElementById('training-task-progress-box');
                            const taskName = document.getElementById('training-current-task-name');
                            const taskDetail = document.getElementById('training-current-task-detail');
                            const taskIcon = document.getElementById('training-current-task-icon');
                            
                            if (progressBox && taskName && taskDetail) {
                                if (line.includes('Preprocessing still running') || line.includes('piper_train.preprocess')) {
                                    progressBox.style.display = 'flex';
                                    if (taskIcon) taskIcon.className = 'spinner-border spinner-border-sm text-primary';
                                    taskName.textContent = 'Preprocessing Dataset...';
                                    const match = line.match(/\(([^)]+)\)/);
                                    taskDetail.textContent = match ? `Elapsed: ${match[1]}` : 'Optimizing audio for training';
                                } else if (line.includes('Preprocess Only mode complete')) {
                                    // Special message for the manual button case
                                    taskName.textContent = 'Preprocessing Finished';
                                    taskDetail.textContent = 'You can now return to the Setup page to start training.';
                                    if (taskIcon) taskIcon.className = 'fas fa-check-circle text-success';
                                } else if (line.includes('Epoch') && line.includes('Step')) {
                                    // Hide box once training starts properly
                                    progressBox.style.display = 'none';
                                } else if (line.includes('Successfully preprocessed dataset')) {
                                    taskName.textContent = 'Preprocessing Complete';
                                    taskDetail.textContent = 'Starting training engine...';
                                }
                            }
                        });

                        // Prevent the terminal DOM from growing infinitely
                        const lines = terminal.querySelectorAll('.log-line');
                        if (lines.length > 1000) {
                            for (let i = 0; i < lines.length - 1000; i++) {
                                lines[i].remove();
                            }
                        }

                        lastSeenLogLine = data.logs[data.logs.length - 1];
                        
                        if (isNearBottom) {
                            terminal.scrollTop = terminal.scrollHeight;
                        }
                    }
                }
            }

            /** @section Auto-Pipeline Progress Injection */
            if (terminal) {
                const isNearBottom = terminal.scrollHeight - terminal.scrollTop - terminal.clientHeight < 100;

                const logLine = (line) => {
                    const onlyLoading = (terminal.querySelectorAll('.log-line').length === 1) && (terminal.textContent || '').includes('Initialising connection...');
                    if (onlyLoading) terminal.innerHTML = '';

                    const div = document.createElement('div');
                    div.className = 'log-line';
                    div.innerHTML = ansiToHtml(line);
                    terminal.appendChild(div);

                    const lines = terminal.querySelectorAll('.log-line');
                    if (lines.length > 1000) {
                        for (let i = 0; i < lines.length - 1000; i++) {
                            lines[i].remove();
                        }
                    }

                    if (isNearBottom) terminal.scrollTop = terminal.scrollHeight;
                };

                const phase = (pipeline && pipeline.phase) ? pipeline.phase : '';
                if (phase && phase !== lastSeenPipelinePhase) {
                    lastSeenPipelinePhase = phase;
                    if (phase === 'transcribing') {
                        logLine('[PIPELINE] Transcription started (filling missing metadata)');
                    } else if (phase === 'starting_training') {
                        logLine('[PIPELINE] Transcription complete; triggering training startup...');
                    } else if (phase === 'failed') {
                        logLine('[PIPELINE] System failure. See error banner for diagnostic.');
                    } else if (phase === 'done') {
                        logLine('[PIPELINE] Task queue finished.');
                    }
                }

                // Periodic progress updates for Step 2 during auto-runs
                const p = data.transcribe_progress;
                if (data.transcribe_active && p && typeof p === 'object') {
                    const curRaw = Number.isFinite(p.current) ? p.current : 0;
                    const total = Number.isFinite(p.total) ? p.total : 0;
                    const statusTextLabel = (p.status || '').toString();

                    const displayCur = (statusTextLabel.startsWith('Transcribing ') && total > 0) ? Math.min(total, curRaw + 1) : curRaw;
                    const pct = (total > 0) ? Math.min(100, Math.round((displayCur / total) * 100)) : 0;
                    const progressLine = `[PIPELINE] ${displayCur}/${total} (${pct}%) ${statusTextLabel}`.trim();

                    if (progressLine && progressLine !== lastSeenPipelineLine) {
                        lastSeenPipelineLine = progressLine;
                        logLine(progressLine);
                    }
                }
            }
        } catch (e) { console.error('Training status poller error:', e); }
    };

    // --- Training Actions (Buttons & Interaction) ---

    /**
     * Stop the active Docker training container.
     * Shared so the main transport button can toggle between Start/Stop.
     */
    const stopTraining = async (voiceName, btnEl) => {
        const deepCleanup = document.querySelector('input[name="deep_cleanup"]')?.checked || false;

        let confirmMsg = `Are you sure you want to stop training for "${voiceName}"?`;
        if (deepCleanup) {
            confirmMsg += "\n\nNote: Deep Cleanup is enabled. This will shut down WSL/Docker to free up all utilized RAM.";
            confirmMsg += "\n\n⚠️ WARNING: If you have any other Docker apps running, they will also be stopped.";
            confirmMsg += "\n\nYou can disable Deep Cleanup in the Settings tab.";
        } else {
            confirmMsg += "\n\n💡 Note: Deep Cleanup is off. Docker will remain running and continue using 1-4GB of RAM even after training stops.";
            confirmMsg += "\n\nTo free up that memory automatically, enable Deep Cleanup in the Settings tab.";
        }

        if (!confirm(confirmMsg)) return;

        const btn = btnEl || document.getElementById('btn-launch-training');
        const originalHtml = btn ? btn.innerHTML : '';
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Stopping...';
        }

        try {
            const resp = await fetch(`/api/training/stop?voice=${voiceName}&deep_cleanup=${deepCleanup}`, { method: 'POST' });
            if (resp.ok) {
                updateTrainingStatus(voiceName);
            } else {
                alert('Failed to stop training container.');
            }
        } catch (e) {
            console.error(e);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalHtml || '<i class="fas fa-stop"></i> Stop Training';
            }
        }
    };

    document.getElementById('btn-stop-training')?.addEventListener('click', async (event) => {
        const voiceName = document.getElementById('editor-voice-name').textContent;
        await stopTraining(voiceName, event.currentTarget);
    });

    /**
     * Triggers an immediate model checkpoint save and .onnx export on the server.
     */
    const handleManualSave = async () => {
        const voiceName = document.getElementById('editor-voice-name').textContent;
        const btnHeader = document.getElementById('btn-manual-save-header');
        
        const originalHtml = btnHeader ? btnHeader.innerHTML : '<i class="fas fa-save"></i> Save & Export Now';
        if (btnHeader) {
            btnHeader.disabled = true;
            btnHeader.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Snapshotting...';
        }

        try {
            const resp = await fetch(`/api/training/save-checkpoint?voice=${voiceName}`, { method: 'POST' });
            const data = await resp.json();
            if (data.ok) {
                alert(`Checkpoint requested! A new version will appear in your history within 10-30 seconds.`);
                updateTrainingStatus(voiceName);
            } else {
                alert('Snapshot failed: ' + (data.error || 'Unknown server error'));
            }
        } catch (e) { 
            console.error(e); 
            alert('Error communicating with training service.');
        } finally {
            if (btnHeader) {
                btnHeader.disabled = false;
                btnHeader.innerHTML = originalHtml;
            }
        }
    };

    document.getElementById('btn-manual-save-header')?.addEventListener('click', handleManualSave);
    document.getElementById('btn-manual-save')?.addEventListener('click', handleManualSave);

    /**
     * Invokes the TTS engine using a specific 'Dojo' checkpoint instead of a production voice.
     * Allows for rapid iteration and quality assessment during training.
     */
    document.getElementById('btn-tester-speak')?.addEventListener('click', async () => {
        const text = document.getElementById('tester-input').value.trim();
        const modelPath = document.getElementById('tester-model-name').dataset.path;
        if (!text || !modelPath) {
            alert("Please select a checkpoint from the history list first.");
            return;
        }

        const btn = document.getElementById('btn-tester-speak');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Synthesizing...';

        try {
            const response = await fetch('/api/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: text,
                    voice_model: modelPath // Direct path to the .onnx in the training folder
                })
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const audio = document.getElementById('tester-audio');
                const container = document.getElementById('tester-player-container');
                
                audio.src = url;
                container.style.display = 'block';
                audio.play();
            } else {
                const err = await response.text();
                alert('Synthesis Error: ' + err);
            }
        } catch (e) { console.error(e); }
        finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-comment"></i> Speak Checkpoint';
        }
    });

    /**
     * Promotes a training checkpoint to the global production 'Voices' folder.
     */
    document.getElementById('btn-export-to-production')?.addEventListener('click', async () => {
        const voiceName = document.getElementById('editor-voice-name').textContent;
        const onnxName = document.getElementById('tester-model-name').textContent;
        if (!confirm(`Promote "${onnxName}" to production? This will make the voice available for global TTS use.`)) return;

        const btn = document.getElementById('btn-export-to-production');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Promoting...';

        try {
            const resp = await fetch('/api/training/export-production', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ voice: voiceName, onnx_filename: onnxName })
            });
            const data = await resp.json();
            if (data.ok) {
                alert('Export Successful! The voice is now live in the global inventory.');
                fetchVoices(); // Refresh main inventory list
            } else {
                alert('Promotion failed: ' + (data.error || 'Check backend logs'));
            }
        } catch (e) { console.error(e); }
        finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-rocket"></i> Export to Production';
        }
    });

    const openTensorBoard = async () => {
        try {
            const voiceName = document.getElementById('editor-voice-name')?.textContent || '';
            await fetch(`/api/tools/launch?tool=tensorboard&dojo=${voiceName}`, { method: 'POST' });
            alert('TensorBoard is launching in a new tab. If it doesn\'t open, check if it\'s already running at http://localhost:6006');
            window.open('http://localhost:6006', '_blank');
        } catch (e) { console.error(e); }
    };

    document.getElementById('btn-view-tensorboard')?.addEventListener('click', openTensorBoard);
    document.getElementById('btn-view-tensorboard-cockpit')?.addEventListener('click', openTensorBoard);

    document.getElementById('settings-auto-save-toggle')?.addEventListener('change', async (e) => {
        const voiceName = document.getElementById('editor-voice-name').textContent;
        const autoSaveToggle = e.target;
        autoSaveToggle.dataset.userModified = "true";
        
        try {
            await fetch(`/api/training/update-settings?voice=${voiceName}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    ENABLE_AUTO_SAVE: autoSaveToggle.checked ? 1 : 0
                })
            });
            setTimeout(() => { delete autoSaveToggle.dataset.userModified; }, 2000);
        } catch (e) {
            console.error("Failed to update auto-save toggle:", e);
        }
    });

    // Settings Modal Logic
    const settingsModal = document.getElementById('settings-modal');
    const closeSettingsBtn = document.getElementById('close-settings-modal');
    const cancelSettingsBtn = document.getElementById('btn-cancel-settings');
    const saveSettingsBtn = document.getElementById('btn-save-settings');

    const closeSettings = () => {
        if (settingsModal) settingsModal.style.display = 'none';
    };

    if (closeSettingsBtn) closeSettingsBtn.onclick = closeSettings;
    if (cancelSettingsBtn) cancelSettingsBtn.onclick = closeSettings;
    
    // Close on outside click
    window.addEventListener('click', (e) => {
        if (e.target === settingsModal) closeSettings();
    });

    document.getElementById('btn-edit-dojo-settings')?.addEventListener('click', () => {
        const currentStep = document.getElementById('settings-epoch-step').textContent;
        const currentLimit = document.getElementById('settings-limit-count').textContent;
        const currentThermal = document.getElementById('settings-thermal-limit').textContent;
        const currentDisk = document.getElementById('settings-min-disk').textContent;
        
        const inputStep = document.getElementById('modal-input-step');
        const inputLimit = document.getElementById('modal-input-limit');
        const inputThermal = document.getElementById('modal-input-thermal');
        const inputDisk = document.getElementById('modal-input-disk');
        
        if (inputStep) inputStep.value = parseInt(currentStep) || 5;
        if (inputLimit) inputLimit.value = parseInt(currentLimit) || 3;
        if (inputThermal) inputThermal.value = parseInt(currentThermal) || 85;
        if (inputDisk) inputDisk.value = parseInt(currentDisk) || 2;
        
        if (settingsModal) settingsModal.style.display = 'block';
    });

    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener('click', async () => {
            const voiceName = document.getElementById('editor-voice-name').textContent;
            const inputStep = document.getElementById('modal-input-step');
            const inputLimit = document.getElementById('modal-input-limit');
            const inputThermal = document.getElementById('modal-input-thermal');
            const inputDisk = document.getElementById('modal-input-disk');
            
            const stepVal = parseInt(inputStep.value);
            const limitVal = parseInt(inputLimit.value);
            const thermalVal = parseInt(inputThermal.value);
            const diskVal = parseInt(inputDisk.value);

            if (isNaN(stepVal) || stepVal < 1 || isNaN(limitVal) || limitVal < 1 || isNaN(thermalVal) || thermalVal < 40 || isNaN(diskVal) || diskVal < 0) {
                alert("Please enter valid numbers.");
                return;
            }

            // GPU Warning if thermal limit was changed
            const currentThermalText = document.getElementById('settings-thermal-limit').textContent;
            const currentThermalVal = parseInt(currentThermalText);
            if (thermalVal !== currentThermalVal) {
                const warning = "WARNING: Graphics cards can break at higher temperatures, so only mess with this if you know what you are doing. We are not responsible for any damage caused.\n\nAre you sure you want to continue?";
                if (!confirm(warning)) {
                    // Revert the input value to previous safe value
                    inputThermal.value = currentThermalVal;
                    return;
                }
            }
            
            // Show loading state
            saveSettingsBtn.disabled = true;
            saveSettingsBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';

            try {
                const resp = await fetch(`/api/training/update-settings?voice=${voiceName}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        PIPER_SAVE_CHECKPOINT_EVERY_N_EPOCHS: stepVal,
                        LIMIT_SAVES_COUNT: limitVal,
                        GPU_THERMAL_LIMIT_CELSIUS: thermalVal,
                        MIN_FREE_SPACE_GB: diskVal
                    })
                });
                const data = await resp.json();
                if (data.ok) {
                    // Update UI immediately (polling will overwrite later)
                    document.getElementById('settings-epoch-step').textContent = stepVal;
                    document.getElementById('settings-limit-count').textContent = limitVal;
                    document.getElementById('settings-thermal-limit').textContent = thermalVal;
                    document.getElementById('settings-min-disk').textContent = diskVal;
                    closeSettings();
                } else {
                    alert('Error updating settings: ' + data.error);
                }
            } catch (e) {
                console.error(e);
                alert('Connection error while saving settings.');
            } finally {
                saveSettingsBtn.disabled = false;
                saveSettingsBtn.textContent = 'Save Changes';
            }
        });
    }


    // --- Log Actions ---
    const audioUploadInput = document.getElementById('master-audio-upload');
    if (audioUploadInput) {
        audioUploadInput.addEventListener('change', async (e) => {
            if (e.target.files.length > 0) {
                // Pass the File object explicitly; we also clear the input inside uploadMasterAudio.
                await window.uploadMasterAudio(e.target.files[0]);
            }
        });
    }

    document.getElementById('btn-to-transcribe')?.addEventListener('click', async () => {
        // If we're in the slicer and have segments, export them automatically before switching
        if (window.slicer && window.slicer.segments.length > 0) {
            const confirmed = confirm(`Export all ${window.slicer.segments.length} segments and proceed to transcription?`);
            if (!confirmed) return;
            
            try {
                await window.slicer.exportAll();
            } catch (e) {
                console.error("Export all failed:", e);
                // We still proceed to next step so user isn't stuck.
            }
        }
        
        switchEditorStep('transcribe');
    });

    const checkSetupSettingsChanged = async () => {
        const voiceName = document.getElementById('editor-voice-name').textContent;
        const gVal = document.getElementById('setup-gender-select').value;
        const qVal = document.getElementById('setup-quality-select').value;
        const lVal = document.getElementById('setup-language-input').value;
        const warning = document.getElementById('setup-change-warning');
        const resumeBtn = document.querySelector('.strategy-card[data-mode="resume"]');
        const pretrainedBtn = document.querySelector('.strategy-card[data-mode="pretrained"]');

        const changed = gVal !== originalDojoSettings.gender || 
                        qVal !== originalDojoSettings.quality || 
                        lVal !== originalDojoSettings.language;

        if (changed) {
            warning.style.display = 'flex';
            resumeBtn.classList.add('disabled');
            if (resumeBtn.classList.contains('active')) {
                resumeBtn.classList.remove('active');
                pretrainedBtn.classList.add('active');
            }
            
            // Auto-save the new settings to the backend project files IMMEDIATELY
            try {
                await fetch('/api/training/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        voice: voiceName,
                        settings: { gender: gVal, quality: qVal, language: lVal }
                    })
                });
            } catch (e) {
                console.error("Auto-save settings failed:", e);
            }
        } else {
            warning.style.display = 'none';
            resumeBtn.classList.remove('disabled');
        }
    };

    document.getElementById('setup-gender-select')?.addEventListener('change', checkSetupSettingsChanged);
    document.getElementById('setup-quality-select')?.addEventListener('change', checkSetupSettingsChanged);
    document.getElementById('setup-language-input')?.addEventListener('input', checkSetupSettingsChanged);

    window.saveMetadata = async (silent = false) => {
        const voiceName = document.getElementById('editor-voice-name').textContent;
        const inputs = document.querySelectorAll('.metadata-input');
        
        // If no inputs, nothing to save
        if (inputs.length === 0) return true;

        const entries = Array.from(inputs).map(input => ({
            id: input.getAttribute('data-id'),
            text: input.value
        }));

        try {
            const response = await fetch('/api/training/metadata', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ voice: voiceName, entries: entries })
            });

            if (response.ok) {
                if (!silent) alert('Metadata saved!');
                return true;
            } else {
                if (!silent) alert('Failed to save metadata.');
                return false;
            }
        } catch (error) {
            console.error('Save error:', error);
            return false;
        }
    };

    // --- Transcription Events ---
    document.getElementById('btn-run-whisper')?.addEventListener('click', async () => {
        await window.runTranscription();
    });

    document.getElementById('btn-to-setup')?.addEventListener('click', async () => {
        const btn = document.getElementById('btn-to-setup');
        const originalText = btn.innerHTML;
        
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving changes...';
        
        const success = await window.saveMetadata(true);
        
        if (success) {
            switchEditorStep('setup');
        } else {
            alert("Could not save your changes. Please check your connection.");
        }
        
        btn.disabled = false;
        btn.innerHTML = originalText;
    });

    const launchTraining = async (event) => {
        const btn = (event && event.currentTarget) ? event.currentTarget : document.getElementById('btn-launch-training');
        const voiceName = document.getElementById('editor-voice-name').textContent;
        const activeStrategy = document.querySelector('.strategy-card.active');
        const startMode = activeStrategy ? activeStrategy.getAttribute('data-mode') : 'resume';
        
        const originalText = btn.innerHTML;
        
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Initializing Trainer...';

        // 2. Notify backend to start training
        try {
            const response = await fetch('/api/training/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ voice: voiceName, start_mode: startMode })
            });
            
            if (response.ok) {
                let data = {};
                try {
                    data = await response.json();
                } catch (_) {
                    data = {};
                }

                // Prepare terminal and progress box
                const phase = (data && data.phase) ? String(data.phase) : '';
                const msg = (data && data.message) ? String(data.message) : '';

                if (phase === 'transcribing') {
                    const pre = (data && data.preflight) ? data.preflight : null;
                    let extra = '';
                    try {
                        const missingCount = pre && pre.details && Number.isFinite(pre.details.missing_count) ? pre.details.missing_count : null;
                        if (missingCount !== null) extra = ` (missing ${missingCount} transcript row(s))`;
                    } catch (_) {}

                    prepareTerminalForTask(`Auto-transcribing missing metadata${extra}...`);
                    // Send the user back to the step that explains transcription rather than the training cockpit.
                    // CHANGED: Moist Critical user requested to stay on Cockpit or Setup, not be forced back to Transcribe.
                    // The backend is running auto-transcription, so we can just show the terminal output.
                    // We will NOT switch steps here.
                    
                    // Show the specific Setup log container if we are on the Setup page
                    const setupLog = document.getElementById('setup-auto-log-container');
                    if (setupLog) setupLog.style.display = 'block';

                    // POLL FOR PROGRESS
                    if (window._autoRepairInterval) clearInterval(window._autoRepairInterval);
                    window._autoRepairInterval = setInterval(async () => {
                        try {
                            const res = await fetch(`/api/training/transcribe/progress?voice=${encodeURIComponent(voiceName)}`);
                            if (!res.ok) return;
                            const progress = await res.json();
                            
                            if (setupLog && progress.active) {
                                setupLog.innerHTML = `
                                    <div style="padding: 1rem; background: rgba(33, 150, 243, 0.1); border-radius: 6px; border: 1px solid rgba(33, 150, 243, 0.3);">
                                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                                            <strong style="color: #2196f3;"><i class="fas fa-magic fa-spin"></i> Auto-Repair in Progress</strong>
                                            <span class="badge badge-primary">${progress.current} / ${progress.total}</span>
                                        </div>
                                        <div style="font-family: monospace; font-size: 0.9em; color: var(--text-dim); margin-bottom: 0.5rem;">
                                            ${progress.status || 'Processing files...'}
                                        </div>
                                        <div class="progress-bar-bg" style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                                            <div class="progress-bar-fill" style="width: ${(progress.current / (progress.total || 1)) * 100}%; height: 100%; background: #2196f3; transition: width 0.3s ease;"></div>
                                        </div>
                                    </div>
                                `;
                            } else if (setupLog && !progress.active) {
                                // Check if we finished?
                                clearInterval(window._autoRepairInterval);
                                setupLog.innerHTML = `
                                    <div style="padding: 1rem; background: rgba(76, 175, 80, 0.1); border-radius: 6px; border: 1px solid rgba(76, 175, 80, 0.3);">
                                        <div style="display: flex; align-items: center; gap: 0.5rem; color: #4caf50;">
                                            <i class="fas fa-check-circle"></i> 
                                            <strong>Repair Complete. Starting training...</strong>
                                        </div>
                                    </div>
                                `;
                                
                                // Transition to training view shortly
                                setTimeout(async () => {
                                    const sRes = await fetch(`/api/training/status?voice=${encodeURIComponent(voiceName)}`);
                                    if (sRes.ok) {
                                        const sData = await sRes.json();
                                        if (sData.is_running || sData.container_running) {
                                            switchEditorStep('train');
                                            loadTrainingData();
                                        }
                                    }
                                }, 1500);
                            }
                        } catch (e) { console.error("Poll error", e); }
                    }, 500);

                    if (msg) {
                        setTimeout(() => {
                            try {
                                // Try writing to the Setup terminal first
                                const setupTerm = document.getElementById('setup-terminal');
                                if (setupTerm) {
                                     const div = document.createElement('div');
                                     div.className = 'log-line';
                                     div.textContent = `[INFO] ${msg}`;
                                     setupTerm.appendChild(div);
                                     setupTerm.scrollTop = setupTerm.scrollHeight;
                                }

                                // Also write to main terminal if available
                                const terminal = document.getElementById('training-terminal');
                                if (terminal) {
                                    const div = document.createElement('div');
                                    div.className = 'log-line';
                                    div.textContent = `[INFO] ${msg}`;
                                    terminal.appendChild(div);
                                }
                            } catch (_) {}
                        }, 50);
                    }
                } else {
                    prepareTerminalForTask('Initializing training session...');
                    // Switch to visible training cockpit
                    switchEditorStep('train');
                    loadTrainingData();
                }
            } else {
                let detail = 'Check Docker status';
                try {
                    const data = await response.json();
                    detail = data.error || data.detail || detail;
                } catch(_) {}
                alert(`Could not start training: ${detail}`);
            }
        } catch (e) {
            console.error(e);
            alert("Network error while starting training.");
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    };

    document.getElementById('btn-launch-training')?.addEventListener('click', async (event) => {
        const btn = event.currentTarget;
        const mode = (btn && btn.dataset) ? btn.dataset.mode : '';
        const voiceName = document.getElementById('editor-voice-name').textContent;
        if (mode === 'stop') {
            await stopTraining(voiceName, btn);
            return;
        }
        await launchTraining(event);
    });
    document.getElementById('btn-confirm-setup')?.addEventListener('click', launchTraining);

    // --- Log Actions ---
    const flashBtn = (btn, html, ms = 2000) => {
        if (!btn) return;
        const originalHtml = btn.innerHTML;
        const fixedWidth = btn.offsetWidth;
        btn.innerHTML = html;
        btn.style.width = fixedWidth + 'px';
        setTimeout(() => {
            btn.innerHTML = originalHtml;
            btn.style.width = '';
        }, ms);
    };

    const openCopyModal = (title, text) => {
        // Create a lightweight modal using existing modal styles
        const overlay = document.createElement('div');
        overlay.className = 'modal copy-modal';
        overlay.style.display = 'block';

        overlay.innerHTML = `
            <div class="modal-content copy-modal-content">
                <div class="modal-header">
                    <h3><i class="fas fa-copy"></i> ${title}</h3>
                    <span class="close-modal" aria-label="Close">&times;</span>
                </div>
                <div class="modal-body">
                    <p class="text-muted" style="margin-top: 0;">Clipboard copy was blocked by your browser. The logs are below—press Ctrl+C.</p>
                    <textarea class="copy-modal-textarea" spellcheck="false"></textarea>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary copy-modal-select-btn">Select All</button>
                    <button type="button" class="btn btn-primary copy-modal-close-btn">Close</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        const textarea = overlay.querySelector('.copy-modal-textarea');
        if (textarea) {
            textarea.value = text;
            textarea.focus();
            textarea.select();
        }

        const close = () => {
            overlay.remove();
        };
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) close();
        });
        overlay.querySelector('.close-modal')?.addEventListener('click', close);
        overlay.querySelector('.copy-modal-close-btn')?.addEventListener('click', close);
        overlay.querySelector('.copy-modal-select-btn')?.addEventListener('click', () => {
            textarea?.focus();
            textarea?.select();
        });
    };

    const copyTextToClipboard = async (text) => {
        // 1) Modern clipboard API (may be blocked on insecure origins)
        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            try {
                await navigator.clipboard.writeText(text);
                return true;
            } catch (e) {
                // Fall through to legacy method
            }
        }

        // 2) Legacy execCommand fallback
        try {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.setAttribute('readonly', '');
            textarea.style.position = 'fixed';
            textarea.style.left = '-9999px';
            textarea.style.top = '0';
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();

            const ok = !!(document.execCommand && document.execCommand('copy'));
            document.body.removeChild(textarea);
            return ok;
        } catch (e) {
            return false;
        }
    };

    const clearLogsBtn = document.getElementById('clear-logs-btn');
    const restoreLogsBtn = document.getElementById('restore-logs-btn');
    
    if (clearLogsBtn) {
        clearLogsBtn.addEventListener('click', () => {
            // Get current timestamp in log format
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            const hours = String(now.getHours()).padStart(2, '0');
            const minutes = String(now.getMinutes()).padStart(2, '0');
            const seconds = String(now.getSeconds()).padStart(2, '0');
            const millis = String(now.getMilliseconds()).padStart(3, '0');
            
            logClearTimestamp = `${year}-${month}-${day} ${hours}:${minutes}:${seconds},${millis}`;
            
            const container = document.getElementById('log-output');
            if (container) {
                container.innerHTML = '<div class="log-line"><i class="fas fa-broom"></i> Previous logs hidden. Showing new logs only...</div>';
            }
            
            // Show restore button and hide clear button
            if (restoreLogsBtn) restoreLogsBtn.style.display = 'inline-block';
            clearLogsBtn.style.display = 'none';
            
            // Immediately refresh to apply filter
            setTimeout(fetchLogs, 100);
        });
    }
    
    if (restoreLogsBtn) {
        restoreLogsBtn.addEventListener('click', () => {
            // Clear the filter timestamp
            logClearTimestamp = null;
            
            // Hide restore button and show clear button
            restoreLogsBtn.style.display = 'none';
            if (clearLogsBtn) clearLogsBtn.style.display = 'inline-block';
            
            // Immediately refresh to show all logs
            fetchLogs();
        });
    }

    const copyLogsBtn = document.getElementById('copy-logs-btn');
    if (copyLogsBtn) {
        copyLogsBtn.addEventListener('click', () => {
            const container = document.getElementById('log-output');
            if (!container) return;
            
            const text = Array.from(container.querySelectorAll('.log-line'))
                .map(line => line.innerText)
                .join('\n');

            if (!text.trim()) {
                flashBtn(copyLogsBtn, '<i class="fas fa-info-circle"></i> No logs');
                return;
            }

            copyTextToClipboard(text).then((ok) => {
                if (ok) {
                    flashBtn(copyLogsBtn, '<i class="fas fa-check"></i> Copied!');
                } else {
                    flashBtn(copyLogsBtn, '<i class="fas fa-exclamation-triangle"></i> Manual copy');
                    openCopyModal('System Logs', text);
                }
            }).catch(err => {
                console.error('Failed to copy logs:', err);
                flashBtn(copyLogsBtn, '<i class="fas fa-exclamation-triangle"></i> Manual copy');
                openCopyModal('System Logs', text);
            });
        });
    }

    const copyTrainingLogsBtn = document.getElementById('copy-training-logs-btn');
    if (copyTrainingLogsBtn) {
        copyTrainingLogsBtn.addEventListener('click', () => {
            const terminal = document.getElementById('training-terminal');
            if (!terminal) return;

            const lines = Array.from(terminal.querySelectorAll('.log-line'));
            const text = (lines.length > 0)
                ? lines.map(line => line.innerText).join('\n')
                : (terminal.innerText || terminal.textContent || '');

            if (!text.trim()) {
                flashBtn(copyTrainingLogsBtn, '<i class="fas fa-info-circle"></i> No logs');
                return;
            }

            copyTextToClipboard(text).then((ok) => {
                if (ok) {
                    flashBtn(copyTrainingLogsBtn, '<i class="fas fa-check"></i> Copied!');
                } else {
                    flashBtn(copyTrainingLogsBtn, '<i class="fas fa-exclamation-triangle"></i> Manual copy');
                    openCopyModal('Training Docker Output', text);
                }
            }).catch(err => {
                console.error('Failed to copy training logs:', err);
                flashBtn(copyTrainingLogsBtn, '<i class="fas fa-exclamation-triangle"></i> Manual copy');
                openCopyModal('Training Docker Output', text);
            });
        });
    }

    const clearTrainingLogsBtn = document.getElementById('clear-training-logs-btn');
    if (clearTrainingLogsBtn) {
        clearTrainingLogsBtn.addEventListener('click', () => {
            const terminal = document.getElementById('training-terminal');
            if (terminal) {
                terminal.innerHTML = '<div class="log-line text-muted">Logs cleared. New output will appear below.</div>';
                flashBtn(clearTrainingLogsBtn, '<i class="fas fa-check"></i> Cleared');
            }
        });
    }

    // --- New Dashboard Features ---

    // Restart logic
    const setupRestartBtn = (id) => {
        const btn = document.getElementById(id);
        if (btn) {
            btn.addEventListener('click', async () => {
                if (!confirm('Are you sure you want to restart the server? This will stop speech during the restart.')) return;
                try {
                    await fetch('/api/system/restart', { method: 'POST' });
                    alert('Restart command sent. The page will reload when the server is back.');
                    setTimeout(() => {
                        window.location.reload();
                    }, 5000);
                } catch (e) { alert('Restart failed: ' + e); }
            });
        }
    };
    setupRestartBtn('restart-server-btn');
    setupRestartBtn('full-restart-btn');

    // Download Models logic
    const setupDownloadBtn = (id) => {
        const btn = document.getElementById(id);
        if (btn) {
            btn.addEventListener('click', async () => {
                try {
                    const res = await fetch('/api/tools/download-models', { method: 'POST' });
                    if (res.ok) {
                        alert('Model download started in background. Check server logs for progress.');
                    }
                } catch (e) { alert('Download failed: ' + e); }
            });
        }
    };
    setupDownloadBtn('download-models-btn');
    setupDownloadBtn('download-models-btn-voices');
    setupDownloadBtn('download-models-btn-alt');

    // Download Piper logic
    const dlPiperBtn = document.getElementById('download-piper-btn');
    if (dlPiperBtn) {
        dlPiperBtn.addEventListener('click', async () => {
            try {
                await fetch('/api/tools/download-piper', { method: 'POST' });
                alert('Piper binary check/download started in background.');
            } catch (e) { alert('Failed: ' + e); }
        });
    }

    // Mini-log preview for Overview
    async function updateMiniLog() {
        try {
            const response = await fetch('/api/logs');
            const data = await response.json();
            if (ui.logPreview && data.logs) {
                // Show last 10 lines
                const lines = data.logs.slice(-10);
                ui.logPreview.innerHTML = lines.map(line => 
                    `<div class="log-line" title="${line.replace(/"/g, '&quot;')}">${line}</div>`
                ).join('');
                ui.logPreview.scrollTop = ui.logPreview.scrollHeight;
            }
        } catch (e) {}
    }

    // GPU Polling & Graph (2s interval for ~30s history)
    const gpuHistoryPoints = 15; // 30s / 2s
    let gpuHistory = new Array(gpuHistoryPoints).fill(0);

    const drawGpuGraph = () => {
        const canvas = document.getElementById('gpu-load-graph');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        
        // Handle HIDPI/Retina if reasonably possible, or just standard
        const w = canvas.width; 
        const h = canvas.height;

        ctx.clearRect(0, 0, w, h);

        // Draw line
        ctx.beginPath();
        ctx.strokeStyle = '#38bdf8'; // var(--accent)
        ctx.lineWidth = 2;
        
        const step = w / (gpuHistoryPoints - 1);
        
        gpuHistory.forEach((val, i) => {
            const x = i * step;
            // Invert Y (0 at bottom)
            const y = h - ((val / 100) * h);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();

        // Fill below
        ctx.lineTo(w, h);
        ctx.lineTo(0, h);
        ctx.closePath();
        ctx.fillStyle = 'rgba(56, 189, 248, 0.2)';
        ctx.fill();
    };

    setInterval(async () => {
        try {
            // Check if user is on training tab and document is visible
            if (ui.gpuContainer && ui.trainStep && ui.trainStep.style.display !== 'none' && document.visibilityState === 'visible') { 
                const gpuRes = await fetch('/api/gpu-stats');
                if (gpuRes.ok) {
                    const gpuData = await gpuRes.json();
                    
                    if (gpuData.available) {
                        ui.gpuContainer.style.display = 'flex';
                        
                        const load = gpuData.utilization_gpu;
                        if(ui.gpuUtilText) ui.gpuUtilText.innerText = load + '%';
                        if(ui.gpuUtilBar) ui.gpuUtilBar.style.width = load + '%';
                        
                        // Update History for Sparkline visualizations
                        gpuHistory.push(load);
                        if (gpuHistory.length > gpuHistoryPoints) gpuHistory.shift();
                        if (typeof drawGpuGraph === 'function') drawGpuGraph();

                        // VRAM usage reporting
                        const usedGb = (gpuData.memory_used_mb / 1024).toFixed(1);
                        const totalGb = (gpuData.memory_total_mb / 1024).toFixed(1);
                        if(ui.gpuVramText) ui.gpuVramText.innerText = `${usedGb} / ${totalGb} GB`;

                        // Thermal state monitoring
                        if(ui.gpuTempText) {
                            ui.gpuTempText.innerText = gpuData.temperature_c + '°C';
                            ui.gpuTempText.style.color = (gpuData.temperature_c > 85) ? 'var(--danger)' : '';
                        }
                    } else {
                        ui.gpuContainer.style.display = 'none';
                    }
                }
            }
        } catch (e) {
            /* Silent fail to prevent UX degradation on transient network drops */
        }
    }, 2000);

    /**
     * Periodic Connectivity & Health Polling.
     * Updates the global "Online/Offline" indicators and refreshes the dashboard log.
     */
    setInterval(async () => {
        try {
            const res = await fetch('/health');
            const data = await res.json();
            
            if (data.ok) {
                ui.statusDots.forEach(dot => {
                    dot.style.backgroundColor = 'var(--success)';
                    dot.style.boxShadow = '0 0 10px var(--success)';
                });
                ui.statusText.forEach(ind => {
                    const txt = ind.querySelector('.status-text');
                    if (txt) {
                        txt.textContent = ind.classList.contains('mini-status') ? 'Online' : 'Server Online';
                        txt.style.color = 'var(--success)';
                    }
                });
            } else {
                ui.statusDots.forEach(dot => {
                    dot.style.backgroundColor = 'var(--orange)';
                    dot.style.boxShadow = '0 0 10px var(--orange)';
                });
                ui.statusText.forEach(ind => {
                    const txt = ind.querySelector('.status-text');
                    if (txt) {
                        txt.textContent = ind.classList.contains('mini-status') ? 'Issues' : 'Server Issues';
                        txt.style.color = 'var(--orange)';
                    }
                });
            }
        } catch (e) {
            ui.statusDots.forEach(dot => {
                dot.style.backgroundColor = '#ef4444';
                dot.style.boxShadow = '0 0 10px #ef4444';
            });
            ui.statusText.forEach(ind => {
                const txt = ind.querySelector('.status-text');
                if (txt) {
                    txt.textContent = ind.classList.contains('mini-status') ? 'Offline' : 'Server Offline';
                    txt.style.color = '#ef4444';
                }
            });
        }

        // Keep the main dashboard log window current if visible
        if (ui.overviewTab && ui.overviewTab.classList.contains('active')) {
            if (typeof updateMiniLog === 'function') updateMiniLog();
        }

        // Training activity indicator for header shortcut
        if (ui.activeTrainingBtn) {
            try {
                const tRes = await fetch('/api/training/active');
                if (tRes.ok) {
                    const tData = await tRes.json();
                    const voices = Array.isArray(tData.voices) ? tData.voices : [];
                    const isActive = Boolean(tData.active) || voices.length > 0;
                    ui.activeTrainingBtn.style.display = isActive ? 'flex' : 'none';
                    if (isActive) {
                        const v = voices[0];
                        ui.activeTrainingBtn.title = v ? `Training is active: ${v}_dojo` : 'Training is active';
                    }
                } else {
                    ui.activeTrainingBtn.style.display = 'none';
                }
            } catch (e) {
                ui.activeTrainingBtn.style.display = 'none';
            }
        }
    }, 5000);

    /**
     * New Voice Project Wizard Logic.
     */
    const newVoiceBtn = document.getElementById('new-voice-btn');
    const newVoiceModal = document.getElementById('new-voice-modal');
    if (newVoiceBtn && newVoiceModal) {
        newVoiceBtn.addEventListener('click', () => {
            newVoiceModal.style.display = 'block';
        });

        const closeBtn = newVoiceModal.querySelector('.close-modal');
        const cancelBtn = newVoiceModal.querySelector('.close-modal-btn');
        const closeModal = () => {
            newVoiceModal.style.display = 'none';
        };

        if (closeBtn) closeBtn.addEventListener('click', closeModal);
        if (cancelBtn) cancelBtn.addEventListener('click', closeModal);

        window.addEventListener('click', (event) => {
            if (event.target == newVoiceModal) {
                closeModal();
            }
        });

        const newVoiceForm = document.getElementById('new-voice-form');
        if (newVoiceForm) {
            newVoiceForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const name = document.getElementById('voice-name').value;
                const quality = document.getElementById('voice-quality').value;
                const gender = document.getElementById('voice-gender').value;
                const scratch = document.getElementById('voice-scratch').checked;

                const submitBtn = document.getElementById('create-voice-confirm-btn');
                const originalText = submitBtn.textContent;
                submitBtn.disabled = true;
                submitBtn.textContent = 'Creating...';

                try {
                    const response = await fetch('/api/training/create', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name, quality, gender, scratch })
                    });

                    if (response.ok) {
                        closeModal();
                        await fetchDojos(); // Refresh training cards
                        newVoiceForm.reset();
                        
                        // Switch into training context immediately
                        if (window.openVoiceEditor) {
                            window.openVoiceEditor(name, 'slicer');
                        }
                    } else {
                        const err = await response.text();
                        alert('Error creating voice: ' + err);
                    }
                } catch (error) {
                    console.error('Create voice failure:', error);
                    alert('Failed to connect to server');
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                }
            });
        }
    }

    // Initialize Global State
    fetchVoices();
    if (typeof updateMiniLog === 'function') updateMiniLog();
});

/**
 * Updates or sets the human-friendly nickname for a specific voice.
 * @param {string} voiceName - The folder name/ID of the voice.
 * @param {string} nickname - The new display name.
 */
async function updateNickname(voiceName, nickname) {
    try {
        await fetch('/api/voice/nickname', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                voice_name: voiceName, 
                nickname: nickname 
            })
        });
        
        // Refresh voices to update labels and stats across all UI elements
        const response = await fetch('/health');
        const data = await response.json();
        if (data.available_voices) {
            const voiceSelect = document.getElementById('voice-select');
            const currentVal = voiceSelect.value;
            voiceSelect.innerHTML = '';

            // Sort voices numerically by name for predictable grouping (e.g. female_01, female_02)
            data.available_voices.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }));

            data.available_voices.forEach(voice => {
                const option = document.createElement('option');
                option.value = voice.name;
                option.textContent = voice.nickname ? `${voice.nickname} (${voice.name})` : voice.name;
                voiceSelect.appendChild(option);
            });
            if (currentVal) voiceSelect.value = currentVal;
            
            // Sync the header display name
            const activeModelName = data.model ? data.model.split(/[\\\/]/).pop() : 'Unknown';
            const activeVoiceObj = data.available_voices.find(v => v.name === activeModelName);
            const activeDisplayName = activeVoiceObj && activeVoiceObj.nickname ? activeVoiceObj.nickname : activeModelName;
            
            document.getElementById('current-voice-name').textContent = activeDisplayName;
            const voicesActiveStat = document.getElementById('voices-active-stat');
            if (voicesActiveStat) voicesActiveStat.textContent = activeDisplayName;
        }
    } catch (e) { console.error('Nickname sync failed:', e); }
}

/**
 * Executes a server-side automation tool (e.g. Slicer UI, Dashboard).
 * @param {string} tool - Tool identifier.
 * @param {string|null} dojo - Optional specific training context.
 */
async function launchTool(tool, dojo = null) {
    try {
        const url = `/api/tools/launch?tool=${tool}${dojo ? '&dojo=' + dojo : ''}`;
        await fetch(url, { method: 'POST' });
    } catch (e) { console.error('Tool execution failed:', e); }
}

/**
 * Requests the server to open a specific OS file explorer path.
 * @param {string} type - Folder classification (voices, uploads, etc).
 * @param {string|null} dojo - Training subfolder if applicable.
 */
async function openFolder(type, dojo = null) {
    try {
        const url = `/api/tools/open-folder?folder_type=${type}${dojo ? '&dojo=' + dojo : ''}`;
        await fetch(url, { method: 'POST' });
    } catch (e) { console.error('File explorer request failed:', e); }
}

/**
 * Storage Management Logic.
 * Responsible for scanning data usage, rendering the management table,
 * and handling recursive deletions of training and model artifacts.
 */
async function refreshStorage() {
    try {
        const response = await fetch('/api/storage/info');
        const data = await response.json();
        
        // Update Docker engine cleanup visibility
        const pruneBtn = document.getElementById('btn-prune-docker');
        if (pruneBtn && data.docker_image_size) {
            pruneBtn.innerHTML = `<i class="fas fa-broom"></i> Delete Training Engine (${data.docker_image_size})`;
        }

        // Update Global Usage Summaries
        const totalLabel = document.getElementById('storage-total');
        if (totalLabel) totalLabel.textContent = data.total_managed_size || '0.00 B';
        
        const dockerStatus = document.getElementById('storage-docker-status');
        if (dockerStatus) {
            if (data.docker_status === 'installed_cached') {
                dockerStatus.innerHTML = `<span style="color: var(--success)">Installed (${data.docker_image_size})</span> <span style="color: var(--text-muted); font-size: 0.85em;">• Docker offline</span>`;
            } else if (data.docker_status === 'not_running') {
                dockerStatus.innerHTML = '<span style="color: var(--warning)">Docker Desktop not running</span>';
            } else if (data.docker_status === 'installed' && data.docker_image_size) {
                dockerStatus.innerHTML = `<span style="color: var(--success)">Ready for training (${data.docker_image_size})</span>`;
            } else {
                dockerStatus.textContent = 'Not Installed';
            }
        }

        // Separate models into Core and Lang
        const langModels = data.models ? data.models.filter(m => m.name.endsWith('.conf') || m.name.includes('ESPEAK')) : [];
        const coreModels = data.models ? data.models.filter(m => !m.name.endsWith('.conf') && !m.name.includes('ESPEAK')) : [];

        // Populate Tables
        renderStorageTable('storage-dojo-list', data.dojos, 'dojo');
        renderStorageTable('storage-lang-list', langModels, 'model');
        renderStorageTable('storage-core-model-list', coreModels, 'model');
        renderStorageTable('storage-voice-list', data.default_voices, 'voice');
        renderStorageTable('storage-custom-voice-list', data.custom_voices, 'voice');

    } catch (error) {
        console.error('Failed to fetch storage info:', error);
    }
}

function renderStorageTable(elementId, items, type) {
    const tbody = document.getElementById(elementId);
    if (!tbody) return;

    let friendlyType = type;
    if (type === 'dojo') friendlyType = 'voice projects';
    if (type === 'model') {
        friendlyType = elementId.includes('lang') ? 'language configs' : 'base models';
    }
    if (type === 'voice') friendlyType = 'installed voices';

    if (!items || items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 2rem; color: var(--text-muted);">No ${friendlyType} found.</td></tr>`;
        return;
    }

    tbody.innerHTML = items.map(item => {
        const safeName = escapeHtml(item.name);
        const displayName = item.display_name ? escapeHtml(item.display_name) : safeName;
        const format = item.format ? escapeHtml(item.format) : 'FILE';
        
        let rows = `
            <tr class="main-row">
                <td>
                    <div class="storage-name-cell">
                        ${type === 'dojo' && item.subparts && item.subparts.length > 0 ? 
                            `<button class="expand-btn" onclick="toggleSubparts('${item.name}', this)"><i class="fas fa-chevron-right"></i></button>` : ''}
                        <i class="fas ${getIconForItem(item, type)}"></i>
                        <span class="storage-item-name" title="${safeName}">${displayName}</span>
                        <button class="btn btn-ghost btn-sm btn-inline-info" onclick="showDeleteInfo('${type}', '${item.name}')" title="Why keep or delete this item">
                            <i class="fas fa-info-circle"></i>
                        </button>
                    </div>
                </td>
                <td><span class="text-dim text-sm">${safeName}</span></td>
                <td><span class="badge badge-dim">${format}</span></td>
                <td><span class="text-mono text-dim text-sm">${item.size}</span></td>
                <td style="text-align: right;">
                    <div class="sub-row-actions">
                        ${type === 'voice' ? `
                            <button class="btn btn-sm btn-test" onclick="testSubpartVoice('${item.name}', this)" title="Test this voice">
                                <i class="fas fa-play"></i> Test
                            </button>
                        ` : ''}
                        <button class="btn btn-danger btn-sm" onclick="handleDelete('${type}', '${item.name}')" title="Permanently delete this ${type} from your disk.">
                            <i class="fas fa-trash-alt"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;

        if (type === 'dojo' && item.subparts) {
            // Sort subparts: Audio first, then Voices, then Latest ckpts, then Archived
            const order = { 'folder': 0, 'voice': 1, 'checkpoint': 2 };
            const sortedSubs = [...item.subparts].sort((a, b) => {
                if (a.name.includes('Archive') && !b.name.includes('Archive')) return 1;
                if (!a.name.includes('Archive') && b.name.includes('Archive')) return -1;
                return order[a.type] - order[b.type];
            });

            sortedSubs.forEach(sub => {
                const safeSubName = escapeHtml(sub.name);
                const icon = sub.type === 'checkpoint' ? 'fa-save' : (sub.type === 'voice' ? 'fa-microphone' : 'fa-folder');
                const isArchive = sub.name.includes('Archive');
                
                rows += `
                    <tr class="sub-row sub-${item.name}" style="display: none;">
                        <td>
                            <div class="sub-part-name${isArchive ? ' is-archive' : ''}">
                                <i class="fas fa-level-up-alt fa-rotate-90 text-dim"></i>
                                <i class="fas ${icon} text-xs"></i>
                                <span class="storage-subpart-name" title="${safeSubName}">${safeSubName}</span>
                                <button class="btn btn-ghost btn-sm btn-inline-info" onclick="showDeleteInfo('dojo_subpart', '${item.name}', '${sub.id}', '${sub.name}', '${sub.type}')" title="Why keep or delete this part">
                                    <i class="fas fa-info-circle"></i>
                                </button>
                            </div>
                        </td>
                        <td><span class="text-mono text-dim text-xs">${sub.size}</span></td>
                        <td style="text-align: right;">
                            <div class="sub-row-actions">
                                ${sub.type === 'voice' ? `
                                    <button class="btn-test" onclick="testSubpartVoice('${sub.full_path.replace(/\\/g, '/')}', this)">
                                        <i class="fas fa-play"></i> Test
                                    </button>
                                ` : ''}
                                <button class="btn btn-ghost btn-sm text-danger" onclick="handleDelete('dojo', '${item.name}', '${sub.id}')" title="Delete only ${sub.name}">
                                    <i class="fas fa-eraser"></i>
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            });
        }
        return rows;
    }).join('');
}

/**
 * Toggles visibility of sub-component rows in the storage table.
 * @param {string} name - Data name of the parent item.
 * @param {HTMLElement} btn - The toggle button element.
 */
window.toggleSubparts = (name, btn) => {
    const subRows = document.querySelectorAll(`.sub-${name}`);
    const isVisible = subRows[0] && subRows[0].style.display !== 'none';
    
    subRows.forEach(row => row.style.display = isVisible ? 'none' : 'table-row');
    btn.classList.toggle('active', !isVisible);
};

    /**
     * Executes a TTS test for a specific model file path (e.g. from Storage Manager).
     * @param {string} full_path - Platform-specific path to the .onnx file.
     * @param {HTMLElement|null} btnEl - Specific button to show loading spinner on.
     */
    window.testSubpartVoice = async (full_path, btnEl = null) => {
        const text = "This is a test of the Piper TTS voice.";
        const btn = btnEl || (typeof event !== 'undefined' ? event.currentTarget : null);
        if (!btn) {
            alert('Could not start test (missing button context).');
            return;
        }
        const originalContent = btn.innerHTML;
        
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        try {
            const response = await fetch('/api/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: text,
                    voice_model: full_path
                })
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const audio = new Audio(url);
                
                // PERFORMANCE: Fix memory leak by revoking the object URL after playback
                audio.onended = () => URL.revokeObjectURL(url);
                audio.onerror = () => URL.revokeObjectURL(url);
                
                audio.play();
            } else {
                alert('Synthesis failed for this voice.');
            }
        } catch (e) {
            console.error(e);
            alert('Error testing voice');
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalContent;
        }
    };

    /**
     * Basic HTML escaping for dynamic modal content.
     */
    const escapeHtml = (value) => {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    };

    /**
     * Helper to wrap deletion reasoning into a UI-ready data object.
     */
    const buildInfo = (subtitle, pros, cons, note = '') => {
        const prosHtml = (pros || []).map(li => `<li>${escapeHtml(li)}</li>`).join('');
        const consHtml = (cons || []).map(li => `<li>${escapeHtml(li)}</li>`).join('');
        return {
            subtitle,
            gridHtml: `
                <div class="pro-box">
                    <h4>Why keep</h4>
                    <ul>${consHtml || '<li>(none)</li>'}</ul>
                </div>
                <div class="con-box">
                    <h4>Why delete</h4>
                    <ul>${prosHtml || '<li>(none)</li>'}</ul>
                </div>
            `,
            note
        };
    };

    /**
     * Reasoning Engine for Storage Deletions.
     * Provides structured "Pros/Cons" analysis to help users decide what to delete.
     * @param {string} contextType - The category of the item (dojo, voice, model, media etc).
     * @param {string} name - Name of the primary item.
     * @param {string|null} subName - Human name of the sub-part.
     * @param {string|null} subType - Type classification of sub-part.
     * @returns {Object} Structured info object.
     */
    const getDeleteInfo = (contextType, name, subName = null, subType = null) => {
        // --- Primary Categories ---
        if (contextType === 'dojo') {
            return buildInfo(
                `Voice Project: ${name}`,
                [
                    'Frees a large amount of disk space (often 1–5GB+).',
                    'Reduces clutter if the project is finished.',
                    'Removes old checkpoints you no longer need.'
                ],
                [
                    'You can no longer continue training this voice project.',
                    'You lose all checkpoints and training history for this project.',
                    'If you did not export a final voice, you may lose the voice entirely.'
                ],
                'Tip: If you still want the voice, export a .onnx first (or keep at least the latest checkpoint).'
            );
        }

        if (contextType === 'voice') {
            return buildInfo(
                `Ready Voice: ${name}`,
                [
                    'Reclaims space (usually 50–150MB per voice).',
                    'Removes voices you never use from your list.'
                ],
                [
                    'You will not be able to synthesize speech with this voice until you re-download or re-import it.',
                    'Any automations referring to this voice may fail.'
                ],
                'Tip: If you are unsure, test the voice first and delete later.'
            );
        }

        if (contextType === 'model') {
            const isLanguageConfig = String(name || '').toLowerCase().endsWith('.conf');
            return buildInfo(
                isLanguageConfig ? `Language Config: ${name}` : `Base AI Model: ${name}`,
                isLanguageConfig
                    ? ['Very small space savings (usually tiny).', 'You can reduce clutter if you never use that language.']
                    : ['Big space savings (base models can be large).', 'Useful if you are done training and only doing synthesis.'],
                isLanguageConfig
                    ? ['Training or importing voices for that language may break or require re-downloading this file.']
                    : ['You will not be able to train new voices that depend on this base model until you re-download it.'],
                'Note: Deleting models does not delete your exported voices.'
            );
        }

        if (contextType === 'media') {
            return buildInfo(
                'Audio Session Data (logs & history)',
                [
                    'Improves privacy by removing generated audio/transcription history.',
                    'Can recover some space (varies by usage).'
                ],
                [
                    'You lose your history of generated audio/transcriptions.',
                    'Cannot be undone.'
                ],
                'Tip: This does not affect your installed voices or models.'
            );
        }

        if (contextType === 'training_engine') {
            return buildInfo(
                'AI Training Engine (Docker)',
                [
                    'Reclaims ~17.5GB immediately.',
                    'Good if you only want speech generation (no training).'
                ],
                [
                    'You cannot train new voices until you re-download the engine.',
                    'Training-related tools may stop working until restored.'
                ],
                'Good news: normal speech synthesis will still work.'
            );
        }

        // --- Granular Project Parts (Dojo Sub-parts) ---
        if (contextType === 'dojo_subpart') {
            const label = subName || subType || 'Project Part';
            const lower = String(label).toLowerCase();

            if (lower.includes('training audio')) {
                return buildInfo(
                    `Voice Project: ${name} → Training Audio`,
                    ['Often one of the biggest space savings.', 'Removes potentially sensitive recorded audio from disk.'],
                    ['You cannot re-train or improve the voice without the original audio.', 'If you delete this, continuing training usually becomes impossible.'],
                    'Tip: Keep this until you are 100% done training.'
                );
            }

            if (lower.includes('reference audio')) {
                return buildInfo(
                    `Voice Project: ${name} → Reference Audio`,
                    ['Small to moderate space savings.', 'Good for privacy cleanup if no longer needed.'],
                    ['Some workflows use reference audio for comparisons/quality checks.', 'May reduce your ability to audit or reproduce results later.'],
                    'Tip: If you still have the final voice exported, deleting reference audio won\'t affect synthesis.'
                );
            }

            if (lower.includes('working training data')) {
                return buildInfo(
                    `Voice Project: ${name} → Working Training Data`,
                    ['Can save a lot of space (generated intermediate files).', 'If you never plan to train again, this is safe to remove.'],
                    ['May break the ability to resume training quickly.', 'Rebuilding it later may require re-processing/transcribing audio.'],
                    'Tip: Keep this if you might continue training soon.'
                );
            }

            if (subType === 'voice' || lower.startsWith('voice:')) {
                return buildInfo(
                    `Voice Project: ${name} → Exported Voice`,
                    ['Small space savings compared to training data.', 'Removes duplicate exports if you already imported the final voice.'],
                    ['You may lose this specific exported version.', 'If this is the only export, you won\'t be able to use it without re-exporting.'],
                    'Tip: Keep at least one exported .onnx you like.'
                );
            }

            if (subType === 'checkpoint' || lower.includes('epoch') || lower.includes('checkpoint') || lower.includes('latest:') || lower.includes('archive')) {
                const isArchive = lower.includes('archive');
                return buildInfo(
                    `Voice Project: ${name} → ${isArchive ? 'Archived Checkpoints' : 'Latest Checkpoint'}`,
                    [
                        'Can free a lot of space (checkpoints are usually large).',
                        isArchive ? 'Safest checkpoint cleanup: remove older ones first.' : 'If you are done training, you can remove the latest too.'
                    ],
                    [
                        'Checkpoints are required to resume training.',
                        isArchive ? 'You lose the ability to roll back to an older state.' : 'You lose the ability to continue training from the latest point.'
                    ],
                    'Tip: A good compromise is keeping the latest checkpoint and deleting older archived ones.'
                );
            }

            return buildInfo(
                `Voice Project: ${name} → ${label}`,
                ['Frees space and reduces clutter.'],
                ['May reduce your ability to resume or reproduce training steps.'],
                'If you are unsure, keep it and delete later.'
            );
        }

        return buildInfo(
            `Item: ${name}`,
            ['Frees disk space.'],
            ['Cannot be undone.'],
            ''
        );
    };

    /**
     * Opens the guided Deletion Advisor modal.
     * @param {string} contextType - The classification of the deletion target.
     * @param {string} name - Name of item.
     * @param {string|null} subId - Technical ID of sub-item.
     * @param {string|null} subName - Display name of sub-item.
     * @param {string|null} subType - Type code of sub-item.
     */
    window.showDeleteInfo = (contextType, name, subId = null, subName = null, subType = null) => {
        const modal = document.getElementById('delete-info-modal');
        if (!modal) return;

        const titleEl = document.getElementById('delete-info-title');
        const subtitleEl = document.getElementById('delete-info-subtitle');
        const gridEl = document.getElementById('delete-info-grid');
        const noteEl = document.getElementById('delete-info-note');

        if (titleEl) titleEl.innerHTML = '<i class="fas fa-info-circle"></i> Why keep vs Why delete';
        const info = getDeleteInfo(contextType, name, subName, subType);
        if (subtitleEl) subtitleEl.textContent = info.subtitle || '';
        if (gridEl) gridEl.innerHTML = info.gridHtml || '';
        if (noteEl) noteEl.textContent = info.note || '';

        modal.classList.add('is-open');
        modal.setAttribute('aria-hidden', 'false');
    };

    /**
     * Global close handler for the Delete Advisor modal.
     */
    window.closeDeleteInfoModal = () => {
        const modal = document.getElementById('delete-info-modal');
        if (!modal) return;
        modal.classList.remove('is-open');
        modal.setAttribute('aria-hidden', 'true');
    };

    // Close on click-outside
    document.addEventListener('click', (e) => {
        const modal = document.getElementById('delete-info-modal');
        if (!modal || !modal.classList.contains('is-open')) return;
        if (e.target === modal) {
            window.closeDeleteInfoModal();
        }
    });

    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        const modal = document.getElementById('delete-info-modal');
        if (!modal || !modal.classList.contains('is-open')) return;
        window.closeDeleteInfoModal();
    });

    /**
     * Resolves the FontAwesome icon class for various storage types.
     */
    const getIconForItem = (item, type) => {
        if (item.name && (item.name.endsWith('.conf') || item.name.includes('ESPEAK'))) return 'fa-language';
        switch (type) {
            case 'dojo': return 'fa-project-diagram';
            case 'model': 
                if (item.name === 'F_voice') return 'fa-venus';
                if (item.name === 'M_voice') return 'fa-mars';
                return 'fa-cube';
            case 'voice': return 'fa-microphone';
            case 'language': return 'fa-globe';
            default: return 'fa-file';
        }
    };

    /**
     * Global entry point for storage deletion requests.
     * @param {string} type - Main classification (dojo, voice, etc).
     * @param {string} name - Target item name.
     * @param {string|null} subpath - Specific sub-folder or sub-file to delete.
     */
    window.handleDelete = async (type, name, subpath = null) => {
        let confirmMsg = `Are you sure you want to delete the ${type} "${name}"? This cannot be undone.`;
        if (subpath) {
            confirmMsg = `Are you sure you want to delete "${subpath}" from "${name}"? This will save space but might break this project's ability to continue training.`;
        }

        if (!confirm(confirmMsg)) {
            return;
        }

        try {
            let url = `/api/storage/delete?type=${type}&name=${encodeURIComponent(name)}`;
            if (subpath) url += `&subpath=${encodeURIComponent(subpath)}`;
            
            const response = await fetch(url, {
                method: 'DELETE'
            });
            const result = await response.json();
            
            if (result.status === 'success') {
                if (typeof refreshStorage === 'function') refreshStorage();
            } else {
                alert('Error: ' + result.message);
            }
        } catch (error) {
            alert('Failed to delete item');
        }
    };

    /**
     * Triggers the Docker image pruning process to reclaim large amounts of disk space.
     * Only affects the 'piper-dojo' image (the training engine).
     */
    window.handlePruneDocker = async () => {
        if (!confirm('This will remove the 17GB Training Engine. You will need to re-download it to train new voices. Continue?')) {
            return;
        }

        const btn = document.getElementById('btn-prune-docker');
        const originalHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Removing...';

        try {
            const response = await fetch('/api/tools/prune-docker', { method: 'POST' });
            const data = await response.json();
            if (typeof refreshStorage === 'function') refreshStorage();
        } catch (error) {
            console.error('Failed to prune Docker:', error);
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    };
