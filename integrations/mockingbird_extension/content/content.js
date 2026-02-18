/**
 * Mockingbird Browser Extension - Content Script
 * Licensed under the MIT License.
 * Copyright (c) 2026 PiperTTS Mockingbird Developers
 */

console.log('[Mockingbird] Content script loaded on', window.location.href);

let currentHighlight = null;
let lastFoundRange = null;
let currentSentenceRange = null;
let currentWordHighlights = [];
let floatingControls = null;
let persistentPlayButton = null;
let progressBar = null;
let isReaderActive = false;
let currentAudio = null;
let currentWebAudio = null;
let sharedAudioContext = null;
let autoScrollEnabled = true;
let hoverListenerEnabled = false;
let clickToListenEnabled = true;
let isHighlighting = false;
let lastHighlightWarningTime = 0;

// Initialize on page load
initialize();

function initialize() {
  // Listen for messages from background
  chrome.runtime.onMessage.addListener(handleMessage);
  
  // Create persistent play button (always visible)
  createPersistentPlayButton();
  
  // Create progress bar
  createProgressBar();
  
  // Enable click-to-listen on paragraphs
  // enableClickToListen();

  // Enable hover-to-listen
  enableHoverToSpeak();
  
  // Initialize Highlight API styles
  const style = document.createElement('style');
  style.textContent = `
    ::highlight(Mockingbird-sentence) {
      background-color: rgba(254, 240, 138, 0.5);
    }
    ::highlight(Mockingbird-word) {
      background-color: #fde047;
      color: black;
    }
  `;
  document.head.appendChild(style);

  // Load auto-scroll preference
  chrome.storage.local.get(['autoScroll'], (result) => {
    autoScrollEnabled = result.autoScroll !== false;
  });
}

// Handle text selection
function handleTextSelection(event) {
  const selection = window.getSelection();
  const selectedText = selection.toString().trim();

  if (selectedText.length > 0) {
    showFloatingButton(event.pageX, event.pageY, selectedText);
  } else {
    hideFloatingButton();
  }
}

// Create floating "Read" button
function createFloatingControls() {
  if (floatingControls) return;

  floatingControls = document.createElement('div');
  floatingControls.id = 'Mockingbird-float-btn';
  floatingControls.innerHTML = `
    <button id="Mockingbird-read-btn" title="Read selected text (Alt+A)">
      🔊 Read
    </button>
  `;
  floatingControls.style.cssText = `
    position: absolute;
    display: none;
    z-index: 999999;
    background: #2563eb;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    font-family: system-ui, -apple-system, sans-serif;
  `;

  document.body.appendChild(floatingControls);

  const readBtn = floatingControls.querySelector('#Mockingbird-read-btn');
  readBtn.addEventListener('click', () => {
    const text = window.getSelection().toString().trim();
    if (text) {
      startReading(text);
      hideFloatingButton();
    }
  });
}

// Create persistent play button (always visible in corner)
function createPersistentPlayButton() {
  if (persistentPlayButton) return;

  persistentPlayButton = document.createElement('div');
  persistentPlayButton.id = 'Mockingbird-persistent-btn';
  persistentPlayButton.innerHTML = `
    <button id="Mockingbird-play-btn" title="Read this page (Alt+A)">
      ▶
    </button>
  `;
  persistentPlayButton.style.cssText = `
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 999997;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 50%;
    width: 56px;
    height: 56px;
    box-shadow: 0 4px 20px rgba(102, 126, 234, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.3s ease;
  `;

  persistentPlayButton.addEventListener('mouseenter', () => {
    persistentPlayButton.style.transform = 'scale(1.1)';
    persistentPlayButton.style.boxShadow = '0 6px 24px rgba(102, 126, 234, 0.6)';
  });

  persistentPlayButton.addEventListener('mouseleave', () => {
    persistentPlayButton.style.transform = 'scale(1)';
    persistentPlayButton.style.boxShadow = '0 4px 20px rgba(102, 126, 234, 0.5)';
  });

  const playBtn = persistentPlayButton.querySelector('#Mockingbird-play-btn');
  playBtn.style.cssText = `
    background: transparent;
    border: none;
    color: white;
    font-size: 24px;
    width: 100%;
    height: 100%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: Arial, sans-serif;
  `;

  playBtn.addEventListener('click', () => {
    const text = getReadableText();
    if (text) {
      startReading(text);
    }
  });

  document.body.appendChild(persistentPlayButton);
}

