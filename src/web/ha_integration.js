/**
 * Home Assistant & Wyoming Integration UI Module
 * Licensed under the MIT License.
 * Copyright (c) 2026 PiperTTS Mockingbird Developers
 * 
 * Provides UI controls for:
 * - Exporting voices to Home Assistant
 * - Managing Wyoming Protocol server
 */

class HomeAssistantIntegration {
    constructor() {
        this.voices = [];
        this.wyomingRunning = false;
        this.init();
    }

    init() {
        // Add HA/Wyoming section to Settings tab
        this.injectUI();
        
        // Load initial status
        this.refreshVoiceList();
        this.checkWyomingStatus();
        
        // Poll Wyoming status every 5 seconds
        setInterval(() => this.checkWyomingStatus(), 5000);
    }

    injectUI() {
        const integrationsTab = document.getElementById('tab-integrations');
        if (!integrationsTab) return;

        // Find the container and CLEAR it to ensure we only have one column and a fresh start
        let container = integrationsTab.querySelector('.integrations-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'integrations-container';
            integrationsTab.appendChild(container);
        }
        container.innerHTML = ''; // Clear everything including static HTML from index.html

        // Create a single main column for everything
        const mainColumn = document.createElement('div');
        mainColumn.className = 'integration-column';
        container.appendChild(mainColumn);

        // 1. Re-add the "Apps & Extensions" section (formerly hardcoded in index.html)
        const appsSection = document.createElement('div');
        appsSection.className = 'settings-section';
        appsSection.innerHTML = `
            <h2><i class="fas fa-plug"></i> Apps & Extensions</h2>
            <p class="help-text">
                Connect your favorite applications to your local Piper TTS server. 
                These tools allow you to use your custom voices across the web and in your documents.
            </p>
            
            <div class="integration-card card">
                <div class="integration-header-row">
                    <div class="integration-icon">
                        <i class="fab fa-chrome"></i>
                    </div>
                    <div class="integration-title">
                        <h3>Mockingbird Browser Extension</h3>
                        <span class="badge badge-success">Ready</span>
                    </div>
                </div>
                <p class="help-text">
                    A privacy-first extension that reads webpages aloud using your local Piper TTS server. 
                    Supports OCR, smart article parsing, and custom voice selection.
                </p>
                <div class="integration-actions">
                    <button class="btn btn-secondary btn-small" onclick="openIntegrationFolder('mockingbird_extension')">
                        <i class="fas fa-folder-open"></i> Open Extension Folder
                    </button>
                </div>
            </div>

            <div class="integration-card card">
                <div class="integration-header-row">
                    <div class="integration-icon">
                        <i class="fas fa-file-word"></i>
                    </div>
                    <div class="integration-title">
                        <h3>Google Docs Add-on</h3>
                        <span class="badge badge-info">Manual Setup</span>
                    </div>
                </div>
                <p class="help-text">
                    Adds high-quality text-to-speech directly to Google Docs. 
                    Use your custom voices to proofread or listen to your documents without leaving the editor.
                </p>
                <div class="integration-actions">
                    <button class="btn btn-secondary btn-small" onclick="openIntegrationFolder('google_docs_addon')">
                        <i class="fas fa-folder-open"></i> Open Add-on Code
                    </button>
                </div>
            </div>

            <div class="integration-card card">
                <div class="integration-header-row">
                    <div class="integration-icon">
                        <i class="fas fa-code"></i>
                    </div>
                    <div class="integration-title">
                        <h3>Mockingbird CLI & API</h3>
                        <span class="badge">Advanced</span>
                    </div>
                </div>
                <p class="help-text">
                    Integrate Piper TTS into your own scripts and batch processes 
                    using the command-line interface or local REST API.
                </p>
                <div class="integration-actions">
                    <a href="api_docs.html" target="_blank" class="btn btn-secondary btn-small" style="text-decoration: none;">
                        <i class="fas fa-book-open"></i> Mockingbird Developer Guide
                    </a>
                </div>
            </div>
        `;
        mainColumn.appendChild(appsSection);

        // 2. Add the "Home Assistant Integration" section
        const haSection = document.createElement('div');
        haSection.className = 'ha-integration-section';
        haSection.innerHTML = `
            <div class="settings-section">
                <h2><i class="fas fa-home"></i> Home Assistant Integration</h2>
                <p class="help-text">
                    Package your voices for Home Assistant's Piper integration or use the Wyoming Protocol for direct discovery.
                </p>

                <div class="card ha-parent-card">
                    <div class="ha-export-panel">
                        <h3>Export Voices for Home Assistant</h3>
                        <div class="export-controls">
                            <button id="ha-refresh-voices" class="btn btn-secondary">
                                <i class="fas fa-sync-alt"></i> Refresh Voice List
                            </button>
                        </div>
                        
                        <div id="ha-voice-list" class="voice-export-list">
                            <p class="loading">Loading voices...</p>
                        </div>
                    </div>

                    <div style="margin: 2.5rem 0; border-top: 1px solid rgba(255,255,255,0.05);"></div>
                    
                    <div class="integration-card card wyoming-card" style="margin-left: 0; margin-right: 0; background: rgba(0,0,0,0.2) !important;">
                        <div class="integration-header-row">
                            <div class="integration-icon">
                                <i class="fas fa-network-wired"></i>
                            </div>
                            <div class="integration-title">
                                <h3>Wyoming Protocol Server</h3>
                                <div class="wyoming-status">
                                    <div class="status-indicator">
                                        <span class="dot" id="wyoming-status-dot"></span>
                                        <span id="wyoming-status-text" class="text-sm">Checking...</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <p class="help-text">
                            Enable Wyoming protocol to make your voices directly accessible to Home Assistant. 
                            Your voices will auto-discover in HA's Piper integration.
                        </p>
                        
                        <div class="wyoming-controls-container">
                            <div class="wyoming-inputs">
                                <div class="input-field">
                                    <label for="wyoming-host">Host</label>
                                    <input type="text" id="wyoming-host" value="0.0.0.0" placeholder="0.0.0.0" />
                                    <small>0.0.0.0 = Accessible by Home Assistant</small>
                                </div>
                                
                                <div class="input-field">
                                    <label for="wyoming-port">Port</label>
                                    <input type="number" id="wyoming-port" value="10200" min="1" max="65535" />
                                    <small>Standard: 10200</small>
                                </div>
                            </div>
                            
                            <div class="integration-actions">
                                <button id="wyoming-start" class="btn btn-primary">
                                    <i class="fas fa-play"></i> Start Server
                                </button>
                                <button id="wyoming-stop" class="btn btn-danger" disabled>
                                    <i class="fas fa-stop"></i> Stop Server
                                </button>
                            </div>

                            <!-- Startup Preference -->
                            <div style="display:flex; align-items:flex-start; gap:0.75rem; padding: 1rem 0; border-top: 1px solid rgba(255,255,255,0.05); margin-top: 1rem;">
                                <input type="checkbox" id="wyoming-startup-checkbox" style="margin-top: 2px; width:18px; height:18px; accent-color:var(--accent); cursor: pointer;">
                                <div style="flex: 1;">
                                    <label for="wyoming-startup-checkbox" style="font-weight:400; color:var(--text-main); cursor:pointer; font-size:0.95rem; display: block;">
                                        🚀 Start Wyoming server automatically on Windows startup
                                    </label>
                                    <div style="font-size:0.85rem; color:var(--text-muted); margin-top: 0.25rem;">
                                        Auto-start Wyoming protocol for seamless Home Assistant integration after system restarts.
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="wyoming-info" id="wyoming-info" style="display: none; margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px solid rgba(255,255,255,0.05);">
                            <h4 style="font-size: 0.9rem; margin-bottom: 0.75rem; color: var(--text-muted);">Connection Info for Home Assistant:</h4>
                            <div style="display: flex; gap: 0.5rem; align-items: center;">
                                <code id="wyoming-connection-info" class="text-mono" style="background: rgba(0,0,0,0.3); padding: 0.5rem 1rem; border-radius: 4px; flex-grow: 1; border: 1px solid rgba(255,255,255,0.1); color: var(--accent);">wyoming://your-ip:10200</code>
                                <button id="copy-wyoming-info" class="btn btn-secondary btn-small">
                                    <i class="fas fa-copy"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        mainColumn.appendChild(haSection);

        // Attach event listeners after everything is in the DOM
        this.attachEventListeners();
    }

    attachEventListeners() {
        console.log("Attaching event listeners for HomeAssistantIntegration...");

        // Use standard references to elements
        const refreshBtn = document.getElementById('ha-refresh-voices');
        const wyomingStartBtn = document.getElementById('wyoming-start');
        const wyomingStopBtn = document.getElementById('wyoming-stop');
        const copyBtn = document.getElementById('copy-wyoming-info');
        const wyomingStartupCheckbox = document.getElementById('wyoming-startup-checkbox');

        if (refreshBtn) {
            refreshBtn.onclick = () => {
                console.log("Refresh Voice List clicked");
                this.refreshVoiceList();
            };
        }

        if (wyomingStartBtn) {
            wyomingStartBtn.onclick = () => {
                console.log("Start Wyoming Server clicked");
                this.startWyoming();
            };
        } else {
            console.error("Could not find wyoming-start button to attach listener");
        }

        if (wyomingStopBtn) {
            wyomingStopBtn.onclick = () => {
                console.log("Stop Wyoming Server clicked");
                this.stopWyoming();
            };
        }

        if (copyBtn) {
            copyBtn.onclick = () => {
                this.copyConnectionInfo();
            };
        }

        if (wyomingStartupCheckbox) {
            wyomingStartupCheckbox.onchange = async () => {
                console.log("Wyoming startup checkbox changed:", wyomingStartupCheckbox.checked);
                await this.toggleWyomingStartup(wyomingStartupCheckbox.checked);
            };
            // Load current startup state
            this.loadWyomingStartupState();
        }
    }

    async refreshVoiceList() {
        const listContainer = document.getElementById('ha-voice-list');
        const countBadge = document.getElementById('ha-voice-count');
        
        if (!listContainer) return;

        try {
            listContainer.innerHTML = '<p class="loading">Loading voices...</p>';

            const response = await fetch('/api/ha/list_voices');
            const data = await response.json();

            if (data.success) {
                this.voices = data.voices;
                
                if (this.voices.length === 0) {
                    listContainer.innerHTML = '<p class="no-data">No voices found in voices/ directory</p>';
                    if (countBadge) countBadge.textContent = '0 voices';
                    return;
                }

                // Update count badge
                if (countBadge) {
                    countBadge.textContent = `${this.voices.length} voice${this.voices.length !== 1 ? 's' : ''}`;
                }

                // Build voice list
                listContainer.innerHTML = this.voices.map(voice => `
                    <div class="voice-export-item" data-voice="${voice.name}">
                        <div class="voice-info">
                            <strong>${voice.name}</strong>
                            <span class="voice-meta">
                                ${voice.language} • ${voice.quality} • ${voice.size_mb}MB
                            </span>
                        </div>
                        <button class="btn btn-primary btn-export" data-voice="${voice.name}">
                            📦 Export for HA
                        </button>
                    </div>
                `).join('');

                // Attach export buttons
                listContainer.querySelectorAll('.btn-export').forEach(btn => {
                    btn.addEventListener('click', (e) => {
                        const voiceName = e.target.getAttribute('data-voice');
                        this.exportVoice(voiceName);
                    });
                });

            } else {
                listContainer.innerHTML = `<p class="error">Error: ${data.error}</p>`;
            }

        } catch (error) {
            console.error('Failed to load voices:', error);
            listContainer.innerHTML = '<p class="error">Failed to load voices</p>';
        }
    }

    async exportVoice(voiceName) {
        const btn = document.querySelector(`.btn-export[data-voice="${voiceName}"]`);
        if (!btn) return;

        const originalText = btn.textContent;
        btn.textContent = '⏳ Exporting...';
        btn.disabled = true;

        try {
            const response = await fetch(`/api/ha/export/${voiceName}`, {
                method: 'POST'
            });
            const data = await response.json();

            if (data.success) {
                btn.textContent = '✅ Exported!';
                
                // Trigger download
                window.location.href = `/api/ha/download/${voiceName}`;
                
                // Show success message
                this.showNotification(`${voiceName} exported successfully!`, 'success');
                
                // Reset button after 3 seconds
                setTimeout(() => {
                    btn.textContent = originalText;
                    btn.disabled = false;
                }, 3000);

            } else {
                btn.textContent = '❌ Failed';
                this.showNotification(`Export failed: ${data.error}`, 'error');
                
                setTimeout(() => {
                    btn.textContent = originalText;
                    btn.disabled = false;
                }, 3000);
            }

        } catch (error) {
            console.error('Export error:', error);
            btn.textContent = '❌ Error';
            this.showNotification('Export failed: Network error', 'error');
            
            setTimeout(() => {
                btn.textContent = originalText;
                btn.disabled = false;
            }, 3000);
        }
    }

    async checkWyomingStatus() {
        try {
            const response = await fetch('/api/wyoming/status');
            const data = await response.json();

            if (data.success) {
                this.updateWyomingUI(data.status);
            }

        } catch (error) {
            console.error('Wyoming status check failed:', error);
        }
    }

    updateWyomingUI(status) {
        const dot = document.getElementById('wyoming-status-dot');
        const text = document.getElementById('wyoming-status-text');
        const startBtn = document.getElementById('wyoming-start');
        const stopBtn = document.getElementById('wyoming-stop');
        const infoPanel = document.getElementById('wyoming-info');
        const connectionInfo = document.getElementById('wyoming-connection-info');

        this.wyomingRunning = status.running;

        if (status.running) {
            // Server is running
            if (dot) {
                dot.className = 'dot running';
            }
            if (text) {
                text.textContent = `Running on ${status.host}:${status.port} (${status.voices_count} voices)`;
            }
            if (startBtn) {
                startBtn.disabled = true;
                startBtn.innerHTML = '<i class="fas fa-play"></i> Start Server';
            }
            if (stopBtn) {
                stopBtn.disabled = false;
                stopBtn.innerHTML = '<i class="fas fa-stop"></i> Stop Server';
            }
            if (infoPanel) {
                infoPanel.style.display = 'block';
            }
            if (connectionInfo) {
                // Use the local IP from the server if available, otherwise try to detect from browser
                let displayHost = status.local_ip || window.location.hostname;
                
                // If still localhost/127.0.0.1, show a helpful placeholder
                if (displayHost === 'localhost' || displayHost === '127.0.0.1' || !displayHost) {
                    displayHost = 'YOUR_IP';
                }
                
                connectionInfo.textContent = `tcp://${displayHost}:${status.port}`;
            }

        } else {
            // Server is stopped
            if (dot) {
                dot.className = 'dot stopped';
            }
            if (text) {
                text.textContent = 'Stopped';
            }
            if (startBtn) {
                startBtn.disabled = false;
                startBtn.innerHTML = '<i class="fas fa-play"></i> Start Server';
            }
            if (stopBtn) {
                stopBtn.disabled = true;
                stopBtn.innerHTML = '<i class="fas fa-stop"></i> Stop Server';
            }
            if (infoPanel) {
                infoPanel.style.display = 'none';
            }
        }
    }

    async startWyoming() {
        const hostInput = document.getElementById('wyoming-host');
        const portInput = document.getElementById('wyoming-port');
        const startBtn = document.getElementById('wyoming-start');

        const host = hostInput?.value || '0.0.0.0';
        const port = parseInt(portInput?.value || '10200');

        if (startBtn) {
            startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...';
            startBtn.disabled = true;
        }

        try {
            const response = await fetch(`/api/wyoming/start?host=${host}&port=${port}`, {
                method: 'POST'
            });
            const data = await response.json();

            if (data.success) {
                this.showNotification('Wyoming server started successfully!', 'success');
                setTimeout(() => this.checkWyomingStatus(), 1000);
            } else {
                this.showNotification(`Failed to start: ${data.error}`, 'error');
                if (startBtn) {
                    startBtn.innerHTML = '<i class="fas fa-play"></i> Start Server';
                    startBtn.disabled = false;
                }
            }

        } catch (error) {
            console.error('Wyoming start error:', error);
            this.showNotification('Failed to start Wyoming server', 'error');
            if (startBtn) {
                startBtn.innerHTML = '<i class="fas fa-play"></i> Start Server';
                startBtn.disabled = false;
            }
        }
    }

    async stopWyoming() {
        const stopBtn = document.getElementById('wyoming-stop');

        if (stopBtn) {
            stopBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Stopping...';
            stopBtn.disabled = true;
        }

        try {
            const response = await fetch('/api/wyoming/stop', {
                method: 'POST'
            });
            const data = await response.json();

            if (data.success) {
                this.showNotification('Wyoming server stopped', 'info');
                setTimeout(() => this.checkWyomingStatus(), 500);
            } else {
                this.showNotification(`Failed to stop: ${data.error}`, 'error');
                if (stopBtn) {
                    stopBtn.innerHTML = '<i class="fas fa-stop"></i> Stop Server';
                    stopBtn.disabled = false;
                }
            }

        } catch (error) {
            console.error('Wyoming stop error:', error);
            this.showNotification('Failed to stop Wyoming server', 'error');
            if (stopBtn) {
                stopBtn.innerHTML = '<i class="fas fa-stop"></i> Stop Server';
                stopBtn.disabled = false;
            }
        }
    }

    copyConnectionInfo() {
        const connectionInfo = document.getElementById('wyoming-connection-info');
        if (!connectionInfo) return;

        const text = connectionInfo.textContent;
        navigator.clipboard.writeText(text).then(() => {
            this.showNotification('Connection info copied to clipboard!', 'success');
        }).catch(err => {
            console.error('Copy failed:', err);
        });
    }

    async loadWyomingStartupState() {
        try {
            const response = await fetch('/api/wyoming/startup');
            const data = await response.json();
            const checkbox = document.getElementById('wyoming-startup-checkbox');
            if (checkbox && data.enabled !== undefined) {
                checkbox.checked = data.enabled;
            }
        } catch (error) {
            console.error('Failed to load Wyoming startup state:', error);
        }
    }

    async toggleWyomingStartup(enabled) {
        try {
            const response = await fetch('/api/wyoming/startup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            });
            
            const data = await response.json();
            
            if (data.success) {
                const statusMsg = enabled 
                    ? 'Wyoming server will now start automatically on Windows startup' 
                    : 'Removed Wyoming server from Windows startup';
                this.showNotification(statusMsg, 'success');
            } else {
                this.showNotification(`Failed to update startup: ${data.error}`, 'error');
                // Revert checkbox on error
                const checkbox = document.getElementById('wyoming-startup-checkbox');
                if (checkbox) checkbox.checked = !enabled;
            }
        } catch (error) {
            console.error('Failed to toggle Wyoming startup:', error);
            this.showNotification('Failed to update startup setting', 'error');
            // Revert checkbox on error
            const checkbox = document.getElementById('wyoming-startup-checkbox');
            if (checkbox) checkbox.checked = !enabled;
        }
    }

    showNotification(message, type = 'info') {
        console.log(`[${type.toUpperCase()}] ${message}`);
        
        // Use existing notification system if available
        if (window.showNotification) {
            window.showNotification(message, type);
        } else {
            // Fallback: show the notification in a way the user can't miss if it's an error
            if (type === 'error') {
                alert(`Error: ${message}`);
            }
        }
    }
}

/**
 * Global helper to open integration folders
 */
async function openIntegrationFolder(name) {
    try {
        const response = await fetch(`/api/integrations/open/${name}`, { method: 'POST' });
        const data = await response.json();
        if (!data.success) {
            if (window.haIntegration) window.haIntegration.showNotification(`Failed to open folder: ${data.error}`, 'error');
        }
    } catch (err) {
        console.error('Failed to open folder:', err);
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.haIntegration = new HomeAssistantIntegration();
    });
} else {
    window.haIntegration = new HomeAssistantIntegration();
}
