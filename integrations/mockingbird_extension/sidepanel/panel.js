/**
 * Mockingbird Browser Extension - Side Panel UI
 * Licensed under the MIT License.
 * Copyright (c) 2026 PiperTTS Mockingbird Developers
 */

const PIPER_SERVER = 'http://localhost:5002';

// Default shared API key (matches server default for automatic protection)
// Change this if you customize PIPER_API_KEY on the server
const API_KEY = 'piper-mockingbird-local-2026';

// UI Elements
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const readPageBtn = document.getElementById('read-page-btn');
const readSelectionBtn = document.getElementById('read-selection-btn');
const screenshotOcrBtn = document.getElementById('screenshot-ocr-btn');
const playPauseBtn = document.getElementById('play-pause-btn');
const stopBtn = document.getElementById('stop-btn');
const prevBtn = document.getElementById('prev-btn');
const nextBtn = document.getElementById('next-btn');
const voiceSelect = document.getElementById('voice-select');
const randomCheckbox = document.getElementById('random-checkbox');
const testTextInput = document.getElementById('test-text-input');
const testVoiceBtn = document.getElementById('test-voice-btn');
const stopTestBtn = document.getElementById('stop-test-btn');
const downloadVoiceBtn = document.getElementById('download-voice-btn');
const testLoading = document.getElementById('test-loading');
const speedValue = document.getElementById('speed-value');
const speedPresets = document.querySelectorAll('.preset-btn');
const volumeSlider = document.getElementById('volume-slider');
const volumeValue = document.getElementById('volume-value');
const serverUrlInput = document.getElementById('server-url');
const testConnectionBtn = document.getElementById('test-connection-btn');
const autoScrollToggle = document.getElementById('auto-scroll-toggle');
const jumpButtons = document.querySelectorAll('.jump-btn');
const sleepTimerSelect = document.getElementById('sleep-timer-select');
const themeToggle = document.getElementById('theme-toggle');
const progressScrubber = document.getElementById('progress-scrubber');
const progressFill = document.getElementById('progress-fill');
const currentTimeEl = document.getElementById('current-time');
const totalTimeEl = document.getElementById('total-time');
const readingPositionEl = document.getElementById('reading-position');
const positionText = document.getElementById('position-text');
const wordsPerSecondEl = document.getElementById('words-per-second');
const wpsText = document.getElementById('wps-text');

// OCR UI Elements
const ocrModal = document.getElementById('ocr-modal');
const ocrCloseBtn = document.getElementById('ocr-close-btn');
const ocrStatus = document.getElementById('ocr-status');
const ocrPreviewContainer = document.getElementById('ocr-preview-container');
const ocrPreviewImg = document.getElementById('ocr-preview-img');
const ocrTextArea = document.getElementById('ocr-text-area');
const ocrConfidence = document.getElementById('ocr-confidence');
const ocrWordCount = document.getElementById('ocr-word-count');
const ocrReadBtn = document.getElementById('ocr-read-btn');
const ocrStopBtn = document.getElementById('ocr-stop-btn');
const ocrCopyBtn = document.getElementById('ocr-copy-btn');
const ocrRetryBtn = document.getElementById('ocr-retry-btn');

// Voice test state
let isTestPlaying = false;
let testAudio = null;

// OCR state
let currentOCRResult = null;
let currentSentenceState = null;
let wordHighlightTimeouts = [];
const ocrTextViewer = document.getElementById('ocr-text-viewer');

// Initialize
initialize();

async function initialize() {
  // Load saved settings
  const settings = await chrome.storage.local.get([
    'voice',
    'speed',
    'volume',
    'serverUrl',
    'autoScroll',
    'darkTheme'
  ]);

  // Apply theme
  if (settings.darkTheme) {
    document.body.classList.add('dark-theme');
    themeToggle.querySelector('.theme-icon').textContent = '☀️';
  }

  if (settings.speed) {
    speedValue.textContent = settings.speed;
    updateSpeedPresets(settings.speed);
  }

  if (settings.volume !== undefined) {
    volumeSlider.value = settings.volume * 100;
    volumeValue.textContent = Math.round(settings.volume * 100);
  }

  if (settings.serverUrl) {
    serverUrlInput.value = settings.serverUrl;
  }
  
  if (settings.autoScroll !== undefined) {
    autoScrollToggle.checked = settings.autoScroll;
  }

  // Load voices
  await loadVoices();

  if (settings.voice) {
    voiceSelect.value = settings.voice;
  }

  // Check server connection
  checkServerConnection();

  // Set up event listeners
  setupEventListeners();

  // Update reader state
  updateReaderState();
  
  // Start progress update interval
  setInterval(updateProgress, 500);
}