// Create progress bar
function createProgressBar() {
  if (progressBar) return;

  progressBar = document.createElement('div');
  progressBar.id = 'Mockingbird-progress-bar';
  progressBar.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 0%;
    height: 3px;
    background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    z-index: 999999;
    transition: width 0.3s ease;
    display: none;
  `;
  document.body.appendChild(progressBar);
}

// Update progress bar
function updateProgressBar(current, total) {
  if (!progressBar) return;
  
  const percentage = total > 0 ? (current / total) * 100 : 0;
  progressBar.style.width = `${percentage}%`;
  
  if (current > 0) {
    progressBar.style.display = 'block';
  }
}

// Hide progress bar
function hideProgressBar() {
  if (progressBar) {
    progressBar.style.display = 'none';
    progressBar.style.width = '0%';
  }
}

// Update persistent button state
function updatePersistentButton(state) {
  if (!persistentPlayButton) return;

  const btn = persistentPlayButton.querySelector('#Mockingbird-play-btn');
  
  if (state === 'playing') {
    btn.textContent = '⏸';
    btn.title = 'Pause (Alt+A)';
    persistentPlayButton.style.background = 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)';
  } else if (state === 'paused') {
    btn.textContent = '▶';
    btn.title = 'Resume (Alt+A)';
    persistentPlayButton.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
  } else {
    btn.textContent = '▶';
    btn.title = 'Read this page (Alt+A)';
    persistentPlayButton.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
  }
}

// Show floating button near selection
function showFloatingButton(x, y, text) {
  if (!floatingControls) return;

  floatingControls.style.display = 'block';
  floatingControls.style.left = `${x}px`;
  floatingControls.style.top = `${y - 50}px`;
  floatingControls.dataset.selectedText = text;
}

// Hide floating button
function hideFloatingButton() {
  if (floatingControls) {
    floatingControls.style.display = 'none';
  }
}

// Handle messages from background script
function handleMessage(message, sender, sendResponse) {
  console.log('[Mockingbird] Content received:', message.action);

  switch (message.action) {
    case 'getSelectedTextFallback':
      // Try to get selected text using various methods
      getSelectedTextWithFallback().then(text => {
        sendResponse({ text });
      }).catch(err => {
        console.error('[Mockingbird] Error getting selection:', err);
        sendResponse({ text: '' });
      });
      return true; // Keep channel open for async response

    case 'getTextToRead':
      const text = getReadableText();
      sendResponse({ text });
      return false; // Sync response

    case 'playAudio':
      // Don't keep the message channel open for the entire duration of playback.
      // Send success immediately to acknowledge the command.
      // Completion/Error is handled via separate 'audioFinished'/'audioError' messages.
      playAudioData(message.audioData, message.speed, message.volume)
        .catch((error) => {
          console.error('[Mockingbird] playAudioData promise rejected:', error);
          // If the rejection wasn't handled internally, ensure we report it
          safeSendMessage({ action: 'audioError', error: error.message });
        });
      sendResponse({ success: true });
      return false; // Close channel immediately

    case 'stopAudioNow':
      // Hard-stop any in-page playback immediately.
      // sendFinished defaults to true (full stop), but skips pass false
      // to avoid a spurious audioFinished that would corrupt position tracking.
      stopCurrentPlayback({ sendFinished: message.sendFinished !== false });
      sendResponse({ success: true });
      return false; // Sync response

    case 'updateVolume':
      setPlaybackVolume(message.volume ?? 1.0);
      console.log('[Mockingbird] Volume updated to:', message.volume);
      sendResponse({ success: true });
      return false; // Sync response

    case 'readerEvent':
      handleReaderEvent(message.event, message.data);
      sendResponse({ success: true });
      return false; // Sync response
    
    case 'performOCR':
      performOCRInContent(message.imageData, message.language, message.autoRead)
        .then(() => sendResponse({ success: true }))
        .catch(error => sendResponse({ success: false, error: error.message }));
      return true; // Keep channel open for async
    
    case 'ocrStatus':
      showOCRNotification('Processing image with OCR...', 'info');
      sendResponse({ success: true });
      return false; // Sync response
    
    case 'ocrComplete':
      showOCRNotification('Text extracted successfully!', 'success');
      displayOCRResult(message.text, message.confidence);
      sendResponse({ success: true });
      return false; // Sync response
    
    case 'ocrError':
      showOCRNotification(`OCR Error: ${message.error}`, 'error');
      sendResponse({ success: true });
      return false; // Sync response

    default:
      sendResponse({ success: false, error: 'Unknown action' });
      return false; // Sync response
  }
}

let currentWordRanges = [];
let lastHighlightedIndex = -1;

function getPlaybackDurationSeconds() {
  if (currentAudio && Number.isFinite(currentAudio.duration)) return currentAudio.duration;
  if (currentWebAudio && Number.isFinite(currentWebAudio.duration)) return currentWebAudio.duration;
  return 0;
}

function stopCurrentPlayback({ sendFinished = false } = {}) {
  // HTMLAudio cleanup
  if (currentAudio) {
    try { currentAudio.pause(); } catch (_) {}
    const srcToRevoke = currentAudio?.src;
    if (srcToRevoke && srcToRevoke.startsWith('blob:')) {
      try { URL.revokeObjectURL(srcToRevoke); } catch (_) {}
    }
    currentAudio = null;
  }

  // WebAudio cleanup
  if (currentWebAudio) {
    try {
      if (currentWebAudio.rafId) cancelAnimationFrame(currentWebAudio.rafId);
    } catch (_) {}
    currentWebAudio.rafId = null;
    currentWebAudio.stopped = true;
    try {
      if (currentWebAudio.source) currentWebAudio.source.onended = null;
    } catch (_) {}
    try {
      if (currentWebAudio.source) currentWebAudio.source.stop(0);
    } catch (_) {}
    try {
      if (currentWebAudio.source) currentWebAudio.source.disconnect();
    } catch (_) {}
    try {
      if (currentWebAudio.gain) currentWebAudio.gain.disconnect();
    } catch (_) {}
    currentWebAudio = null;
  }

  if (sendFinished) {
    safeSendMessage({ action: 'audioFinished' });
  }
}

function pauseCurrentPlayback() {
  if (currentAudio) {
    try { currentAudio.pause(); } catch (_) {}
    return;
  }
  if (currentWebAudio && currentWebAudio.state === 'playing') {
    currentWebAudio.pause();
  }
}

function resumeCurrentPlayback() {
  if (currentAudio) {
    try { currentAudio.play(); } catch (_) {}
    return;
  }
  if (currentWebAudio && currentWebAudio.state === 'paused') {
    currentWebAudio.resume();
  }
}

function setPlaybackVolume(volume) {
  if (currentAudio) {
    try { currentAudio.volume = volume; } catch (_) {}
    return;
  }
  if (currentWebAudio && currentWebAudio.gain) {
    try { currentWebAudio.gain.gain.value = volume; } catch (_) {}
  }
}

// Helper to convert Base64 Data URI to Blob
function base64ToBlob(base64Data) {
  try {
    const parts = base64Data.split(';base64,');
    if (parts.length !== 2) return null;
    
    const contentType = parts[0].split(':')[1];
    const raw = window.atob(parts[1]);
    const rawLength = raw.length;
    const uInt8Array = new Uint8Array(rawLength);

    for (let i = 0; i < rawLength; ++i) {
      uInt8Array[i] = raw.charCodeAt(i);
    }

    return new Blob([uInt8Array], { type: contentType });
  } catch (e) {
    console.error('Error converting base64 to blob:', e);
    return null;
  }
}

function dataUrlToArrayBuffer(dataUrl) {
  const commaIdx = dataUrl.indexOf(',');
  const base64 = commaIdx >= 0 ? dataUrl.slice(commaIdx + 1) : dataUrl;
  const binaryString = window.atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) bytes[i] = binaryString.charCodeAt(i);
  return bytes.buffer;
}

async function getSharedAudioContext() {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) {
    throw new Error('Web Audio API not available in this page context');
  }
  if (!sharedAudioContext || sharedAudioContext.state === 'closed') {
    sharedAudioContext = new AudioCtx();
  }
  // Some sites require a resume() after a user gesture.
  if (sharedAudioContext.state === 'suspended') {
    try { await sharedAudioContext.resume(); } catch (_) {}
  }
  return sharedAudioContext;
}

function shouldFallbackToWebAudio(err) {
  const msg = (err && (err.message || String(err))) || '';
  return (
    msg.includes('URL safety check') ||
    msg.includes('Content Security Policy') ||
    msg.includes('NotSupportedError') ||
    msg.includes('no supported source')
  );
}

async function playAudioDataViaWebAudio(audioBase64, speed, volume) {
  // Stop any previous playback
  stopCurrentPlayback({ sendFinished: false });

  const ctx = await getSharedAudioContext();
  const arrayBuffer = dataUrlToArrayBuffer(audioBase64);
  const decodedBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0));

  const gain = ctx.createGain();
  gain.gain.value = volume ?? 1.0;
  gain.connect(ctx.destination);

  const state = {
    ctx,
    buffer: decodedBuffer,
    gain,
    source: null,
    playbackRate: speed ?? 1.0,
    startOffset: 0,
    startedAt: 0,
    pausedAt: 0,
    state: 'stopped',
    rafId: null,
    stopped: false
  };

  function getPositionSeconds() {
    if (state.state === 'playing') {
      const elapsed = state.ctx.currentTime - state.startedAt;
      return Math.min(state.buffer.duration, state.startOffset + elapsed * state.playbackRate);
    }
    if (state.state === 'paused') return Math.min(state.buffer.duration, state.pausedAt);
    return 0;
  }

  function startTickingForHighlights() {
    const tick = () => {
      if (!currentWebAudio || currentWebAudio !== controller) return;
      if (controller.state !== 'playing') return;

      if (window.currentSentenceWords && window.currentSentenceWords.length > 0) {
        const pos = getPositionSeconds();
        const progress = state.buffer.duration ? (pos / state.buffer.duration) : 0;
        const index = Math.min(
          Math.floor(progress * window.currentSentenceWords.length),
          window.currentSentenceWords.length - 1
        );
        if (index !== lastHighlightedIndex && index >= 0) {
          highlightWordAtIndex(index);
          lastHighlightedIndex = index;
        }
      }

      state.rafId = requestAnimationFrame(tick);
    };
    state.rafId = requestAnimationFrame(tick);
  }

  function createSourceAndStart(offsetSeconds) {
    const src = state.ctx.createBufferSource();
    src.buffer = state.buffer;
    src.playbackRate.value = state.playbackRate;
    src.connect(state.gain);
    state.source = src;
    state.startOffset = offsetSeconds;
    state.startedAt = state.ctx.currentTime;
    state.state = 'playing';
    state.stopped = false;
    src.start(0, offsetSeconds);
  }

  const controller = {
    type: 'webaudio',
    gain,
    duration: state.buffer.duration,
    get state() { return state.state; },
    pause() {
      if (state.state !== 'playing') return;
      state.pausedAt = getPositionSeconds();
      state.state = 'paused';
      try { if (state.rafId) cancelAnimationFrame(state.rafId); } catch (_) {}
      state.rafId = null;
      try {
        if (state.source) {
          state.source.onended = null;
          state.source.stop(0);
          state.source.disconnect();
        }
      } catch (_) {}
      state.source = null;
    },
    resume() {
      if (state.state !== 'paused') return;
      createSourceAndStart(state.pausedAt);
      startTickingForHighlights();
    },
    stop() {
      state.stopped = true;
      state.state = 'stopped';
      try { if (state.rafId) cancelAnimationFrame(state.rafId); } catch (_) {}
      state.rafId = null;
      try {
        if (state.source) {
          state.source.onended = null;
          state.source.stop(0);
          state.source.disconnect();
        }
      } catch (_) {}
      state.source = null;
      try { state.gain.disconnect(); } catch (_) {}
    }
  };

  currentWebAudio = controller;

  // Duration needs to reflect playbackRate for background timing.
  const effectiveDuration = state.buffer.duration / state.playbackRate;
  safeSendMessage({ action: 'audioDuration', duration: effectiveDuration });
  if (window.currentSentenceWords && window.currentSentenceWords.length > 0) {
    startWordHighlighting(window.currentSentenceWords, effectiveDuration, window.currentHighlightElement);
  }

  return new Promise((resolve, reject) => {
    try {
      createSourceAndStart(0);
      state.source.onended = () => {
        // If we were stopped (pause/stop), don't treat as completion.
        if (!currentWebAudio || currentWebAudio !== controller) return;
        if (state.stopped || state.state !== 'playing') return;

        stopCurrentPlayback({ sendFinished: true });
        resolve();
      };

      startTickingForHighlights();
    } catch (e) {
      stopCurrentPlayback({ sendFinished: false });
      safeSendMessage({ action: 'audioError', error: e?.message || String(e) });
      reject(e);
    }
  });
}

// Play audio data (base64 encoded)
function playAudioData(audioBase64, speed, volume) {
  return new Promise((resolve, reject) => {
    console.log('[Mockingbird] playAudioData called with:', {
      dataLength: audioBase64?.length,
      dataPrefix: audioBase64?.substring(0, 50),
      speed,
      volume
    });
    
    // Clean up previous playback (HTMLAudio or WebAudio)
    stopCurrentPlayback({ sendFinished: false });

    // Try to use Blob URL to bypass CSP data: limitations
    const blob = base64ToBlob(audioBase64);
    console.log('[Mockingbird] Blob conversion result:', blob);
    
    let createdBlobUrl = null;
    if (blob) {
      createdBlobUrl = URL.createObjectURL(blob);
      console.log('[Mockingbird] Created blob URL:', createdBlobUrl);
      currentAudio = new Audio(createdBlobUrl);
    } else {
      console.log('[Mockingbird] Fallback to data URL');
      // Fallback to original if blob conversion fails
      currentAudio = new Audio(audioBase64);
    }

    currentAudio.playbackRate = speed ?? 1.0;
    currentAudio.volume = volume ?? 1.0;

    // Once metadata is loaded, we can get the duration
    currentAudio.onloadedmetadata = () => {
      if (!currentAudio) return; // Guard against null
      const duration = currentAudio.duration / currentAudio.playbackRate;
      
      // Send duration to background for progress tracking
      safeSendMessage({ 
        action: 'audioDuration', 
        duration: duration 
      });
      
      // Notify that we have the duration (for word highlighting)
      if (window.currentSentenceWords && window.currentSentenceWords.length > 0) {
        startWordHighlighting(window.currentSentenceWords, duration, window.currentHighlightElement);
      }
    };

    currentAudio.ontimeupdate = () => {
       if (!currentAudio || !window.currentSentenceWords || window.currentSentenceWords.length === 0) return;
       
       const duration = currentAudio.duration;
       if (!duration) return;
       
       const progress = currentAudio.currentTime / duration;
       const index = Math.min(
           Math.floor(progress * window.currentSentenceWords.length), 
           window.currentSentenceWords.length - 1
       );
       
       if (index !== lastHighlightedIndex && index >= 0) {
           highlightWordAtIndex(index);
           lastHighlightedIndex = index;
       }
    };


    currentAudio.onended = () => {
      if (currentAudio && currentAudio.src && currentAudio.src.startsWith('blob:')) {
        URL.revokeObjectURL(currentAudio.src);
      }
      currentAudio = null;
      // Notify background that audio finished
      safeSendMessage({ action: 'audioFinished' });
      resolve();
    };

    currentAudio.onerror = (event) => {
      console.error('[Mockingbird] Audio error event:', event);
      console.error('[Mockingbird] Audio error details:', {
        error: currentAudio?.error,
        code: currentAudio?.error?.code,
        message: currentAudio?.error?.message,
        src: currentAudio?.src,
        readyState: currentAudio?.readyState,
        networkState: currentAudio?.networkState
      });
      
      const errorMsg = currentAudio?.error ?
        `Media error code ${currentAudio.error.code}: ${currentAudio.error.message}` :
        'Audio playback error';
      
      const srcToRevoke = currentAudio?.src;
      if (srcToRevoke && srcToRevoke.startsWith('blob:')) {
        URL.revokeObjectURL(srcToRevoke);
      }
      currentAudio = null;
      
      // On CSP-heavy sites, blob:/data: playback can be blocked. Fall back to WebAudio.
      const errorObj = Object.assign(new Error(errorMsg), { code: currentAudio?.error?.code, src: currentAudio?.src });
      if (shouldFallbackToWebAudio(errorObj)) {
        console.warn('[Mockingbird] Falling back to WebAudio due to playback error:', errorMsg);
        playAudioDataViaWebAudio(audioBase64, speed, volume)
          .then(resolve)
          .catch(reject);
        return;
      }

      // Notify background of error
      safeSendMessage({
        action: 'audioError',
        error: errorMsg
      });
      reject(errorObj);
    };

    // Try to play the audio
    currentAudio.play().catch((error) => {
      console.error('[Mockingbird] Play error:', error);
      
      let errMsg = 'Failed to start audio playback';
      if (error) {
         errMsg = error.message || String(error);
      } else {
         errMsg = 'Unknown playback error (undefined)';
      }
      
      const errorObj = new Error(errMsg);

      if (currentAudio && currentAudio.src && currentAudio.src.startsWith('blob:')) {
        try { URL.revokeObjectURL(currentAudio.src); } catch (_) {}
      }
      currentAudio = null;

      if (shouldFallbackToWebAudio(errorObj)) {
        console.warn('[Mockingbird] Falling back to WebAudio due to play() rejection:', errMsg);
        playAudioDataViaWebAudio(audioBase64, speed, volume)
          .then(resolve)
          .catch(reject);
        return;
      }

      safeSendMessage({
        action: 'audioError',
        error: errMsg
      });
      reject(errorObj);
    });
  });
}

// Get selected text with fallback for Google Docs and other sites
async function getSelectedTextWithFallback() {
  // Try standard window.getSelection() first
  let selection = window.getSelection().toString().trim();
  if (selection.length > 0) {
    return selection;
  }

  // For Google Docs, try accessing the iframe directly
  if (window.location.hostname.includes('docs.google.com')) {
    try {
      // Try to access the Google Docs iframe
      const iframe = document.querySelector('.docs-texteventtarget-iframe');
      if (iframe && iframe.contentDocument) {
        const iframeSelection = iframe.contentDocument.getSelection();
        if (iframeSelection) {
          const iframeText = iframeSelection.toString().trim();
          if (iframeText.length > 0) {
            console.log('[Mockingbird] Got text from Google Docs iframe selection');
            return iframeText;
          }
        }
      }
    } catch (err) {
      console.warn('[Mockingbird] Iframe access failed:', err);
    }

    // Fallback to clipboard method
    try {
      // Try to copy selection to clipboard
      document.execCommand('copy');
      
      // Read from clipboard
      const clipboardText = await navigator.clipboard.readText();
      if (clipboardText && clipboardText.trim().length > 0) {
        console.log('[Mockingbird] Got text from clipboard for Google Docs');
        return clipboardText.trim();
      }
    } catch (err) {
      console.warn('[Mockingbird] Clipboard fallback failed:', err);
    }
  }

  return '';
}

// Get readable text from page
function getReadableText() {
  // First check if there's selected text
  const selection = window.getSelection().toString().trim();
  if (selection.length > 0) {
    return selection;
  }

  // Otherwise, extract main content from page
  return extractMainContent();
}

// Extract main content from webpage with smart site detection
function extractMainContent() {
  const hostname = window.location.hostname;
  const pathname = window.location.pathname;
  
  // Google Docs special handling
  if (hostname.includes('docs.google.com') && pathname.includes('/document/')) {
    return extractGoogleDocsContent();
  }
  
  // Wikipedia special handling
  if (hostname.includes('wikipedia.org')) {
    return extractWikipediaContent();
  }
  
  // Reddit special handling
  if (hostname.includes('reddit.com')) {
    return extractRedditContent();
  }
  
  // Medium special handling
  if (hostname.includes('medium.com')) {
    return extractMediumContent();
  }
  
  // Twitter/X special handling
  if (hostname.includes('twitter.com') || hostname.includes('x.com')) {
    return extractTwitterContent();
  }
  
  // LinkedIn special handling
  if (hostname.includes('linkedin.com')) {
    return extractLinkedInContent();
  }
  
  // Substack special handling
  if (hostname.includes('substack.com')) {
    return extractSubstackContent();
  }
  
  // GitHub special handling
  if (hostname.includes('github.com')) {
    return extractGitHubContent();
  }
  
  // PDF detection
  if (pathname.toLowerCase().endsWith('.pdf') || document.querySelector('embed[type="application/pdf"]')) {
    return extractPDFContent();
  }
  
  // Standard content extraction
  return extractStandardContent();
}

// Extract content from Google Docs
function extractGoogleDocsContent() {
  // Try to find all line views which contain the text
  const lines = document.querySelectorAll('.kix-lineview');
  if (lines.length > 0) {
    let text = '';
    lines.forEach(line => {
      text += line.innerText + ' ';
    });
    return text.trim();
  }

  // Fallback to the paginated document plugin
  const docContent = document.querySelector('.kix-paginateddocumentplugin');
  if (docContent) {
    return extractTextFromElement(docContent);
  }
  return extractStandardContent();
}

// Extract content from Wikipedia
function extractWikipediaContent() {
  const content = document.querySelector('#mw-content-text .mw-parser-output');
  if (content) {
    const clone = content.cloneNode(true);
    // Remove reference links, nav boxes, info boxes, hatnotes, and image figures.
    // Hatnotes are the "Further information: X § Y" cross-reference blocks.
    // Figures/thumbs are image thumbnails with captions — their text can't be
    // matched back to the DOM for highlighting and causes the reader to hang.
    clone.querySelectorAll(
      '.reference, .navbox, .infobox, .mw-editsection, .toc, .hatnote, ' +
      'figure, .thumb, .thumbinner, .thumbcaption, figcaption, ' +
      '.mw-halign-none, .mw-halign-right, .mw-halign-left, .mw-halign-center, ' +
      '.gallery, .gallerytable, .mw-gallery-traditional'
    ).forEach(el => el.remove());
    return extractTextFromElement(clone);
  }
  return extractStandardContent();
}

// Extract content from Reddit
function extractRedditContent() {
  // Try new Reddit first
  let post = document.querySelector('[data-test-id="post-content"]');
  if (post) {
    return extractTextFromElement(post);
  }
  
  // Try old Reddit
  post = document.querySelector('.usertext-body');
  if (post) {
    return extractTextFromElement(post);
  }
  
  return extractStandardContent();
}

// Extract content from Medium
function extractMediumContent() {
  const article = document.querySelector('article');
  if (article) {
    return extractTextFromElement(article);
  }
  return extractStandardContent();
}

// Extract content from Twitter/X
function extractTwitterContent() {
  // Try to get a single tweet
  const tweet = document.querySelector('article[data-testid="tweet"]');
  if (tweet) {
    const tweetText = tweet.querySelector('[data-testid="tweetText"]');
    if (tweetText) {
      return extractTextFromElement(tweetText);
    }
  }
  
  // Try to get thread
  const tweets = document.querySelectorAll('article[data-testid="tweet"]');
  if (tweets.length > 0) {
    return Array.from(tweets)
      .map(t => {
        const text = t.querySelector('[data-testid="tweetText"]');
        return text ? text.textContent.trim() : '';
      })
      .filter(t => t.length > 0)
      .join('\n\n');
  }
  
  return extractStandardContent();
}

// Extract content from LinkedIn
function extractLinkedInContent() {
  // LinkedIn post
  const post = document.querySelector('.feed-shared-update-v2__description');
  if (post) {
    return extractTextFromElement(post);
  }
  
  // LinkedIn article
  const article = document.querySelector('.article-content');
  if (article) {
    return extractTextFromElement(article);
  }
  
  return extractStandardContent();
}

// Extract content from Substack
function extractSubstackContent() {
  const article = document.querySelector('.post-content') || 
                  document.querySelector('.single-post-content') ||
                  document.querySelector('article');
  if (article) {
    return extractTextFromElement(article);
  }
  return extractStandardContent();
}

// Extract content from GitHub
function extractGitHubContent() {
  // README file
  const readme = document.querySelector('article.markdown-body');
  if (readme) {
    return extractTextFromElement(readme);
  }
  
  // Issue or PR description
  const issue = document.querySelector('.comment-body');
  if (issue) {
    return extractTextFromElement(issue);
  }
  
  return extractStandardContent();
}

// Extract content from PDF (basic)
function extractPDFContent() {
  // Try to get text from PDF viewer
  const pdfText = document.querySelector('#viewer .textLayer');
  if (pdfText) {
    return extractTextFromElement(pdfText);
  }
  
  // Fallback message
  return 'PDF detected. Text extraction from PDFs is limited. For best results, try opening the PDF in a dedicated viewer.';
}

// Standard content extraction
function extractStandardContent() {
  // Try to find main content container with expanded selectors
  const contentSelectors = [
    'article',
    'main',
    '[role="main"]',
    '[role="article"]',
    '.content',
    '.post-content',
    '.article-content',
    '.article-body',
    '.post-body',
    '.entry-content',
    '.page-content',
    '.story-body',
    '.article__body',
    '#content',
    '#main-content',
    '.main-content',
    '.body-content',
    // News sites
    '.article__content',
    '.story__content',
    // Blog platforms
    '.post__content',
    '.blog-post-content',
    // Documentation sites
    '.documentation-content',
    '.doc-content'
  ];

  for (const selector of contentSelectors) {
    const element = document.querySelector(selector);
    if (element && hasSignificantContent(element)) {
      return extractTextFromElement(element);
    }
  }

  // Fallback: get all text from body, excluding scripts and styles
  return extractTextFromElement(document.body);
}

// Check if element has significant readable content
function hasSignificantContent(element) {
  const text = element.innerText || element.textContent || '';
  const wordCount = text.trim().split(/\s+/).length;
  return wordCount > 50; // At least 50 words to be considered significant
}

// Extract clean text from element
function extractTextFromElement(element) {
  // Clone to avoid modifying the actual DOM
  const clone = element.cloneNode(true);

  // Remove unwanted elements with expanded list
  const unwantedSelectors = [
    'script',
    'style',
    'nav',
    'header',
    'footer',
    'aside',
    'iframe',
    'noscript',
    // Ads and tracking
    '.ad',
    '.ads',
    '.advertisement',
    '.adsbygoogle',
    '[id*="ad-"]',
    '[class*="ad-"]',
    // Social and sharing
    '.social-share',
    '.share-buttons',
    '.social-buttons',
    // Navigation
    '.sidebar',
    '.menu',
    '.navigation',
    '.nav',
    '.breadcrumb',
    '.breadcrumbs',
    // Comments
    '.comments',
    '.comment',
    '.comment-section',
    '#comments',
    // Related content
    '.related',
    '.recommended',
    '.related-posts',
    '.recommendations',
    // Popups and overlays
    '.popup',
    '.modal',
    '.overlay',
    '.newsletter',
    '.subscription',
    // Cookie notices
    '.cookie-notice',
    '.cookie-banner',
    // Toolbars and controls
    '.toolbar',
    '.controls',
    '.player-controls'
  ];

  unwantedSelectors.forEach(selector => {
    clone.querySelectorAll(selector).forEach(el => el.remove());
  });
  
  // Remove hidden elements
  clone.querySelectorAll('[style*="display: none"], [style*="display:none"], [hidden], .hidden').forEach(el => el.remove());

  // Get text content
  let text = clone.innerText || clone.textContent || '';
  
  // Clean up whitespace
  text = text
    .replace(/\s+/g, ' ')
    .replace(/\n\s*\n/g, '\n')
    .trim();

  return text;
}

// Handle reader events from background
function handleReaderEvent(event, data) {
  console.log('[Mockingbird] Reader event:', event, data);

  switch (event) {
    case 'readingStarted':
      isReaderActive = true;
      showReaderOverlay();
      updatePersistentButton('playing');
      break;

    case 'sentenceStart':
      highlightSentenceWordByWord(data.text, data.words, data.index, data.total);
      break;

    case 'speedChanged':
      showSpeedNotification(data.speed);
      break;

    case 'paused':
      pauseCurrentPlayback();
      updateOverlayStatus('Paused');
      updatePersistentButton('paused');
      break;

    case 'resumed':
      resumeCurrentPlayback();
      updateOverlayStatus('Reading...');
      updatePersistentButton('playing');
      break;

    case 'stopped':
    case 'readingComplete':
      // Notify background to unblock waiting promise
      stopCurrentPlayback({ sendFinished: true });
      isReaderActive = false;
      hideReaderOverlay();
      clearHighlight();
      clearWordHighlights();
      hideProgressBar();
      updatePersistentButton('stopped');
      lastFoundRange = null; // Reset search position
      break;

    case 'error':
      showError(data.message);
      updatePersistentButton('stopped');
      break;
    
    case 'notification':
      showNotification(data.message, data.type, data.duration);
      break;
  }
}

// Show reader overlay with controls
function showReaderOverlay() {
  let overlay = document.getElementById('Mockingbird-overlay');
  
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'Mockingbird-overlay';
    overlay.innerHTML = `
      <div class="Mockingbird-controls">
        <div class="Mockingbird-status">Reading...</div>
        <div class="Mockingbird-buttons">
          <button id="Mockingbird-prev" title="Previous sentence">⏮</button>
          <button id="Mockingbird-pause" title="Pause (Alt+A)">⏸</button>
          <button id="Mockingbird-next" title="Next sentence">⏭</button>
          <button id="Mockingbird-stop" title="Stop (Alt+S)">⏹</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    // Add event listeners with debouncing to prevent rapid-fire clicks
    overlay.querySelector('#Mockingbird-prev').addEventListener('click', () => {
      debounce('skipBackward', () => {
        safeSendMessage({ action: 'skipBackward' });
      }, 250);
    });

    overlay.querySelector('#Mockingbird-pause').addEventListener('click', () => {
      safeSendMessage({ action: 'togglePlayPause' });
    });

    overlay.querySelector('#Mockingbird-next').addEventListener('click', () => {
      debounce('skipForward', () => {
        safeSendMessage({ action: 'skipForward' });
      }, 250);
    });

    overlay.querySelector('#Mockingbird-stop').addEventListener('click', () => {
      safeSendMessage({ action: 'stopReading' });
    });
  }

  overlay.style.display = 'block';
}