function setupEventListeners() {
  // Main controls
  readPageBtn.addEventListener('click', async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) {
      chrome.tabs.sendMessage(tab.id, { action: 'getTextToRead' }, (response) => {
        if (response && response.text) {
          chrome.runtime.sendMessage({
            action: 'startReading',
            text: response.text
          });
        }
      });
    }
  });

  readSelectionBtn.addEventListener('click', async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) {
      chrome.tabs.sendMessage(tab.id, { action: 'getTextToRead' }, (response) => {
        if (response && response.text) {
          chrome.runtime.sendMessage({
            action: 'startReading',
            text: response.text
          });
        }
      });
    }
  });

  // Playback controls
  playPauseBtn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'togglePlayPause' }, () => {
      updateReaderState();
    });
  });

  stopBtn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'stopReading' }, () => {
      updateReaderState();
    });
  });

  prevBtn.addEventListener('click', () => {
    console.log('[Mockingbird Panel] prevBtn clicked');
    chrome.runtime.sendMessage({ action: 'skipBackward' }, (response) => {
      if (chrome.runtime.lastError) {
        console.error('[Mockingbird Panel] skipBackward failed:', chrome.runtime.lastError.message);
      } else {
        console.log('[Mockingbird Panel] skipBackward response:', response);
      }
    });
  });

  nextBtn.addEventListener('click', () => {
    console.log('[Mockingbird Panel] nextBtn clicked');
    chrome.runtime.sendMessage({ action: 'skipForward' }, (response) => {
      if (chrome.runtime.lastError) {
        console.error('[Mockingbird Panel] skipForward failed:', chrome.runtime.lastError.message);
      } else {
        console.log('[Mockingbird Panel] skipForward response:', response);
      }
    });
  });

  // Settings
  voiceSelect.addEventListener('change', () => {
    const voice = voiceSelect.value;
    chrome.runtime.sendMessage({ action: 'setVoice', voice });
    chrome.storage.local.set({ voice });
  });
  
  // Random checkbox toggle
  randomCheckbox.addEventListener('change', () => {
    if (randomCheckbox.checked) {
      testTextInput.disabled = true;
      testTextInput.style.background = 'var(--bg-tertiary)';
    } else {
      testTextInput.disabled = false;
      testTextInput.style.background = 'var(--bg-primary)';
      testTextInput.focus();
    }
  });
  
  // Test voice button
  testVoiceBtn.addEventListener('click', async () => {
    const voice = voiceSelect.value;
    if (!voice) {
      testLoading.textContent = 'Please select a voice first';
      setTimeout(() => testLoading.textContent = '', 2000);
      return;
    }
    
    // Stop any currently playing test audio
    if (isTestPlaying && testAudio) {
      testAudio.pause();
      testAudio = null;
      isTestPlaying = false;
      stopTestBtn.disabled = true;
    }
    
    const testMessages = [
      "Hey there! I'm Piper, your friendly text-to-speech assistant!",
      "Testing one two three! Sounds great, doesn't it?",
      "Hello! I can speak anything you type. Pretty cool, right?",
      "Beep boop! Just kidding, I'm much better than a robot!",
      "Ready to chat? I'm all ears... well, actually all voice!",
    ];
    
    let sampleText;
    if (randomCheckbox.checked) {
      sampleText = testMessages[Math.floor(Math.random() * testMessages.length)];
    } else {
      sampleText = testTextInput.value.trim();
      if (!sampleText) {
        sampleText = "Please enter some text for me to voice.";
      }
    }
    
    try {
      testVoiceBtn.disabled = true;
      testLoading.textContent = 'Generating...';
      
      const response = await fetch(`${serverUrlInput.value || PIPER_SERVER}/api/tts`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          ...(API_KEY ? { 'X-API-Key': API_KEY } : {})
        },
        body: JSON.stringify({ text: sampleText, voice_model: voice })
      });
      
      if (response.ok) {
        const audioBlob = await response.blob();
        const audioUrl = URL.createObjectURL(audioBlob);
        testAudio = new Audio(audioUrl);
        
        testLoading.textContent = '';
        isTestPlaying = true;
        stopTestBtn.disabled = false;
        
        testAudio.onended = () => {
          isTestPlaying = false;
          stopTestBtn.disabled = true;
          testVoiceBtn.disabled = false;
        };
        
        testAudio.onerror = () => {
          testLoading.textContent = 'Playback failed';
          setTimeout(() => testLoading.textContent = '', 2000);
          isTestPlaying = false;
          stopTestBtn.disabled = true;
          testVoiceBtn.disabled = false;
        };
        
        await testAudio.play();
        testVoiceBtn.disabled = false;
      } else {
        testLoading.textContent = 'Generation failed';
        setTimeout(() => testLoading.textContent = '', 2000);
        testVoiceBtn.disabled = false;
      }
    } catch (error) {
      console.error('Test voice failed:', error);
      testLoading.textContent = 'Error: ' + error.message;
      setTimeout(() => testLoading.textContent = '', 3000);
      testVoiceBtn.disabled = false;
    }
  });
  
  // Stop test button
  stopTestBtn.addEventListener('click', () => {
    if (testAudio) {
      testAudio.pause();
      testAudio = null;
    }
    isTestPlaying = false;
    stopTestBtn.disabled = true;
  });
  
  // Download voice button
  downloadVoiceBtn.addEventListener('click', async () => {
    const voice = voiceSelect.value;
    if (!voice) {
      testLoading.textContent = 'Please select a voice first';
      setTimeout(() => testLoading.textContent = '', 2000);
      return;
    }
    
    const testMessages = [
      "Hey there! I'm Piper, your friendly text-to-speech assistant!",
      "Testing one two three! Sounds great, doesn't it?",
      "Hello! I can speak anything you type. Pretty cool, right?",
      "Beep boop! Just kidding, I'm much better than a robot!",
      "Ready to chat? I'm all ears... well, actually all voice!",
    ];
    
    let sampleText;
    if (randomCheckbox.checked) {
      sampleText = testMessages[Math.floor(Math.random() * testMessages.length)];
    } else {
      sampleText = testTextInput.value.trim();
      if (!sampleText) {
        testLoading.textContent = 'Please enter text to download';
        setTimeout(() => testLoading.textContent = '', 2000);
        return;
      }
    }
    
    try {
      downloadVoiceBtn.disabled = true;
      testLoading.textContent = 'Generating audio...';
      
      const response = await fetch(`${serverUrlInput.value || PIPER_SERVER}/api/tts`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          ...(API_KEY ? { 'X-API-Key': API_KEY } : {})
        },
        body: JSON.stringify({ text: sampleText, voice_model: voice })
      });
      
      if (response.ok) {
        const audioBlob = await response.blob();
        const url = URL.createObjectURL(audioBlob);
        const a = document.createElement('a');
        a.href = url;
        
        // Create filename from first few words of text
        const filename = sampleText.substring(0, 30).replace(/[^a-z0-9]/gi, '_').toLowerCase() + '.wav';
        a.download = filename;
        
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        testLoading.textContent = 'Downloaded!';
        setTimeout(() => testLoading.textContent = '', 2000);
      } else {
        testLoading.textContent = 'Download failed';
        setTimeout(() => testLoading.textContent = '', 2000);
      }
    } catch (error) {
      console.error('Download failed:', error);
      testLoading.textContent = 'Error: ' + error.message;
      setTimeout(() => testLoading.textContent = '', 3000);
    } finally {
      downloadVoiceBtn.disabled = false;
    }
  });
  
  // Speed presets
  speedPresets.forEach(btn => {
    btn.addEventListener('click', () => {
      const speed = parseFloat(btn.dataset.speed);
      speedValue.textContent = speed.toFixed(1);
      updateSpeedPresets(speed);
      chrome.runtime.sendMessage({ action: 'setSpeed', speed });
      chrome.storage.local.set({ speed });
    });
  });
  
  // Theme toggle
  themeToggle.addEventListener('click', () => {
    const isDark = document.body.classList.toggle('dark-theme');
    themeToggle.querySelector('.theme-icon').textContent = isDark ? '☀️' : '🌙';
    chrome.storage.local.set({ darkTheme: isDark });
  });
  
  // Progress scrubber
  progressScrubber.addEventListener('input', () => {
    const percent = progressScrubber.value;
    progressFill.style.width = `${percent}%`;
  });
  
  progressScrubber.addEventListener('change', () => {
    const percent = progressScrubber.value;
    chrome.runtime.sendMessage({ action: 'seekTo', percent: parseFloat(percent) });
  });

  volumeSlider.addEventListener('input', () => {
    const volume = parseInt(volumeSlider.value) / 100;
    volumeValue.textContent = Math.round(volume * 100);
    chrome.runtime.sendMessage({ action: 'setVolume', volume });
    chrome.storage.local.set({ volume });
  });

  serverUrlInput.addEventListener('change', () => {
    const serverUrl = serverUrlInput.value;
    chrome.storage.local.set({ serverUrl });
    checkServerConnection();
  });

  testConnectionBtn.addEventListener('click', () => {
    checkServerConnection();
  });
  
  // Auto-scroll toggle
  autoScrollToggle.addEventListener('change', () => {
    const enabled = autoScrollToggle.checked;
    chrome.runtime.sendMessage({ action: 'toggleAutoScroll', enabled });
    chrome.storage.local.set({ autoScroll: enabled });
  });

  // Screenshot OCR
  if (screenshotOcrBtn) {
    screenshotOcrBtn.addEventListener('click', async () => {
      console.log('[OCR Button] Opening sidepanel...');
      
      // First, open sidepanel directly (user gesture context is here!)
      try {
        const currentWindow = await chrome.windows.getCurrent();
        await chrome.sidePanel.open({ windowId: currentWindow.id });
        console.log('[OCR Button] Sidepanel opened successfully');
      } catch (err) {
        console.warn('[Mockingbird OCR] Could not open sidepanel:', err);
      }
      
      // Small delay to let sidepanel open
      await new Promise(resolve => setTimeout(resolve, 150));
      
      // Then activate OCR capture
      console.log('[OCR Button] Activating OCR capture...');
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id) {
        console.error('[OCR Button] No active tab found');
        return;
      }
      
      chrome.tabs.sendMessage(tab.id, { type: 'ACTIVATE_OCR_CAPTURE' }).catch(err => {
        console.error('[Mockingbird OCR] Failed to activate capture:', err);
        alert('Could not start OCR. Please refresh the page and try again.');
      });
    });
  }

  // OCR Modal Buttons
  if (ocrCloseBtn && ocrModal) {
    ocrCloseBtn.addEventListener('click', () => {
      ocrModal.style.display = 'none';
    });
  }

  if (ocrReadBtn && ocrModal) {
    ocrReadBtn.addEventListener('click', () => {
      const text = ocrTextArea?.value?.trim() || '';
      if (!text) return;
      
      // Log current state for debugging
      chrome.runtime.sendMessage({ action: 'getState' }, (response) => {
        console.log('[OCR Read] Current reader state:', response?.state);
        console.log('[OCR Read] Speed:', response?.state?.readingSpeed, 'Volume:', response?.state?.volume, 'Voice:', response?.state?.currentVoice);
      });
      
      chrome.runtime.sendMessage({ action: 'startReading', text });
      // Keep the OCR modal open while reading, so you can copy/stop/etc.
      updateReaderState();
    });
  }

  if (ocrStopBtn) {
    ocrStopBtn.addEventListener('click', () => {
      chrome.runtime.sendMessage({ action: 'stopReading' }, () => {
        updateReaderState();
      });
    });
  }

  if (ocrCopyBtn) {
    ocrCopyBtn.addEventListener('click', async () => {
      const text = ocrTextArea?.value?.trim() || '';
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        const originalText = ocrCopyBtn.textContent;
        ocrCopyBtn.textContent = 'Copied!';
        setTimeout(() => (ocrCopyBtn.textContent = originalText), 2000);
      } catch (err) {
        console.error('Failed to copy:', err);
      }
    });
  }

  if (ocrRetryBtn && ocrModal) {
    ocrRetryBtn.addEventListener('click', async () => {
      ocrModal.style.display = 'none';
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab?.id) {
        chrome.tabs.sendMessage(tab.id, { type: 'ACTIVATE_OCR_CAPTURE' }).catch(() => {});
      }
    });
  }

  // Listen for OCR results from background
  chrome.runtime.onMessage.addListener((message) => {
    if (message?.type === 'OCR_RESULT') {
      handleOCRResult(message.result, message.image);
    } else if (message?.type === 'OCR_ERROR') {
      handleOCRError(message.error);
    } else if (message?.action === 'readerEvent') {
      handleReaderEvent(message.event, message.data);
    } else if (message?.action === 'audioDuration' && typeof message.duration === 'number') {
      handleAudioDuration(message.duration);
    }
  });
  
  // Skip buttons removed - Piper works sentence-by-sentence, not time-based
  // Use prev/next sentence buttons instead
  
  // Jump buttons
  jumpButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const percentage = parseInt(btn.dataset.percent);
      chrome.runtime.sendMessage({ action: 'jumpToPercentage', percentage });
    });
  });
  
  // Sleep timer
  sleepTimerSelect.addEventListener('change', () => {
    const minutes = parseInt(sleepTimerSelect.value);
    if (minutes > 0) {
      chrome.runtime.sendMessage({ action: 'setSleepTimer', minutes });
    } else {
      chrome.runtime.sendMessage({ action: 'cancelSleepTimer' });
    }
  });
  
  // OCR settings
  const ocrLanguageSelect = document.getElementById('ocr-language');
  const ocrAutoReadCheckbox = document.getElementById('ocr-auto-read');
  
  if (ocrLanguageSelect) {
    // Load saved OCR language
    chrome.storage.local.get(['ocrLanguage'], (result) => {
      if (result.ocrLanguage) {
        ocrLanguageSelect.value = result.ocrLanguage;
      }
    });
    
    ocrLanguageSelect.addEventListener('change', () => {
      const language = ocrLanguageSelect.value;
      chrome.runtime.sendMessage({ action: 'setOCRLanguage', language });
      chrome.storage.local.set({ ocrLanguage: language });
    });
  }
  
  if (ocrAutoReadCheckbox) {
    // Load saved OCR auto-read setting
    chrome.storage.local.get(['ocrAutoRead'], (result) => {
      ocrAutoReadCheckbox.checked = result.ocrAutoRead || false;
    });
    
    ocrAutoReadCheckbox.addEventListener('change', () => {
      const enabled = ocrAutoReadCheckbox.checked;
      chrome.runtime.sendMessage({ action: 'setOCRAutoRead', enabled });
      chrome.storage.local.set({ ocrAutoRead: enabled });
    });
  }

  // Poll reader state periodically
  setInterval(updateReaderState, 1000);
}

async function loadVoices() {
  try {
    statusText.textContent = 'Loading voices...';
    
    const response = await chrome.runtime.sendMessage({ action: 'getVoices' });
    
    if (response && response.voices && response.voices.length > 0) {
      voiceSelect.innerHTML = '';
      
      response.voices.forEach(voice => {
        const option = document.createElement('option');
        option.value = voice;
        option.textContent = formatVoiceName(voice);
        voiceSelect.appendChild(option);
      });
      
      statusText.textContent = `${response.voices.length} voices available`;
    } else {
      voiceSelect.innerHTML = '<option value="">No voices found</option>';
      statusText.textContent = 'No voices available';
    }
  } catch (error) {
    console.error('Error loading voices:', error);
    voiceSelect.innerHTML = '<option value="">Error loading voices</option>';
    statusText.textContent = 'Error loading voices';
  }
}

function formatVoiceName(filename) {
  // Convert "en_US-hfc_female-medium.onnx" to "HFC Female (Medium)"
  return filename
    .replace('.onnx', '')
    .replace(/^en_[A-Z]{2}-/, '')
    .replace(/_/g, ' ')
    .replace(/-/g, ' ')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

async function checkServerConnection() {
  const settings = await chrome.storage.local.get(['serverUrl']);
  const serverUrl = settings.serverUrl || PIPER_SERVER;

  try {
    statusText.textContent = 'Checking server...';
    statusDot.className = 'status-dot';

    const response = await fetch(`${serverUrl}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(5000)
    });

    if (response.ok) {
      const data = await response.json();
      statusText.textContent = `✓ Server connected (${data.available_voices?.length || 0} voices)`;
      statusDot.className = 'status-dot connected';
      
      // Schedule next check in 30 seconds
      setTimeout(() => checkServerConnection(), 30000);
    } else {
      throw new Error('Server not responding');
    }
  } catch (error) {
    console.error('Connection error:', error);
    statusText.textContent = '✗ Server offline - Check if Piper is running';
    statusDot.className = 'status-dot error';
    
    // Retry sooner when offline (10 seconds)
    setTimeout(() => checkServerConnection(), 10000);
  }
}

async function updateReaderState() {
  try {
    const response = await chrome.runtime.sendMessage({ action: 'getState' });
    
    if (response && response.state) {
      const state = response.state;
      const { isReading, isPaused } = state;
      
      // Update button states
      readPageBtn.disabled = isReading && !isPaused;
      readSelectionBtn.disabled = isReading && !isPaused;
      
      playPauseBtn.disabled = !isReading && !isPaused;
      stopBtn.disabled = !isReading;
      prevBtn.disabled = !isReading;
      nextBtn.disabled = !isReading;
      progressScrubber.disabled = !isReading;

      if (ocrStopBtn) {
        ocrStopBtn.disabled = !isReading;
      }

      if (isReading) {
        playPauseBtn.querySelector('span').textContent = isPaused ? '▶' : '⏸';
        playPauseBtn.title = isPaused ? 'Resume' : 'Pause';
      } else {
        playPauseBtn.querySelector('span').textContent = '⏯';
        playPauseBtn.title = 'Play';
      }
      
      // Update connection status
      if (state.serverConnected) {
        statusDot.className = 'status-dot online';
        statusText.textContent = 'Server connected';
      } else {
        statusDot.className = 'status-dot offline';
        statusText.textContent = 'Server offline';
      }
      
      // Update position display
      if (isReading && state.currentPosition !== undefined && state.totalSentences !== undefined) {
        positionText.textContent = `Sentence ${state.currentPosition + 1} of ${state.totalSentences}`;
        readingPositionEl.style.display = 'block';
        
        // Update progress scrubber
        if (state.totalSentences > 0) {
          const percent = (state.currentPosition / state.totalSentences) * 100;
          progressScrubber.value = percent;
          progressFill.style.width = `${percent}%`;
        }
      } else {
        readingPositionEl.style.display = 'none';
      }
    }
  } catch (error) {
    // Background might not be ready yet
    console.debug('Could not get reader state:', error);
  }
}

// Helper function to update speed preset buttons
function updateSpeedPresets(speed) {
  speedPresets.forEach(btn => {
    const btnSpeed = parseFloat(btn.dataset.speed);
    if (Math.abs(btnSpeed - speed) < 0.05) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

// Update progress bar and time display
async function updateProgress() {
  try {
    const response = await chrome.runtime.sendMessage({ action: 'getProgress' });
    
    if (response && response.currentTime !== undefined) {
      const { currentTime, totalTime, currentParagraph, totalParagraphs, wordsPerSecond } = response;
      
      // Update time display
      currentTimeEl.textContent = formatTime(currentTime);
      totalTimeEl.textContent = formatTime(totalTime);
      
      // Update progress bar
      const percent = totalTime > 0 ? (currentTime / totalTime) * 100 : 0;
      progressFill.style.width = `${percent}%`;
      progressScrubber.value = percent;
      
      // Update reading position
      if (currentParagraph > 0 && totalParagraphs > 0) {
        readingPositionEl.style.display = 'block';
        positionText.textContent = `${currentParagraph} / ${totalParagraphs}`;
      } else {
        readingPositionEl.style.display = 'none';
      }
      
      // Update words per second display
      if (wordsPerSecond !== null && wordsPerSecond !== undefined && wordsPerSecond > 0) {
        wordsPerSecondEl.style.display = 'block';
        wpsText.textContent = `⚡ ${wordsPerSecond.toFixed(1)} words/sec`;
      } else {
        wordsPerSecondEl.style.display = 'none';
      }
    }
  } catch (error) {
    // Reader not active, hide progress
    readingPositionEl.style.display = 'none';
    wordsPerSecondEl.style.display = 'none';
  }
}

// Format seconds to MM:SS
function formatTime(seconds) {
  if (!seconds || isNaN(seconds)) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// OCR Handlers
function handleOCRResult(result, image) {
  currentOCRResult = result;

  if (!ocrModal) return;
  ocrModal.style.display = 'flex';

  if (ocrStatus) {
    ocrStatus.textContent = 'OCR Processing Complete';
    ocrStatus.className = 'ocr-status success';
  }

  if (ocrPreviewContainer && ocrPreviewImg) {
    if (image) {
      ocrPreviewImg.src = image;
      ocrPreviewContainer.style.display = 'block';
    } else {
      ocrPreviewContainer.style.display = 'none';
    }
  }

  const text = result?.text || '';
  
  if (ocrTextArea) {
    ocrTextArea.value = text;
  }

  if (ocrTextViewer) {
    ocrTextViewer.textContent = text;
  }

  if (ocrConfidence) {
    ocrConfidence.textContent = `Confidence: ${Math.round(result?.confidence ?? 0)}%`;
  }

  if (ocrWordCount) {
    const wordCount = text.split(/\s+/).filter(w => w.length > 0).length;
    ocrWordCount.textContent = `${wordCount} words extracted`;
  }

  const hasText = !!text.trim();
  if (ocrReadBtn) ocrReadBtn.disabled = !hasText;
  if (ocrCopyBtn) ocrCopyBtn.disabled = !hasText;
  if (ocrStopBtn) ocrStopBtn.disabled = true;
}

function handleOCRError(error) {
  if (!ocrModal) return;
  ocrModal.style.display = 'flex';

  if (ocrStatus) {
    ocrStatus.textContent = `Error: ${error || 'OCR failed'}`;
    ocrStatus.className = 'ocr-status error';
  }
  if (ocrPreviewContainer) ocrPreviewContainer.style.display = 'none';
  if (ocrTextArea) ocrTextArea.value = '';
  if (ocrConfidence) ocrConfidence.textContent = '';
  if (ocrWordCount) ocrWordCount.textContent = '';
  if (ocrReadBtn) ocrReadBtn.disabled = true;
  if (ocrCopyBtn) ocrCopyBtn.disabled = true;
  if (ocrStopBtn) ocrStopBtn.disabled = true;
}

// OCR Text Highlighting Functions
function handleReaderEvent(event, data) {
  console.log('[Mockingbird] Handling reader event:', event, data);
  
  if (!ocrTextViewer || !ocrTextArea) return;
  
  if (event === 'sentenceStart') {
    const sentence = (data && (data.sentence || data.text)) || '';
    if (!sentence) return;
    console.log('[Mockingbird] Highlighting sentence:', sentence);
    const words = (data && Array.isArray(data.words)) ? data.words : null;
    clearWordTimers();
    currentSentenceState = null;
    highlightSentenceInViewer(ocrTextViewer, ocrTextArea.value, sentence, words);
  } else if (event === 'paused') {
    clearWordTimers();
    clearWordHighlight(ocrTextViewer);
  } else if (event === 'resumed') {
    // Wait for next sentenceStart/audioDuration
  } else if (event === 'stopped' || event === 'readingComplete') {
    clearWordTimers();
    clearViewerHighlight(ocrTextViewer);
  }
}

function handleAudioDuration(durationSeconds) {
  if (!currentSentenceState || !currentSentenceState.wordRanges || !currentSentenceState.words) {
    return;
  }
  scheduleWordHighlights(durationSeconds, currentSentenceState);
}

function clearWordTimers() {
  for (const id of wordHighlightTimeouts) {
    clearTimeout(id);
  }
  wordHighlightTimeouts = [];
}

function clearViewerHighlight(viewer) {
  if (!viewer) return;
  
  // Remove Custom Highlight API highlight
  if (window.CSS && CSS.highlights) {
    try {
      CSS.highlights.delete('Mockingbird-ocr-sentence');
      CSS.highlights.delete('Mockingbird-ocr-word');
    } catch (_) {}
  }

  // Remove fallback <mark>
  const existing = viewer.querySelector('mark[data-Mockingbird-sentence]');
  if (existing) {
    const wordSpan = existing.querySelector('span[data-Mockingbird-word]');
    if (wordSpan) {
      const wsParent = wordSpan.parentNode;
      while (wordSpan.firstChild) wsParent.insertBefore(wordSpan.firstChild, wordSpan);
      wsParent.removeChild(wordSpan);
    }
    const parent = existing.parentNode;
    while (existing.firstChild) parent.insertBefore(existing.firstChild, existing);
    parent.removeChild(existing);
    parent.normalize();
  }
}

function clearWordHighlight(viewer) {
  if (!viewer) return;
  
  if (window.CSS && CSS.highlights) {
    try {
      CSS.highlights.delete('Mockingbird-ocr-word');
    } catch (_) {}
  }

  const mark = viewer.querySelector('mark[data-Mockingbird-sentence]');
  if (!mark) return;

  const wordSpan = mark.querySelector('span[data-Mockingbird-word]');
  if (wordSpan) {
    const parent = wordSpan.parentNode;
    while (wordSpan.firstChild) parent.insertBefore(wordSpan.firstChild, wordSpan);
    parent.removeChild(wordSpan);
    parent.normalize();
  }
}

function highlightSentenceInViewer(viewer, fullText, sentence, words) {
  console.log('[Mockingbird] Attempting to highlight:', sentence.substring(0, 50));
  const text = fullText || '';
  if (!text) return;

  clearViewerHighlight(viewer);

  // Ensure viewer matches the current source
  if (viewer.textContent !== text) {
    viewer.textContent = text;
  }
  
  // Try to find the sentence (trim and normalize whitespace)
  const normalizedSentence = sentence.trim().replace(/\s+/g, ' ');
  const normalizedText = text.replace(/\s+/g, ' ');
  
  let index = normalizedText.indexOf(normalizedSentence);
  
  if (index === -1) {
    // Try partial match
    const firstWords = normalizedSentence.split(' ').slice(0, 5).join(' ');
    index = normalizedText.indexOf(firstWords);
    console.log('[Mockingbird] Partial match attempt with:', firstWords, 'index:', index);
  }
  
  if (index === -1) {
    console.warn('[Mockingbird] Could not find sentence in OCR text');
    return;
  }

  // Map normalized index back to original text index
  let originalIndex = 0;
  let normalizedIndex = 0;
  while (normalizedIndex < index && originalIndex < text.length) {
    if (/\s/.test(text[originalIndex])) {
      if (originalIndex > 0 && /\s/.test(text[originalIndex - 1])) {
        originalIndex++;
      } else {
        originalIndex++;
        normalizedIndex++;
      }
    } else {
      originalIndex++;
      normalizedIndex++;
    }
  }

  while (originalIndex < text.length && /\s/.test(text[originalIndex])) {
    originalIndex++;
  }

  const length = sentence.length;
  const start = Math.max(0, Math.min(originalIndex, text.length));
  const end = Math.max(start, Math.min(start + length, text.length));

  console.log('[Mockingbird] Highlighting at position:', start, 'length:', end - start);

  const range = buildRangeFromOffsets(viewer, start, end);
  if (!range) {
    console.warn('[Mockingbird] Could not build DOM range for sentence highlight');
    return;
  }

  // Prefer Custom Highlight API when available
  if (window.CSS && CSS.highlights && typeof Highlight !== 'undefined') {
    try {
      const highlight = new Highlight(range);
      CSS.highlights.set('Mockingbird-ocr-sentence', highlight);
    } catch (e) {
      console.warn('[Mockingbird] CSS highlight failed, falling back to <mark>:', e);
      fallbackMarkRange(range);
    }
  } else {
    fallbackMarkRange(range);
  }

  // Prepare word ranges for per-word highlight
  if (words && words.length > 0) {
    currentSentenceState = {
      text,
      start,
      end,
      words,
      wordRanges: computeWordRanges(text, start, end, words)
    };
  } else {
    currentSentenceState = null;
  }

  // Scroll so the highlight is visible
  const lineHeight = parseInt(window.getComputedStyle(viewer).lineHeight) || 20;
  const lines = text.substring(0, start).split('\n').length;
  viewer.scrollTop = Math.max(0, (lines - 2) * lineHeight);

  console.log('[Mockingbird] Highlight applied successfully');
}

function fallbackMarkRange(range) {
  try {
    const mark = document.createElement('mark');
    mark.setAttribute('data-Mockingbird-sentence', '1');
    range.surroundContents(mark);
  } catch (e) {
    console.warn('[Mockingbird] Fallback mark highlight failed:', e);
  }
}

function buildRangeFromOffsets(containerEl, start, end) {
  const range = document.createRange();
  const walker = document.createTreeWalker(containerEl, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  let offset = 0;
  let startNode = null;
  let startOffset = 0;
  let endNode = null;
  let endOffset = 0;

  while (node) {
    const nodeText = node.nodeValue || '';
    const nextOffset = offset + nodeText.length;

    if (!startNode && start >= offset && start <= nextOffset) {
      startNode = node;
      startOffset = start - offset;
    }
    if (!endNode && end >= offset && end <= nextOffset) {
      endNode = node;
      endOffset = end - offset;
    }
    if (startNode && endNode) break;

    offset = nextOffset;
    node = walker.nextNode();
  }

  if (!startNode || !endNode) return null;
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  return range;
}

function computeWordRanges(fullText, sentenceStart, sentenceEnd, words) {
  const ranges = [];
  let cursor = sentenceStart;

  for (const word of words) {
    if (!word) {
      ranges.push(null);
      continue;
    }

    const idx = fullText.indexOf(word, cursor);
    if (idx === -1 || idx > sentenceEnd) {
      ranges.push(null);
      continue;
    }

    const wStart = idx;
    const wEnd = Math.min(idx + word.length, fullText.length);
    ranges.push({ start: wStart, end: wEnd });
    cursor = wEnd;
  }

  return ranges;
}

function scheduleWordHighlights(durationSeconds, state) {
  clearWordTimers();
  clearWordHighlight(ocrTextViewer);

  const viewer = ocrTextViewer;
  if (!viewer) return;

  const words = state.words;
  const wordRanges = state.wordRanges;
  if (!words || words.length === 0 || !wordRanges || wordRanges.length === 0) return;

  const msPerWord = Math.max(25, (durationSeconds * 1000) / words.length);

  for (let i = 0; i < wordRanges.length; i++) {
    const r = wordRanges[i];
    if (!r) continue;

    const id = setTimeout(() => {
      highlightWordRange(viewer, r.start, r.end);
    }, Math.round(i * msPerWord));

    wordHighlightTimeouts.push(id);
  }

  // Clear word highlight at the end of the audio chunk
  wordHighlightTimeouts.push(setTimeout(() => {
    clearWordHighlight(viewer);
  }, Math.round(durationSeconds * 1000) + 30));
}

function highlightWordRange(viewer, start, end) {
  const wordRange = buildRangeFromOffsets(viewer, start, end);
  if (!wordRange) return;

  if (window.CSS && CSS.highlights && typeof Highlight !== 'undefined') {
    try {
      const highlight = new Highlight(wordRange);
      CSS.highlights.set('Mockingbird-ocr-word', highlight);
      return;
    } catch (_) {
      // fall back below
    }
  }

  // Fallback: if sentence mark exists, try to wrap word within it
  const mark = viewer.querySelector('mark[data-Mockingbird-sentence]');
  if (!mark) return;

  try {
    const localRange = wordRange.cloneRange();
    const span = document.createElement('span');
    span.setAttribute('data-Mockingbird-word', '1');
    localRange.surroundContents(span);
  } catch (_) {}
}

console.log('[Mockingbird] Side panel loaded');