// Hide reader overlay
function hideReaderOverlay() {
  const overlay = document.getElementById('Mockingbird-overlay');
  if (overlay) {
    overlay.style.display = 'none';
  }
}

// Update overlay status text
function updateOverlayStatus(status) {
  const overlay = document.getElementById('Mockingbird-overlay');
  if (overlay) {
    const statusEl = overlay.querySelector('.Mockingbird-status');
    if (statusEl) {
      statusEl.textContent = status;
    }
  }
}

// Highlight current sentence word-by-word
// Highlight current sentence word-by-word
function highlightSentenceWordByWord(text, words, index, total) {
  // Prevent overlapping highlight operations
  if (isHighlighting) {
    return;
  }
  isHighlighting = true;

  clearHighlight();
  clearWordHighlights();
  updateProgressBar(index, total);
  
  // Reset search position to ensure we always search from the beginning
  // This is crucial for both forward and backward navigation
  lastFoundRange = null;

  console.log('[Mockingbird] Highlighting sentence:', text.substring(0, 50));

  // Find the sentence text in the page
  const sentenceRange = findTextInPage(text);
  
  if (sentenceRange) {
    // 1. Highlight Sentence
    if (window.CSS && CSS.highlights) {
      const highlight = new Highlight(sentenceRange);
      CSS.highlights.set('Mockingbird-sentence', highlight);
      currentSentenceRange = sentenceRange;
    } else {
      // Fallback highlighting
      try {
        const container = sentenceRange.commonAncestorContainer;
        const element = container.nodeType === Node.TEXT_NODE ? container.parentElement : container;
        if (element) {
           element.style.backgroundColor = 'rgba(254, 240, 138, 0.3)';
           currentHighlight = element;
        }
      } catch (e) {}
    }
    
    // 2. Scroll into view
    try {
        const element = sentenceRange.commonAncestorContainer.nodeType === Node.ELEMENT_NODE 
            ? sentenceRange.commonAncestorContainer 
            : sentenceRange.commonAncestorContainer.parentElement;
        if (element && autoScrollEnabled) {
            element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    } catch(e) {}
      
    // Store words for word highlighting
    window.currentSentenceWords = words;
  } else {
    // Suppress excessive warnings (max one per second)
    const now = Date.now();
    if (now - lastHighlightWarningTime > 1000) {
      console.warn('[Mockingbird] Could not find text in page:', text.substring(0, 50) + '...');
      lastHighlightWarningTime = now;
    }
    currentSentenceRange = null; 
    window.currentSentenceWords = null;
    // Reset search position for next attempt
    lastFoundRange = null;
  }

  updateOverlayStatus(`Reading ${index + 1} of ${total}...`);
  isHighlighting = false;
}

// Simple fallback highlighting (legacy)
function highlightSimple(text) {
  // Kept for compatibility but logic moved to highlightSentenceWordByWord
}

// Prepare word highlighting
function startWordHighlighting(words, audioDuration, element) {
  clearWordHighlights(); // Ensure clean slate
  lastHighlightedIndex = -1;
  currentWordRanges = [];
  
  if (!words || words.length === 0) return;
  
  // Pre-calculate ranges if using CSS Custom Highlight API
  if (window.CSS && CSS.highlights && currentSentenceRange) {
     const selection = window.getSelection();
     selection.removeAllRanges();
     selection.addRange(currentSentenceRange);
     selection.collapseToStart();
     
     // Try to find each word in the sentence range
     // Note: This assumes words in array match text exactly.
     // Since text was extracted and then split, it should match.
     
     words.forEach((word) => {
         // Search for the word within the range context (implicitly done by collapsing)
         // We rely on window.find searching forward
         try {
             const found = window.find(word, false, false, true, false, false, false);
             if (found) {
                // Check if found range is within or overlaps sentence range?
                // For now assuming sequential find works relative to start
                const range = selection.getRangeAt(0);
                
                // Ensure the found range is actually inside our target sentence
                // (Simple check: is it after the end?)
                if (range.compareBoundaryPoints(Range.START_TO_START, currentSentenceRange) >= 0 &&
                    range.compareBoundaryPoints(Range.END_TO_END, currentSentenceRange) <= 0) {
                     currentWordRanges.push(range.cloneRange());
                } else {
                     currentWordRanges.push(null);
                }
                selection.collapseToEnd();
             } else {
                currentWordRanges.push(null);
             }
         } catch(e) {
             currentWordRanges.push(null);
         }
     });

     selection.removeAllRanges();
  }
}

function highlightWordAtIndex(index) {
    if (window.CSS && CSS.highlights && currentWordRanges[index]) {
        const highlight = new Highlight(currentWordRanges[index]);
        CSS.highlights.set('Mockingbird-word', highlight);
    } else if (window.currentHighlightElement) {
        // Fallback for element based highlighting
        const words = window.currentSentenceWords;
    const durationSeconds = getPlaybackDurationSeconds();
    const msPerWord = durationSeconds ? ((durationSeconds * 1000) / words.length) : 120;
        // Just flash the element if precise word finding failed
        if (window.currentHighlightElement.style) {
             window.currentHighlightElement.style.backgroundColor = '#fde047';
             setTimeout(() => {
                 if (window.currentHighlightElement && window.currentHighlightElement.style) 
                    window.currentHighlightElement.style.backgroundColor = 'rgba(254, 240, 138, 0.3)';
             }, msPerWord * 0.9);
        }
    }
}

// Clear word highlights
function clearWordHighlights() {
  if (window.CSS && CSS.highlights) {
    CSS.highlights.delete('Mockingbird-word');
  }
  currentWordHighlights = [];
  lastHighlightedIndex = -1;
}

// Show speed change notification
function showSpeedNotification(speed) {
  const notification = document.createElement('div');
  notification.id = 'Mockingbird-speed-notification';
  notification.textContent = `Speed: ${speed.toFixed(1)}x`;
  notification.style.cssText = `
    position: fixed;
    top: 60px;
    right: 20px;
    background: rgba(102, 126, 234, 0.95);
    color: white;
    padding: 12px 20px;
    border-radius: 8px;
    z-index: 1000001;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    font-family: system-ui, -apple-system, sans-serif;
    font-size: 16px;
    font-weight: 600;
    animation: Mockingbird-slide-in 0.3s ease-out;
  `;
  document.body.appendChild(notification);

  setTimeout(() => {
    notification.style.opacity = '0';
    notification.style.transition = 'opacity 0.3s ease';
    setTimeout(() => notification.remove(), 300);
  }, 1500);
}

// Find text in page using window.find for robustness
function findTextInPage(searchText) {
  if (!searchText) return null;
  const selection = window.getSelection();

  // Try to find `query` string using window.find(), returning a cloned Range or null.
  function tryFind(query) {
    try {
      selection.removeAllRanges();
      const r = document.createRange();
      r.selectNodeContents(document.body);
      r.collapse(true);
      selection.addRange(r);
      const found = window.find(query, false, false, true, false, false, false);
      if (found) {
        const cloned = selection.getRangeAt(0).cloneRange();
        selection.removeAllRanges();
        return cloned;
      }
      selection.removeAllRanges();
    } catch (e) {
      try { selection.removeAllRanges(); } catch (_) {}
    }
    return null;
  }

  try {
    const trimmed = searchText.trim();

    // 1. Exact match first.
    const exact = tryFind(trimmed);
    if (exact) return exact;

    // 2. Fuzzy fallback: progressively shorten from the end in 10-char steps,
    //    stopping at 30 characters to avoid false positives on short strings.
    const MIN_LENGTH = 30;
    if (trimmed.length > MIN_LENGTH) {
      // Work down from 90 % of length to MIN_LENGTH.
      let len = Math.floor(trimmed.length * 0.9);
      while (len >= MIN_LENGTH) {
        const partial = tryFind(trimmed.substring(0, len).trim());
        if (partial) {
          console.log(`[Mockingbird] Fuzzy match at length ${len} for: ${trimmed.substring(0, 40)}...`);
          return partial;
        }
        len -= 10;
      }
    }
  } catch (e) {
    console.warn('[Mockingbird] Error in findTextInPage:', e);
    try { selection.removeAllRanges(); } catch (_) {}
  }

  return null;
}



// Clear current highlight
function clearHighlight() {
  if (window.CSS && CSS.highlights) {
     CSS.highlights.delete('Mockingbird-sentence');
  }

  if (currentHighlight) {
    try {
      // Reset styles instead of replacing DOM nodes
      if (currentHighlight.style) {
        currentHighlight.style.backgroundColor = '';
        currentHighlight.style.transition = '';
        currentHighlight.style.borderRadius = '';
        currentHighlight.style.boxShadow = '';
      }
    } catch (e) {
      console.warn('[Mockingbird] Error clearing highlight:', e);
    }
    currentHighlight = null;
  }
}

// Show error message
function showError(message) {
  const errorDiv = document.createElement('div');
  errorDiv.id = 'Mockingbird-error';
  errorDiv.textContent = `Mockingbird Error: ${message}`;
  errorDiv.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: #dc2626;
    color: white;
    padding: 16px 24px;
    border-radius: 8px;
    z-index: 1000000;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    font-family: system-ui, -apple-system, sans-serif;
    font-size: 14px;
  `;
  document.body.appendChild(errorDiv);

  setTimeout(() => {
    errorDiv.remove();
  }, 5000);
}

// Safe wrapper for extension communication
function safeSendMessage(message, callback) {
  try {
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        // Just log it, don't alert for every background pulse check
        console.warn('[Mockingbird] Runtime error:', chrome.runtime.lastError.message);
      }
      if (callback) callback(response);
    });
  } catch (error) {
    console.error('[Mockingbird] SendMessage failed:', error);
    if (error.message.includes('Extension context invalidated')) {
      showContextInvalidatedAlert();
    }
  }
}

let contextAlertShown = false;

// Debounce utility for rapid button clicks
const debounceTimers = {};
function debounce(key, func, delay = 300) {
  if (debounceTimers[key]) {
    return; // Skip if already pending
  }
  debounceTimers[key] = setTimeout(() => {
    delete debounceTimers[key];
  }, delay);
  func();
}

function showContextInvalidatedAlert() {
  if (contextAlertShown) return;
  contextAlertShown = true;
  alert('Mockingbird extension has been updated.\n\nPlease refresh this page to reconnect.');
}

// Start reading text
function startReading(text) {
  safeSendMessage({
    action: 'startReading',
    text: text
  });
}

// Enable click-to-listen on paragraphs
function enableClickToListen() {
  if (!clickToListenEnabled) return;
  
  // Add click listeners to all paragraph-like elements
  const readableSelectors = 'p, h1, h2, h3, h4, h5, h6, li, blockquote, article > div';
  
  document.addEventListener('click', (e) => {
    if (!clickToListenEnabled) return;
    
    // Check if clicked element or parent matches readable selectors
    const target = e.target.closest(readableSelectors);
    
    if (target && !e.target.closest('a, button, input, textarea, select')) {
      // Get text from clicked element forward
      const text = getTextFromElement(target);
      
      if (text.trim().length > 10) {
        e.stopPropagation();
        
        // Add visual feedback
        target.style.transition = 'background-color 0.3s';
        target.style.backgroundColor = 'rgba(102, 126, 234, 0.1)';
        setTimeout(() => {
          target.style.backgroundColor = '';
        }, 300);
        
        startReading(text);
      }
    }
  }, true);
}

// Get text starting from a specific element
function getTextFromElement(startElement) {
  const contentContainer = findMainContentContainer();
  
  if (!contentContainer.contains(startElement)) {
    return extractTextFromElement(startElement);
  }
  
  // Get all paragraph elements from start to end
  const allElements = Array.from(contentContainer.querySelectorAll('p, h1, h2, h3, h4, h5, h6, li, blockquote'));
  const startIndex = allElements.indexOf(startElement);
  
  if (startIndex === -1) {
    return extractTextFromElement(startElement);
  }
  
  // Collect text from this point forward
  const elementsToRead = allElements.slice(startIndex);
  return elementsToRead.map(el => el.textContent.trim()).filter(t => t.length > 0).join(' ');
}

// Find main content container
function findMainContentContainer() {
  const contentSelectors = [
    'article',
    'main',
    '[role="main"]',
    '.content',
    '.post-content',
    '.article-content'
  ];
  
  for (const selector of contentSelectors) {
    const element = document.querySelector(selector);
    if (element) return element;
  }
  
  return document.body;
}

// Show notification with type styling
function showNotification(message, type = 'info', duration = 3000) {
  const notification = document.createElement('div');
  notification.className = 'Mockingbird-notification';
  notification.textContent = message;
  
  // Determine color based on type
  let gradientColor;
  switch (type) {
    case 'success':
      gradientColor = 'linear-gradient(135deg, #10b981 0%, #059669 100%)';
      break;
    case 'error':
      gradientColor = 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)';
      break;
    case 'warning':
      gradientColor = 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)';
      break;
    default: // info
      gradientColor = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
  }
  
  notification.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    background: ${gradientColor};
    color: white;
    padding: 12px 24px;
    border-radius: 8px;
    z-index: 1000001;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    font-family: system-ui, -apple-system, sans-serif;
    font-size: 14px;
    font-weight: 600;
    animation: slideInRight 0.3s ease-out;
    max-width: 400px;
    word-wrap: break-word;
  `;
  document.body.appendChild(notification);

  setTimeout(() => {
    notification.style.opacity = '0';
    notification.style.transition = 'opacity 0.3s ease';
    setTimeout(() => notification.remove(), 300);
  }, duration);
}

console.log('[Mockingbird] Content script ready');

// Enable hover-to-listen functionality
function enableHoverToSpeak() {
  if (document.getElementById('Mockingbird-hover-btn')) return;

  // Create the hover button
  const hoverBtn = document.createElement('div');
  hoverBtn.id = 'Mockingbird-hover-btn';
  hoverBtn.innerHTML = `
    <button title="Read this block">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M8 5V19L19 12L8 5Z" fill="#4F46E5" stroke="none"/>
      </svg>
    </button>
  `;
  hoverBtn.style.cssText = `
    position: absolute;
    display: none;
    z-index: 2147483647; /* Max z-index */
    background: white;
    border-radius: 50%;
    width: 36px;
    height: 36px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    cursor: pointer;
    align-items: center;
    justify-content: center;
    transition: opacity 0.2s, transform 0.2s, top 0.1s, left 0.1s;
    pointer-events: auto;
  `;
  
  const innerBtn = hoverBtn.querySelector('button');
  innerBtn.style.cssText = `
    background: transparent;
    border: none;
    padding: 0;
    margin: 0;
    width: 100%;
    height: 100%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
  `;
  
  // Hover effect for the button itself
  innerBtn.addEventListener('mouseenter', () => {
    hoverBtn.style.transform = 'scale(1.1)';
    hoverBtn.style.backgroundColor = '#EEF2FF';
  });
  innerBtn.addEventListener('mouseleave', () => {
    hoverBtn.style.transform = 'scale(1)';
    hoverBtn.style.backgroundColor = 'white';
  });

  document.body.appendChild(hoverBtn);

  let currentTarget = null;
  let hideTimeout = null;
  let isHoveringButton = false;

  // Track if mouse is on the button
  hoverBtn.addEventListener('mouseenter', () => {
    isHoveringButton = true;
    if (hideTimeout) clearTimeout(hideTimeout);
  });
  
  hoverBtn.addEventListener('mouseleave', () => {
    isHoveringButton = false;
    // Hide if we leave the button and aren't on the target
    hideTimeout = setTimeout(() => {
        if (!isHoveringButton) {
            hoverBtn.style.display = 'none';
        }
    }, 300);
  });

  // Decide if an element is worth reading
  const isValidTarget = (el) => {
    if (!el || !el.tagName) return false;
    const tag = el.tagName.toLowerCase();
    
    // Must be a block text element
    if (!['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote', 'article', 'section'].includes(tag)) return false;
    
    // Check text content length (at least 5 words to be worth reading)
    const text = el.textContent.trim();
    if (!text || text.split(/\s+/).length < 5) return false;
    
    // Exclude interactive elements
    if (el.closest('a, button, form, input, textarea, [role="button"]')) return false;

    // Exclude our own UI
    if (el.closest('#Mockingbird-hover-btn') || el.closest('#Mockingbird-float-btn') || el.closest('#Mockingbird-persistent-btn')) return false;
    
    return true;
  };

  // Main mouseover listener
  document.addEventListener('mouseover', (e) => {
    const target = e.target;
    
    if (isHoveringButton) return;

    // Use closest to find the container block if hovering a span or partial text
    const blockTarget = target.closest && target.closest('p, h1, h2, h3, h4, h5, h6, li, blockquote');
    
    if (blockTarget && isValidTarget(blockTarget)) {
      if (hideTimeout) clearTimeout(hideTimeout);
      
      // Don't move if we are already showing for this element (prevents jitter)
      if (currentTarget === blockTarget && hoverBtn.style.display !== 'none') return;
      
      currentTarget = blockTarget;
      
      const rect = blockTarget.getBoundingClientRect();
      const scrollTop = window.scrollY || document.documentElement.scrollTop;
      const scrollLeft = window.scrollX || document.documentElement.scrollLeft;

      // Position: Vertically centered on the first line approx, and to the left
      // We aim for left margin.
      let leftPos = rect.left + scrollLeft - 45;
      
      // If element is at the very edge, put it inside/overlay
      if (rect.left < 50) {
         leftPos = rect.left + scrollLeft + 5;
      }
      
      hoverBtn.style.top = `${rect.top + scrollTop - 5}px`; 
      hoverBtn.style.left = `${leftPos}px`;
      hoverBtn.style.display = 'flex';
      
    } else if (!hoverBtn.contains(target)) {
      // If hovering something invalid (like empty space), start hide timer
       if (!hideTimeout) {
          hideTimeout = setTimeout(() => {
              if (!isHoveringButton) {
                  hoverBtn.style.display = 'none';
                  currentTarget = null;
              }
          }, 300);
       }
    }
  });
  
  // Play action
  innerBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (currentTarget) {
        startReading(currentTarget.innerText);
    }
  });
}

// ===== OCR Functions =====
let tesseractLoaded = false;
let tesseractWorker = null;

async function loadTesseract() {
  if (tesseractLoaded) return true;
  
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js';
    script.onload = () => {
      tesseractLoaded = true;
      console.log('[OCR] Tesseract.js loaded');
      resolve(true);
    };
    script.onerror = () => {
      console.error('[OCR] Failed to load Tesseract.js');
      reject(new Error('Failed to load Tesseract.js'));
    };
    document.head.appendChild(script);
  });
}

async function performOCRInContent(imageData, language = 'eng', autoRead = false) {
  try {
    showOCRNotification('Loading OCR engine...', 'info');
    
    // Load Tesseract if not already loaded
    await loadTesseract();
    
    showOCRNotification('Processing image...', 'info');
    
    // Create worker if needed
    if (tesseractWorker) {
      await tesseractWorker.terminate();
      tesseractWorker = null;
    }
    
    tesseractWorker = await Tesseract.createWorker(language, 1, {
      logger: (m) => {
        if (m.status === 'recognizing text') {
          const percent = Math.round(m.progress * 100);
          showOCRNotification(`Processing: ${percent}%`, 'info');
        }
      }
    });
    
    // Perform OCR
    const { data } = await tesseractWorker.recognize(imageData);
    
    console.log('[OCR] Text extracted:', data.text.length, 'characters');
    console.log('[OCR] Confidence:', data.confidence);
    
    showOCRNotification('Text extracted successfully!', 'success');
    
    // Display results
    displayOCRResult(data.text, data.confidence);
    
    // Auto-read if enabled
    if (autoRead && data.text) {
      setTimeout(() => {
        startReading(data.text);
        closeOCRModal();
      }, 1000);
    }
    
  } catch (error) {
    console.error('[OCR] Error:', error);
    showOCRNotification(`OCR Error: ${error.message}`, 'error');
    throw error;
  }
}

// ===== OCR UI Functions =====
function showOCRNotification(message, type = 'info') {
  // Create or get notification element
  let notification = document.getElementById('Mockingbird-ocr-notification');
  if (!notification) {
    notification = document.createElement('div');
    notification.id = 'Mockingbird-ocr-notification';
    notification.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      padding: 12px 20px;
      border-radius: 8px;
      font-family: system-ui, -apple-system, sans-serif;
      font-size: 14px;
      font-weight: 500;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      z-index: 999999;
      transition: opacity 0.3s ease;
    `;
    document.body.appendChild(notification);
  }

  // Set message and style based on type
  notification.textContent = message;
  switch (type) {
    case 'success':
      notification.style.background = '#10b981';
      notification.style.color = 'white';
      break;
    case 'error':
      notification.style.background = '#ef4444';
      notification.style.color = 'white';
      break;
    case 'info':
    default:
      notification.style.background = '#3b82f6';
      notification.style.color = 'white';
      break;
  }

  notification.style.opacity = '1';

  // Auto-hide after 3 seconds
  setTimeout(() => {
    notification.style.opacity = '0';
    setTimeout(() => {
      if (notification.parentNode) {
        notification.parentNode.removeChild(notification);
      }
    }, 300);
  }, 3000);
}

function displayOCRResult(text, confidence) {
  // Create modal to display OCR result
  let modal = document.getElementById('Mockingbird-ocr-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'Mockingbird-ocr-modal';
    modal.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: white;
      border-radius: 12px;
      padding: 24px;
      max-width: 600px;
      max-height: 500px;
      width: 90%;
      box-shadow: 0 8px 32px rgba(0,0,0,0.2);
      z-index: 1000000;
      font-family: system-ui, -apple-system, sans-serif;
      overflow-y: auto;
    `;
    document.body.appendChild(modal);

    // Add backdrop
    const backdrop = document.createElement('div');
    backdrop.id = 'Mockingbird-ocr-backdrop';
    backdrop.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.5);
      z-index: 999999;
    `;
    backdrop.addEventListener('click', () => closeOCRModal());
    document.body.appendChild(backdrop);
  }

  const confidencePercent = Math.round(confidence);
  modal.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2 style="margin: 0; color: #1f2937; font-size: 20px;">OCR Text Extracted</h2>
      <button id="Mockingbird-ocr-close" style="background: none; border: none; font-size: 24px; cursor: pointer; color: #6b7280;">×</button>
    </div>
    <div style="margin-bottom: 12px; color: #6b7280; font-size: 13px;">
      Confidence: ${confidencePercent}%
    </div>
    <div style="background: #f3f4f6; border-radius: 8px; padding: 16px; margin-bottom: 16px; max-height: 300px; overflow-y: auto;">
      <pre style="margin: 0; white-space: pre-wrap; word-wrap: break-word; font-family: system-ui, -apple-system, sans-serif; color: #1f2937; font-size: 14px; line-height: 1.6;">${escapeHtml(text)}</pre>
    </div>
    <div style="display: flex; gap: 8px;">
      <button id="Mockingbird-ocr-read" style="flex: 1; background: #2563eb; color: white; border: none; border-radius: 6px; padding: 10px 16px; font-size: 14px; font-weight: 600; cursor: pointer;">
        🔊 Read Aloud
      </button>
      <button id="Mockingbird-ocr-copy" style="flex: 1; background: #059669; color: white; border: none; border-radius: 6px; padding: 10px 16px; font-size: 14px; font-weight: 600; cursor: pointer;">
        📋 Copy Text
      </button>
    </div>
  `;

  // Event listeners
  document.getElementById('Mockingbird-ocr-close').addEventListener('click', closeOCRModal);
  document.getElementById('Mockingbird-ocr-read').addEventListener('click', () => {
    startReading(text);
    closeOCRModal();
  });
  document.getElementById('Mockingbird-ocr-copy').addEventListener('click', () => {
    navigator.clipboard.writeText(text).then(() => {
      showOCRNotification('Text copied to clipboard!', 'success');
    });
  });
}

function closeOCRModal() {
  const modal = document.getElementById('Mockingbird-ocr-modal');
  const backdrop = document.getElementById('Mockingbird-ocr-backdrop');
  if (modal) modal.remove();
  if (backdrop) backdrop.remove();
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
