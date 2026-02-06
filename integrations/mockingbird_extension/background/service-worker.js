/**
 * Mockingbird Browser Extension - Background Service Worker
 * Licensed under the MIT License.
 * Copyright (c) 2026 PiperTTS Mockingbird Developers
 */

const PIPER_SERVER = 'http://localhost:5002';

// Default shared API key (matches server default for automatic protection)
// Change this if you customize PIPER_API_KEY on the server
const API_KEY = 'piper-mockingbird-local-2026';

const MAX_RETRY_ATTEMPTS = 3;
const RETRY_DELAY = 1000; // ms
const MIN_SENTENCE_LENGTH = 10; // chars - batch shorter sentences
const CACHE_SIZE_LIMIT_MB = 100; // Session-only cache limit
const DEFAULT_WORDS_PER_SECOND_AT_1X = 2.74; // Baseline rate at 1.0x speed

let audioQueue = [];
let isPlaying = false;
let currentAudio = null;
let currentSentenceIndex = 0;
let allSentences = [];
// Tracks the current "wait for audioFinished" promise so Stop can interrupt immediately.
let activePlaybackWaiter = null;
// Tracks the active /api/tts request so Stop can cancel it immediately.
let activeTtsAbortController = null;
let isPaused = false;
let serverOnline = true;
let lastHealthCheck = 0;
// Session-only in-memory cache with LRU eviction
let audioCache = new Map(); // key -> { audioBlob, timestamp, size, accessTime }
let cacheCurrentSize = 0; // bytes

function abortActiveTts(reason = 'stopped') {
  try {
    if (activeTtsAbortController) {
      activeTtsAbortController.abort(reason);
    }
  } catch (_) {
    // ignore
  } finally {
    activeTtsAbortController = null;
  }
}

// State management
let readerState = {
  isReading: false,
  isPaused: false,
  currentText: '',
  currentVoice: 'en_US-hfc_female-medium.onnx',
  readingSpeed: 1.0,
  volume: 1.0,
  currentPage: null,
  currentPosition: 0,
  totalSentences: 0,
  sleepTimer: null,
  autoScroll: true,
  serverConnected: true,
  isWaitingForAudio: false,
  currentTime: 0,
  totalTime: 0,
  audioStartTime: 0,
  currentAudioDuration: 0,
  // Adaptive timing
  baseWordsPerSecond: null,
  baseSpeed: null,
  recentSentences: [],
  totalWordsRead: 0,
  totalActualTime: 0
};

// ===== Initialize Settings =====
async function loadSavedSettings() {
  const settings = await chrome.storage.local.get([
    'voice',
    'speed',
    'volume',
    'autoScroll'
  ]);
  
  if (settings.voice !== undefined) {
    readerState.currentVoice = settings.voice;
  }
  if (settings.speed !== undefined) {
    readerState.readingSpeed = settings.speed;
  }
  if (settings.volume !== undefined) {
    readerState.volume = settings.volume;
  }
  if (settings.autoScroll !== undefined) {
    readerState.autoScroll = settings.autoScroll;
  }
  
  console.log('[Settings] Loaded:', {
    voice: readerState.currentVoice,
    speed: readerState.readingSpeed,
    volume: readerState.volume,
    autoScroll: readerState.autoScroll
  });
}

// ===== Session-Only In-Memory Audio Cache =====
function initAudioCache() {
  // In-memory cache requires no initialization
  console.log('[Cache] Session-only cache initialized (limit: ' + CACHE_SIZE_LIMIT_MB + ' MB)');
  return Promise.resolve();
}

function generateCacheKey(text, voice) {
  // Hash text to avoid storing plain content in keys
  let hash = 0;
  const str = text + voice;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash) + str.charCodeAt(i);
    hash = hash & hash; // Convert to 32bit integer
  }
  return `${voice}:${hash}`;
}

async function getCachedAudio(text, voice) {
  try {
    const key = generateCacheKey(text, voice);
    const entry = audioCache.get(key);
    
    if (entry) {
      // Update access time for LRU
      entry.accessTime = Date.now();
      console.log('[Cache] HIT (size: ' + (cacheCurrentSize / 1024 / 1024).toFixed(1) + ' MB)');
      return entry.audioBlob;
    }
    
    return null;
  } catch (error) {
    console.error('[Cache] Error reading:', error);
    return null;
  }
}

async function cacheAudio(text, voice, audioBlob) {
  try {
    const key = generateCacheKey(text, voice);
    const blobSize = audioBlob.size;
    const maxSize = CACHE_SIZE_LIMIT_MB * 1024 * 1024;
    
    // Skip if single blob exceeds limit
    if (blobSize > maxSize) {
      console.log('[Cache] Blob too large to cache:', (blobSize / 1024 / 1024).toFixed(1), 'MB');
      return;
    }
    
    // Evict LRU entries until we have space
    while (cacheCurrentSize + blobSize > maxSize && audioCache.size > 0) {
      // Find oldest accessed entry
      let oldestKey = null;
      let oldestTime = Infinity;
      
      for (const [k, v] of audioCache.entries()) {
        if (v.accessTime < oldestTime) {
          oldestTime = v.accessTime;
          oldestKey = k;
        }
      }
      
      if (oldestKey) {
        const evicted = audioCache.get(oldestKey);
        cacheCurrentSize -= evicted.size;
        audioCache.delete(oldestKey);
        console.log('[Cache] LRU evicted (freed ' + (evicted.size / 1024).toFixed(1) + ' KB)');
      } else {
        break;
      }
    }
    
    // Store new entry
    const now = Date.now();
    audioCache.set(key, {
      audioBlob: audioBlob,
      timestamp: now,
      accessTime: now,
      size: blobSize
    });
    
    cacheCurrentSize += blobSize;
    console.log('[Cache] STORED (total: ' + (cacheCurrentSize / 1024 / 1024).toFixed(1) + ' MB / ' + CACHE_SIZE_LIMIT_MB + ' MB)');
  } catch (error) {
    console.error('[Cache] Error storing:', error);
  }
}

async function clearAllCache() {
  try {
    const entriesCleared = audioCache.size;
    audioCache.clear();
    cacheCurrentSize = 0;
    console.log('[Cache] Cleared all entries (' + entriesCleared + ' items)');
  } catch (error) {
    console.error('[Cache] Error clearing:', error);
  }
}

function getCacheStats() {
  return {
    entries: audioCache.size,
    sizeMB: (cacheCurrentSize / 1024 / 1024).toFixed(2),
    limitMB: CACHE_SIZE_LIMIT_MB
  };
}

// ===== Server Health Checks =====
async function checkServerHealth() {
  // Don't check too frequently (max once per 10 seconds)
  if (Date.now() - lastHealthCheck < 10000) {
    return serverOnline;
  }
  
  try {
    const settings = await chrome.storage.local.get(['serverUrl']);
    const serverUrl = settings.serverUrl || PIPER_SERVER;
    const response = await fetch(`${serverUrl}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(5000), // 5 second timeout
      headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
    });
    
    lastHealthCheck = Date.now();
    const wasOffline = !serverOnline;
    serverOnline = response.ok;
    readerState.serverConnected = serverOnline;
    
    if (serverOnline && wasOffline) {
      notifyContentScript('notification', {
        message: '✓ Server connection restored',
        type: 'success'
      });
    }
    
    return serverOnline;
  } catch (error) {
    console.error('[Health] Server check failed:', error);
    lastHealthCheck = Date.now();
    const wasOnline = serverOnline;
    serverOnline = false;
    readerState.serverConnected = false;
    
    if (wasOnline) {
      const settings = await chrome.storage.local.get(['serverUrl']);
      notifyContentScript('notification', {
        message: '⚠ Cannot reach Piper server at ' + (settings.serverUrl || PIPER_SERVER),
        type: 'error',
        duration: 5000
      });
    }
    
    return false;
  }
}

async function retryWithBackoff(fn, maxAttempts = MAX_RETRY_ATTEMPTS) {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (error) {
      if (attempt === maxAttempts) {
        throw error;
      }
      const delay = RETRY_DELAY * Math.pow(2, attempt - 1);
      console.log(`[Retry] Attempt ${attempt} failed, retrying in ${delay}ms...`);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}

// Listen for extension installation
chrome.runtime.onInstalled.addListener(async () => {
  console.log('Mockingbird installed');

  // (Re)create context menus on install/update
  try {
    await createContextMenus();
  } catch (error) {
    console.error('[Menus] Failed to create context menus onInstalled:', error);
  }
  
  // Initialize session-only cache
  try {
    await initAudioCache();
  } catch (error) {
    console.error('[Cache] Initialization failed:', error);
  }
  
  // Initialize default settings
  chrome.storage.local.set({
    voice: 'en_US-hfc_female-medium.onnx',
    speed: 1.0,
    volume: 1.0,
    serverUrl: PIPER_SERVER,
    autoScroll: true
  });
  
  // Load settings into readerState
  await loadSavedSettings();
  
  // Initial health check
  checkServerHealth();
  
});

async function createContextMenus() {
  await new Promise((resolve) => chrome.contextMenus.removeAll(() => resolve()));

  chrome.contextMenus.create({
    id: 'read-selection',
    title: 'Read with Mockingbird',
    contexts: ['selection']
  });

  chrome.contextMenus.create({
    id: 'read-page',
    title: 'Read entire page',
    contexts: ['page']
  });

  chrome.contextMenus.create({
    id: 'save-to-library',
    title: 'Save page to library',
    contexts: ['page']
  });

  chrome.contextMenus.create({
    id: 'ocr-image',
    title: 'Extract text from image (OCR)',
    contexts: ['image']
  }, () => {
    if (chrome.runtime.lastError) {
      console.error('[OCR] Error creating OCR context menu:', chrome.runtime.lastError);
    } else {
      console.log('[OCR] OCR context menu created');
    }
  });

  console.log('[Menus] Context menus (re)created');
}

// Load settings when service worker starts up
chrome.runtime.onStartup.addListener(async () => {
  console.log('Mockingbird service worker starting up');

  // Ensure context menus exist after browser restart
  try {
    await createContextMenus();
  } catch (error) {
    console.error('[Menus] Failed to create context menus onStartup:', error);
  }
  
  // Initialize session-only cache
  try {
    await initAudioCache();
  } catch (error) {
    console.error('[Cache] Initialization failed:', error);
  }
  
  // Load saved settings into readerState
  await loadSavedSettings();
  
  // Check server health
  checkServerHealth();
});

// Also load settings immediately when script loads (for service worker restarts)
(async () => {
  try {
    await initAudioCache();
    await loadSavedSettings();
    await createContextMenus();
    checkServerHealth();
    console.log('[Init] Service worker ready');
  } catch (error) {
    console.error('[Init] Error:', error);
  }
})();

// Command shortcuts handler
chrome.commands.onCommand.addListener((command) => {
  if (command === 'play-pause') {
    togglePlayPause();
  } else if (command === 'stop-reading') {
    stopReading();
  } else if (command === 'screenshot-ocr') {
    chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
      const tabId = tabs?.[0]?.id;
      const windowId = tabs?.[0]?.windowId;
      if (!tabId) return;
      
      // Open sidepanel first (command handlers have user gesture context)
      try {
        console.log('[OCR Shortcut] Opening sidepanel for window:', windowId);
        await chrome.sidePanel.open({ windowId });
        
        // Small delay to let sidepanel open
        await new Promise(resolve => setTimeout(resolve, 150));
      } catch (err) {
        console.warn('[OCR Shortcut] Could not open sidepanel:', err);
      }
      
      // Then activate OCR capture
      chrome.tabs.sendMessage(tabId, { type: 'ACTIVATE_OCR_CAPTURE' }).catch(() => {});
    });
  } else if (command === 'speed-up') {
    adjustSpeed(0.1);
  } else if (command === 'speed-down') {
    adjustSpeed(-0.1);
  } else if (command === 'skip-forward') {
    skipTimeForward(10);
  } else if (command === 'skip-backward') {
    skipTimeBackward(10);
  }
});

// Context menu handler
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === 'read-selection') {
    // Try to use Chrome's selection first
    if (info.selectionText) {
      startReading(info.selectionText);
    } else {
      // Fallback: Ask content script to get selection (for Google Docs, etc.)
      chrome.tabs.sendMessage(tab.id, { action: 'getSelectedTextFallback' }, (response) => {
        if (response && response.text) {
          startReading(response.text);
        } else {
          console.warn('[Context Menu] No text selected');
        }
      });
    }
  } else if (info.menuItemId === 'read-page') {
    chrome.tabs.sendMessage(tab.id, { action: 'getTextToRead' }, (response) => {
      if (response && response.text) {
        startReading(response.text);
      }
    });
  } else if (info.menuItemId === 'ocr-image' && info.srcUrl) {
    // Open sidepanel first for OCR results
    try {
      await chrome.sidePanel.open({ windowId: tab.windowId });
    } catch (err) {
      console.warn('[OCR Context Menu] Could not open sidepanel:', err);
    }
    
    handleOCRRequest(info.srcUrl, tab.id);
  }
});

// Adjust reading speed
async function adjustSpeed(delta) {
  readerState.readingSpeed = Math.max(0.5, Math.min(2.0, readerState.readingSpeed + delta));
  await chrome.storage.local.set({ speed: readerState.readingSpeed });
  
  if (currentAudio) {
    currentAudio.playbackRate = readerState.readingSpeed;
  }
  
  // Notify UI of speed change
  notifyContentScript('speedChanged', { speed: readerState.readingSpeed });
  
  console.log(`Speed adjusted to ${readerState.readingSpeed.toFixed(1)}x`);
}

// Message handler from content scripts and side panel
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const messageKind = message?.action ?? message?.type;
  console.log('Background received message:', messageKind);

  switch (messageKind) {
    case 'startReading':
      startReading(message.text, message.options || {});
      sendResponse({ success: true });
      break;

    case 'togglePlayPause':
      togglePlayPause();
      sendResponse({ success: true, isPlaying: readerState.isReading });
      break;

    case 'stopReading':
      stopReading();
      sendResponse({ success: true });
      break;

    case 'getState':
      sendResponse({ state: readerState });
      break;

    case 'setVoice':
      readerState.currentVoice = message.voice;
      chrome.storage.local.set({ voice: message.voice });
      sendResponse({ success: true });
      break;

    case 'setSpeed':
      const oldSpeed = readerState.readingSpeed;
      readerState.readingSpeed = message.speed;
      
      // If we have learned a base rate, recalculate total time
      if (readerState.baseWordsPerSecond && readerState.baseSpeed) {
        const speedRatio = message.speed / readerState.baseSpeed;
        const currentWordsPerSecond = readerState.baseWordsPerSecond * speedRatio;
        const remainingWords = calculateRemainingWords(currentSentenceIndex);
        const estimatedRemainingTime = remainingWords / currentWordsPerSecond;
        
        readerState.totalTime = readerState.totalActualTime + estimatedRemainingTime;
        console.log(`[Speed Change] ${oldSpeed}x → ${message.speed}x, New total: ${readerState.totalTime.toFixed(1)}s`);
      }
      
      chrome.storage.local.set({ speed: message.speed });
      sendResponse({ success: true });
      break;

    case 'setVolume':
      readerState.volume = message.volume;
      // Update current audio if playing
      if (currentAudio) {
        currentAudio.volume = message.volume;
      }
      // Forward volume change to content script where audio actually plays
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs[0]) {
          chrome.tabs.sendMessage(tabs[0].id, {
            action: 'updateVolume',
            volume: message.volume
          }).catch(() => {}); // Ignore errors if content script not ready
        }
      });
      chrome.storage.local.set({ volume: message.volume });
      sendResponse({ success: true });
      break;

    case 'getVoices':
      fetchVoiceList().then(voices => {
        sendResponse({ voices });
      });
      return true; // Keep channel open for async response

    case 'skipForward':
      try {
        skipToNextSentence();
        sendResponse({ success: true });
      } catch (error) {
        console.error('[skipForward] Error:', error);
        sendResponse({ success: false, error: error.message });
      }
      break;

    case 'skipBackward':
      try {
        skipToPreviousSentence();
        sendResponse({ success: true });
      } catch (error) {
        console.error('[skipBackward] Error:', error);
        sendResponse({ success: false, error: error.message });
      }
      break;
    
    case 'setSleepTimer':
      setSleepTimer(message.minutes);
      sendResponse({ success: true });
      break;
    
    case 'cancelSleepTimer':
      cancelSleepTimer();
      sendResponse({ success: true });
      break;
    
    case 'skipTimeForward':
      skipTimeForward(message.seconds || 10);
      sendResponse({ success: true });
      break;
    
    case 'skipTimeBackward':
      skipTimeBackward(message.seconds || 10);
      sendResponse({ success: true });
      break;
    
    case 'jumpToPercentage':
      jumpToPercentage(message.percentage);
      sendResponse({ success: true });
      break;
    
    case 'toggleAutoScroll':
      readerState.autoScroll = message.enabled;
      chrome.storage.local.set({ autoScroll: message.enabled });
      sendResponse({ success: true });
      break;
    
    case 'openSidePanel':
      (async () => {
        try {
          // Get the current tab's window (not the popup window)
          const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
          const windowId = tab?.windowId || (await chrome.windows.getLastFocused()).id;
          
          console.log('[openSidePanel] Opening sidepanel for window:', windowId);
          await chrome.sidePanel.open({ windowId });
          sendResponse({ success: true });
        } catch (error) {
          console.error('[openSidePanel] Error:', error);
          sendResponse({ success: false, error: error.message });
        }
      })();
      return true; // Keep channel open for async response
    
    case 'getProgress':
      const currentTime = calculateCurrentTime();
      sendResponse({
        currentTime: currentTime,
        totalTime: readerState.totalTime,
        currentParagraph: currentSentenceIndex + 1,
        totalParagraphs: allSentences.length,
        wordsPerSecond: readerState.baseWordsPerSecond
      });
      break;
    
    case 'getCacheStats':
      sendResponse(getCacheStats());
      break;
    
    case 'clearCache':
      clearAllCache().then(() => {
        sendResponse({ success: true, ...getCacheStats() });
      });
      return true; // Keep channel open for async response

    case 'OCR_CAPTURE':
      handleOCRCapture(message.selection, sender.tab?.id)
        .then(result => sendResponse(result))
        .catch(error => sendResponse({ success: false, error: error.message }));
      return true; // Keep channel open for async response
    
    case 'performOCR':
      performOCR(message.imageUrl, message.language || 'eng')
        .then(result => sendResponse(result))
        .catch(error => sendResponse({ success: false, error: error.message }));
      return true; // Keep channel open for async response
    
    case 'setOCRLanguage':
      chrome.storage.local.set({ ocrLanguage: message.language });
      sendResponse({ success: true });
      break;
    
    case 'setOCRAutoRead':
      chrome.storage.local.set({ ocrAutoRead: message.enabled });
      sendResponse({ success: true });
      break;

    case 'OCR_SELF_TEST':
      (async () => {
        const ok = await ensureOffscreenDocument();
        if (!ok) {
          return { success: false, error: 'Local OCR unavailable (offscreen document could not be created)' };
        }
        return await sendMessageWithTimeout(
          { type: 'OCR_SELF_TEST', language: message.language || 'eng' },
          60000
        );
      })()
        .then(sendResponse)
        .catch(err => sendResponse({ success: false, error: err?.message || String(err) }));
      return true; // Keep channel open for async response
    
    default:
      // Unknown message type - send empty response to prevent channel errors
      sendResponse({ success: false, error: 'Unknown message type: ' + messageKind });
      break;
  }
  
  // Don't return true here - only specific async handlers should keep channel open
});

// Fetch available voices from Piper server
async function fetchVoiceList() {
  try {
    const settings = await chrome.storage.local.get(['serverUrl']);
    const serverUrl = settings.serverUrl || PIPER_SERVER;
    const response = await fetch(`${serverUrl}/health`, {
      headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
    });
    if (!response.ok) throw new Error('Failed to fetch voices');
    const data = await response.json();
    
    // Extract voice names from health response
    if (data.available_voices && Array.isArray(data.available_voices)) {
      return data.available_voices.map(v => v.name);
    }
    return [];
  } catch (error) {
    console.error('Error fetching voices:', error);
    return [];
  }
}

// Start reading text
async function startReading(text, options = {}) {
  if (!text || !text.trim()) {
    console.warn('No text to read');
    return;
  }
  
  // Check server health before starting
  const isHealthy = await checkServerHealth();
  if (!isHealthy) {
    notifyContentScript('notification', {
      message: '⚠ Piper server is not responding. Please check if it\'s running.',
      type: 'error',
      duration: 5000
    });
    return;
  }

  // Stop any current reading
  stopReading();

  readerState.isReading = true;
  readerState.isPaused = false;
  readerState.currentText = text;
  currentSentenceIndex = 0;

  // Split text into sentences and batch short ones
  const rawSentences = splitIntoSentences(text);
  allSentences = batchShortSentences(rawSentences);
  
  // Count words in each sentence
  allSentences = allSentences.map(sentence => ({
    text: sentence,
    wordCount: countWords(sentence)
  }));
  
  // Calculate total words
  const totalWords = allSentences.reduce((sum, s) => sum + s.wordCount, 0);
  
  readerState.totalSentences = allSentences.length;
  readerState.currentPosition = 0;
  
  // Reset adaptive timing
  readerState.currentTime = 0;
  readerState.audioStartTime = 0;
  readerState.currentAudioDuration = 0;
  readerState.baseWordsPerSecond = null;
  readerState.baseSpeed = null;
  readerState.recentSentences = [];
  readerState.totalWordsRead = 0;
  readerState.totalActualTime = 0;
  
  // Initial estimate using default baseline rate adjusted for current speed
  const estimatedWordsPerSecond = DEFAULT_WORDS_PER_SECOND_AT_1X * readerState.readingSpeed;
  readerState.totalTime = totalWords / estimatedWordsPerSecond;
  
  console.log(`Split into ${rawSentences.length} sentences, batched to ${allSentences.length}, ${totalWords} words`);
  console.log(`Initial estimate: ${readerState.totalTime.toFixed(1)}s at ${readerState.readingSpeed}x (${estimatedWordsPerSecond.toFixed(2)} words/sec)`);

  // Notify content script that reading started
  notifyContentScript('readingStarted', { totalSentences: allSentences.length });

  // Start reading from first sentence
  await readNextSentence();
}

// Count words in a sentence
function countWords(text) {
  return text.trim().split(/\s+/).filter(w => w.length > 0).length;
}

// Split text into sentences with better punctuation handling
function splitIntoSentences(text) {
  // Split on period, exclamation, question mark followed by space or end
  // Preserve common abbreviations
  const sentences = text
    .replace(/(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|etc|vs|i\.e|e\.g)\.\s/gi, '$1<DOT> ')
    .replace(/([.!?:;])\s+/g, '$1|')
    .replace(/<DOT>/g, '.')
    .split('|')
    .map(s => s.trim())
    .filter(s => s.length > 0);
  
  return sentences;
}

// Split sentence into words for word-by-word highlighting
function splitIntoWords(sentence) {
  return sentence.match(/\S+/g) || [];
}

// Read the next sentence in queue
async function readNextSentence() {
  readerState.currentPosition = currentSentenceIndex;
  
  if (currentSentenceIndex >= allSentences.length) {
    // Finished reading all sentences
    stopReading();
    notifyContentScript('readingComplete');
    return;
  }

  if (!readerState.isReading || readerState.isPaused) {
    return;
  }

  const sentenceObj = allSentences[currentSentenceIndex];
  const sentence = sentenceObj.text;
  console.log(`Reading sentence ${currentSentenceIndex + 1}/${allSentences.length}`);

  // Split sentence into words for word-by-word highlighting
  const words = splitIntoWords(sentence);
  
  // Notify content script about current sentence with word data
  notifyContentScript('sentenceStart', {
    index: currentSentenceIndex,
    text: sentence,
    words: words,
    total: allSentences.length
  });

  try {
    const audioData = await synthesizeSpeech(sentence);
    
    if (!readerState.isReading) return;

    // Convert blob to base64 for sending to content script
    const reader = new FileReader();
    const audioBase64 = await new Promise((resolve, reject) => {
      reader.onloadend = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(audioData);
    });
    
    // Send audio to content script to play
    readerState.isWaitingForAudio = true;
    await playAudioInContent(audioBase64);
    readerState.isWaitingForAudio = false;

    // If Stop was pressed while we were waiting for audio, exit immediately.
    if (!readerState.isReading) return;
    
    // Move to next sentence
    currentSentenceIndex++;
    readNextSentence();
  } catch (error) {
    readerState.isWaitingForAudio = false;
    
    // Extract error info early for better checking
    const errorString = typeof error === 'string' ? error : error?.message || '';
    
    // If request was aborted/skipped or message channel closed, just return silently
    if (error.name === 'AbortError' || 
        errorString === 'new-request' ||
        errorString.includes('Skipped') || 
        errorString.includes('skipped') ||
        errorString.includes('Message channel closed')) {
      console.log('[Reader] Request cancelled or interrupted, moving to next sentence');
      return;
    }
    
    // If Stop was pressed or reading was otherwise cancelled, don't surface an error.
    if (!readerState.isReading) {
      return;
    }
    
    console.error('Error reading sentence:', error);
    
    // Extract a meaningful error message
    let errorMessage = 'Unknown error occurred while reading';
    if (error) {
      if (typeof error === 'string') {
        errorMessage = error;
      } else if (error.message) {
        errorMessage = error.message;
      } else if (error.toString && error.toString() !== '[object Object]') {
        errorMessage = error.toString();
      } else {
        try {
          errorMessage = JSON.stringify(error);
        } catch (e) {
          errorMessage = 'Unserializable error object';
        }
      }
    }
    
    // Check for specific "undefined" string case or internal signals
    if (errorMessage === 'undefined' || !errorMessage || errorMessage === 'new-request') {
       console.log('[Reader] Suppressing internal error signal:', errorMessage);
       return;
    }

    notifyContentScript('error', { message: errorMessage });
    stopReading();
  }
}

// Track completed sentence and update timing estimates
function trackSentenceCompletion(sentenceIndex, duration) {
  if (sentenceIndex >= allSentences.length) return;
  
  const sentenceObj = allSentences[sentenceIndex];
  const words = sentenceObj.wordCount;
  
  // Add to rolling window (keep last 5)
  readerState.recentSentences.push({ words, duration });
  if (readerState.recentSentences.length > 5) {
    readerState.recentSentences.shift();
  }
  
  readerState.totalWordsRead += words;
  
  // After 3 sentences, calculate base rate and update estimate
  if (readerState.recentSentences.length >= 3) {
    const totalWords = readerState.recentSentences.reduce((sum, s) => sum + s.words, 0);
    const totalTime = readerState.recentSentences.reduce((sum, s) => sum + s.duration, 0);
    
    // Calculate base rate at current speed
    readerState.baseWordsPerSecond = totalWords / totalTime;
    readerState.baseSpeed = readerState.readingSpeed;
    
    // Recalculate total time based on remaining words
    const remainingWords = calculateRemainingWords(sentenceIndex + 1);
    const currentWordsPerSecond = readerState.baseWordsPerSecond;
    const estimatedRemainingTime = remainingWords / currentWordsPerSecond;
    
    readerState.totalTime = readerState.totalActualTime + estimatedRemainingTime;
    
    // Calculate what the rate would be at 1.0x for comparison
    const normalizedRate = readerState.baseWordsPerSecond / readerState.baseSpeed;
    
    console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
    console.log(`[Adaptive Timing] LEARNED RATE:`);
    console.log(`  Current: ${readerState.baseWordsPerSecond.toFixed(2)} words/sec at ${readerState.baseSpeed}x speed`);
    console.log(`  At 1.0x: ${normalizedRate.toFixed(2)} words/sec (normalized baseline)`);
    console.log(`  Remaining: ${remainingWords} words = ${estimatedRemainingTime.toFixed(1)}s`);
    console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
  }
}

// Calculate remaining words from given sentence index
function calculateRemainingWords(fromIndex) {
  let remaining = 0;
  for (let i = fromIndex; i < allSentences.length; i++) {
    remaining += allSentences[i].wordCount;
  }
  return remaining;
}

// Calculate current playback time
function calculateCurrentTime() {
  if (!readerState.isReading) return 0;
  
  // Use actual tracked time from completed sentences
  let totalElapsed = readerState.totalActualTime;
  
  // Add time from current audio
  if (readerState.audioStartTime > 0 && !readerState.isPaused) {
    const currentAudioElapsed = (Date.now() - readerState.audioStartTime) / 1000;
    totalElapsed += Math.min(currentAudioElapsed, readerState.currentAudioDuration);
  }
  
  return totalElapsed;
}

// Play audio in content script
function playAudioInContent(audioBase64) {
  return new Promise((resolve, reject) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) {
        const targetTabId = tabs[0].id;
        // If we somehow have a previous waiter, clean it up.
        if (activePlaybackWaiter?.listener) {
          try { chrome.runtime.onMessage.removeListener(activePlaybackWaiter.listener); } catch (_) {}
          activePlaybackWaiter = null;
        }

        // Create a listener for when the audio finishes
        const messageListener = (message, sender) => {
          // Only accept messages from the tab we started playback in.
          if (sender?.tab?.id !== targetTabId) return;
          if (message.action === 'audioFinished') {
            chrome.runtime.onMessage.removeListener(messageListener);
            if (activePlaybackWaiter?.listener === messageListener) {
              activePlaybackWaiter = null;
            }
            // Update timing
            const duration = readerState.currentAudioDuration;
            readerState.currentTime += duration;
            readerState.totalActualTime += duration;
            
            // Track this sentence for adaptive timing
            trackSentenceCompletion(currentSentenceIndex, duration);
            
            readerState.audioStartTime = 0;
            readerState.currentAudioDuration = 0;
            resolve();
          } else if (message.action === 'audioError') {
            chrome.runtime.onMessage.removeListener(messageListener);
            if (activePlaybackWaiter?.listener === messageListener) {
              activePlaybackWaiter = null;
            }
            const errorMsg = message.error || 'Unknown audio error reported by content script';
            reject(new Error(errorMsg));
          } else if (message.action === 'audioDuration') {
            // Content script sends us the audio duration
            readerState.currentAudioDuration = message.duration;
            readerState.audioStartTime = Date.now();
            
            // Broadcast to side panel for word-by-word highlighting
            chrome.runtime.sendMessage({
              action: 'audioDuration',
              duration: message.duration
            }).catch(() => {});
          }
        };
        
        chrome.runtime.onMessage.addListener(messageListener);

        // Save a handle so stopReading() can immediately unblock this await.
        activePlaybackWaiter = {
          tabId: targetTabId,
          listener: messageListener,
          resolve,
          reject,
        };
        
        // Send audio to content script
        chrome.tabs.sendMessage(targetTabId, {
          action: 'playAudio',
          audioData: audioBase64,
          speed: readerState.readingSpeed,
          volume: readerState.volume
        }, (response) => {
          console.log('[Audio Playback] Sent with speed:', readerState.readingSpeed, 'volume:', readerState.volume);
          // Check for runtime errors (e.g., message channel closed)
          if (chrome.runtime.lastError) {
            console.log('[Audio] Send message error:', chrome.runtime.lastError.message);
            // Clean up listener
            try {
              chrome.runtime.onMessage.removeListener(messageListener);
            } catch (e) {}
            if (activePlaybackWaiter?.listener === messageListener) {
              activePlaybackWaiter = null;
            }
            // Reject with a specific error so it can be caught upstream
            reject(new Error('Message channel closed'));
            return;
          }
          
          if (!response || !response.success) {
            chrome.runtime.onMessage.removeListener(messageListener);
            if (activePlaybackWaiter?.listener === messageListener) {
              activePlaybackWaiter = null;
            }
            reject(new Error(response?.error || 'Failed to start audio playback'));
          }
          // Otherwise, wait for audioFinished message
        });
      } else {
        reject(new Error('No active tab'));
      }
    });
  });
}

// Synthesize speech using Piper server (with caching and retry logic)
async function synthesizeSpeech(text) {
  const settings = await chrome.storage.local.get(['voice', 'serverUrl']);
  const voice = settings.voice || readerState.currentVoice;
  const serverUrl = settings.serverUrl || PIPER_SERVER;

  // Check cache first
  const cachedAudio = await getCachedAudio(text, voice);
  if (cachedAudio) {
    return cachedAudio;
  }

  console.log(`Synthesizing: "${text.substring(0, 50)}..."`);

  // Synthesize with retry logic
  const audioBlob = await retryWithBackoff(async () => {
    // Cancel any previous in-flight request (e.g., rapid stop/start).
    abortActiveTts('new-request');
    const controller = new AbortController();
    activeTtsAbortController = controller;

    const timeoutId = setTimeout(() => {
      try { controller.abort('timeout'); } catch (_) {}
    }, 30000);

    try {
      const response = await fetch(`${serverUrl}/api/tts`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          text: text,
          voice_model: voice,
          stream: false
        }),
        signal: controller.signal
      });

      if (!response.ok) {
        // Update server status
        serverOnline = false;
        readerState.serverConnected = false;
        throw new Error(`TTS server error: ${response.status} ${response.statusText}`);
      }
      
      // Server is working
      serverOnline = true;
      readerState.serverConnected = true;

      return await response.blob();
    } finally {
      clearTimeout(timeoutId);
      if (activeTtsAbortController === controller) {
        activeTtsAbortController = null;
      }
    }
  });
  
  // Cache the audio for future use
  await cacheAudio(text, voice, audioBlob);

  return audioBlob;
}

// Toggle play/pause
function togglePlayPause() {
  if (!readerState.isReading) {
    // Not currently reading, try to read selected text or page
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) {
        chrome.tabs.sendMessage(tabs[0].id, { action: 'getTextToRead' }, (response) => {
          if (response && response.text) {
            startReading(response.text);
          }
        });
      }
    });
  } else if (readerState.isPaused) {
    // Resume
    readerState.isPaused = false;
    notifyContentScript('resumed');
    if (!readerState.isWaitingForAudio) {
      readNextSentence();
    }
  } else {
    // Pause
    readerState.isPaused = true;
    if (currentAudio) {
      currentAudio.pause();
    }
    notifyContentScript('paused');
  }
}

// Stop reading
function stopReading() {
  // Cancel any in-flight synthesis immediately.
  abortActiveTts('stopped');

  // Mark as stopped immediately to prevent the sentence loop from advancing.
  readerState.isReading = false;
  readerState.isPaused = false;
  readerState.isWaitingForAudio = false;

  // Best-effort: also tell the active tab to stop audio immediately.
  try {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tabId = tabs?.[0]?.id;
      if (!tabId) return;
      chrome.tabs.sendMessage(tabId, { action: 'stopAudioNow' }).catch(() => {});
    });
  } catch (_) {}

  // Immediately unblock any pending wait on the current sentence audio.
  if (activePlaybackWaiter) {
    const waiter = activePlaybackWaiter;
    activePlaybackWaiter = null;

    try { chrome.runtime.onMessage.removeListener(waiter.listener); } catch (_) {}

    // Tell the tab that is actually playing audio to stop NOW.
    if (waiter.tabId) {
      try {
        chrome.tabs.sendMessage(waiter.tabId, { action: 'stopAudioNow' }).catch(() => {});
        chrome.tabs.sendMessage(waiter.tabId, {
          action: 'readerEvent',
          event: 'stopped',
          data: {}
        }).catch(() => {});
      } catch (_) {}
    }

    // Clear timing so we don't count the rest of the chunk.
    readerState.audioStartTime = 0;
    readerState.currentAudioDuration = 0;
    readerState.isWaitingForAudio = false;

    // Resolve the awaited playAudioInContent() so readNextSentence() can exit.
    try { waiter.resolve(); } catch (_) {}
  }

  currentSentenceIndex = 0;
  allSentences = [];
  readerState.totalSentences = 0;
  readerState.currentPosition = 0;
  readerState.currentTime = 0;
  readerState.totalTime = 0;
  readerState.audioStartTime = 0;
  readerState.currentAudioDuration = 0;
  readerState.baseWordsPerSecond = null;
  readerState.baseSpeed = null;
  readerState.recentSentences = [];
  readerState.totalWordsRead = 0;
  readerState.totalActualTime = 0;

  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }

  notifyContentScript('stopped');
}

// Skip to next sentence
function skipToNextSentence() {
  console.log('[Mockingbird] skipToNextSentence called');
  if (!readerState.isReading) return;

  // Cancel any in-progress TTS request
  abortActiveTts('skipped to next');
  
  // Cancel any waiting audio playback
  if (activePlaybackWaiter) {
    // Remove the listener to prevent leaks
    if (activePlaybackWaiter.listener) {
      try { chrome.runtime.onMessage.removeListener(activePlaybackWaiter.listener); } catch (_) {}
    }
    try {
      activePlaybackWaiter.reject?.(new Error('Skipped to next sentence'));
    } catch (e) {
      // Ignore
    }
    activePlaybackWaiter = null;
  }

  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }

  currentSentenceIndex++;
  if (currentSentenceIndex >= allSentences.length) {
    stopReading();
  } else {
    readNextSentence();
  }
}

// Skip to previous sentence
function skipToPreviousSentence() {
  console.log('[Mockingbird] skipToPreviousSentence called');
  if (!readerState.isReading) return;

  // Cancel any in-progress TTS request
  abortActiveTts('skipped to previous');
  
  // Cancel any waiting audio playback
  if (activePlaybackWaiter) {
    if (activePlaybackWaiter.listener) {
      try { chrome.runtime.onMessage.removeListener(activePlaybackWaiter.listener); } catch (_) {}
    }
    try {
      activePlaybackWaiter.reject?.(new Error('Skipped to previous sentence'));
    } catch (e) {
      // Ignore
    }
    activePlaybackWaiter = null;
  }

  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }

  currentSentenceIndex = Math.max(0, currentSentenceIndex - 1);
  readNextSentence();
}

// Notify content script of state changes
function notifyContentScript(event, data = {}) {
  const message = {
    action: 'readerEvent',
    event: event,
    data: data
  };
  
  // Send to active tab (content script)
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]) {
      chrome.tabs.sendMessage(tabs[0].id, message).catch(() => {
        // Content script might not be ready
      });
    }
  });
  
  // Also broadcast to side panel and other extension contexts
  chrome.runtime.sendMessage(message).catch(() => {
    // Side panel might not be open
  });
}

// Set sleep timer
function setSleepTimer(minutes) {
  cancelSleepTimer();
  
  readerState.sleepTimer = setTimeout(() => {
    stopReading();
    notifyContentScript('notification', { message: 'Sleep timer ended - reading stopped' });
    readerState.sleepTimer = null;
  }, minutes * 60 * 1000);
  
  notifyContentScript('notification', { message: `Sleep timer set for ${minutes} minutes` });
}

// Cancel sleep timer
function cancelSleepTimer() {
  if (readerState.sleepTimer) {
    clearTimeout(readerState.sleepTimer);
    readerState.sleepTimer = null;
    notifyContentScript('notification', { message: 'Sleep timer cancelled' });
  }
}

// Skip forward by time
function skipTimeForward(seconds) {
  if (!readerState.isReading) return;
  
  // Calculate how many sentences to skip based on average reading speed
  const avgSecondsPerSentence = 4; // rough estimate
  const sentencesToSkip = Math.ceil(seconds / avgSecondsPerSentence);
  
  currentSentenceIndex = Math.min(
    allSentences.length - 1,
    currentSentenceIndex + sentencesToSkip
  );
  
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  
  readNextSentence();
}

// Skip backward by time
function skipTimeBackward(seconds) {
  if (!readerState.isReading) return;
  
  const avgSecondsPerSentence = 4;
  const sentencesToSkip = Math.ceil(seconds / avgSecondsPerSentence);
  
  currentSentenceIndex = Math.max(0, currentSentenceIndex - sentencesToSkip);
  
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  
  readNextSentence();
}

// Jump to percentage
function jumpToPercentage(percentage) {
  if (!readerState.isReading || allSentences.length === 0) return;
  
  currentSentenceIndex = Math.floor((percentage / 100) * allSentences.length);
  currentSentenceIndex = Math.max(0, Math.min(allSentences.length - 1, currentSentenceIndex));
  
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  
  readNextSentence();
}

// ===== Sentence Batching =====
function batchShortSentences(sentences) {
  const batched = [];
  let currentBatch = '';
  
  for (const sentence of sentences) {
    const trimmed = sentence.trim();
    if (!trimmed) continue;
    
    // If sentence is long enough or batch is getting full, flush batch
    if (trimmed.length >= MIN_SENTENCE_LENGTH * 3 || 
        (currentBatch && (currentBatch.length + trimmed.length) > MIN_SENTENCE_LENGTH * 5)) {
      if (currentBatch) {
        batched.push(currentBatch.trim());
        currentBatch = '';
      }
      batched.push(trimmed);
    } else {
      // Add to current batch
      currentBatch += (currentBatch ? ' ' : '') + trimmed;
      
      // Flush if batch is big enough
      if (currentBatch.length >= MIN_SENTENCE_LENGTH * 3) {
        batched.push(currentBatch.trim());
        currentBatch = '';
      }
    }
  }
  
  // Flush remaining batch
  if (currentBatch) {
    batched.push(currentBatch.trim());
  }
  
  return batched;
}

// ===== OCR Functions =====

let offscreenDocumentReady = false;

async function ensureOffscreenDocument() {
  if (offscreenDocumentReady) return true;

  try {
    const existingContexts = await chrome.runtime.getContexts({
      contextTypes: ['OFFSCREEN_DOCUMENT'],
      documentUrls: [chrome.runtime.getURL('offscreen/offscreen.html')]
    });

    if (existingContexts.length > 0) {
      offscreenDocumentReady = true;
      return true;
    }

    await chrome.offscreen.createDocument({
      url: 'offscreen/offscreen.html',
      reasons: ['WORKERS'],
      justification: 'OCR processing with Tesseract.js in an offscreen document'
    });

    offscreenDocumentReady = true;
    await new Promise(resolve => setTimeout(resolve, 250));
    return true;
  } catch (error) {
    console.error('[Mockingbird OCR] Failed to create offscreen document:', error);
    return false;
  }
}

function sendMessageWithTimeout(message, timeoutMs = 60000) {
  return new Promise((resolve, reject) => {
    let done = false;
    const timer = setTimeout(() => {
      done = true;
      reject(new Error('OCR processing timed out'));
    }, timeoutMs);

    chrome.runtime
      .sendMessage(message)
      .then(response => {
        if (done) return;
        clearTimeout(timer);
        resolve(response);
      })
      .catch(err => {
        if (done) return;
        clearTimeout(timer);
        reject(err);
      });
  });
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

// Convert a data URL (data:mime[;base64],...) into a Blob without using fetch().
// Service workers can throw "TypeError: Failed to fetch" for fetch(data:...).
function dataUrlToBlob(dataUrl) {
  if (typeof dataUrl !== 'string' || !dataUrl.startsWith('data:')) {
    throw new Error('Expected a data URL');
  }

  const commaIdx = dataUrl.indexOf(',');
  if (commaIdx === -1) {
    throw new Error('Invalid data URL');
  }

  const meta = dataUrl.slice(0, commaIdx);
  const data = dataUrl.slice(commaIdx + 1);

  const isBase64 = /;base64/i.test(meta);
  const mimeMatch = /^data:([^;]+)/i.exec(meta);
  const mime = mimeMatch?.[1] || 'application/octet-stream';

  let bytes;
  if (isBase64) {
    const binary = atob(data);
    bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
  } else {
    const text = decodeURIComponent(data);
    bytes = new TextEncoder().encode(text);
  }

  return new Blob([bytes], { type: mime });
}

async function fetchImageAsDataUrl(imageUrl) {
  const response = await fetch(imageUrl);
  if (!response.ok) throw new Error(`Failed to fetch image: ${response.status}`);
  const blob = await response.blob();
  return await blobToDataUrl(blob);
}

async function cropImage(dataUrl, selection) {
  // Avoid fetch(data:...) in service worker; decode manually.
  const blob = dataUrlToBlob(dataUrl);
  const bitmap = await createImageBitmap(blob);

  // Convert selection (CSS pixels in viewport) to bitmap pixels.
  // Using bitmap/viewport scaling is more reliable than devicePixelRatio alone.
  let scaleX = 1;
  let scaleY = 1;
  if (selection?.viewportWidth && selection?.viewportHeight) {
    scaleX = bitmap.width / selection.viewportWidth;
    scaleY = bitmap.height / selection.viewportHeight;
  } else {
    const dpr = selection?.dpr || 1;
    scaleX = dpr;
    scaleY = dpr;
  }

  let sx = Math.round((selection?.left || 0) * scaleX);
  let sy = Math.round((selection?.top || 0) * scaleY);
  let sw = Math.round((selection?.width || 1) * scaleX);
  let sh = Math.round((selection?.height || 1) * scaleY);

  // Clamp to bitmap bounds
  sx = Math.max(0, Math.min(sx, bitmap.width - 1));
  sy = Math.max(0, Math.min(sy, bitmap.height - 1));
  sw = Math.max(1, Math.min(sw, bitmap.width - sx));
  sh = Math.max(1, Math.min(sh, bitmap.height - sy));

  const canvas = new OffscreenCanvas(sw, sh);
  const ctx = canvas.getContext('2d');
  ctx.drawImage(bitmap, sx, sy, sw, sh, 0, 0, sw, sh);

  const outBlob = await canvas.convertToBlob({ type: 'image/png' });
  return await blobToDataUrl(outBlob);
}

async function performLocalOCR(imageDataUrl, language = 'eng') {
  const ok = await ensureOffscreenDocument();
  if (!ok) throw new Error('Local OCR unavailable (offscreen document could not be created)');

  const response = await sendMessageWithTimeout(
    {
      type: 'OCR_PROCESS',
      imageData: imageDataUrl,
      language
    },
    60000
  );

  if (!response?.success) {
    const detail = response?.error ? String(response.error) : 'No error details from offscreen OCR';
    throw new Error(`OCR failed: ${detail}`);
  }

  return response.result;
}

async function handleOCRRequest(imageUrl, tabId) {
  try {
    const settings = await chrome.storage.local.get(['ocrLanguage', 'ocrAutoRead']);
    const language = settings.ocrLanguage || 'eng';
    const autoRead = !!settings.ocrAutoRead;

    const imageDataUrl = await fetchImageAsDataUrl(imageUrl);
    const result = await performLocalOCR(imageDataUrl, language);

    chrome.runtime.sendMessage({
      type: 'OCR_RESULT',
      result,
      image: imageDataUrl,
      tabId
    }).catch(() => {});

    if (autoRead && result?.text?.trim()) {
      startReading(result.text);
    }
  } catch (error) {
    chrome.runtime.sendMessage({
      type: 'OCR_ERROR',
      error: error.message || 'OCR processing failed',
      tabId
    }).catch(() => {});
  }
}

async function handleOCRCapture(selection, tabId) {
  try {
    const settings = await chrome.storage.local.get(['ocrLanguage', 'ocrAutoRead']);
    const language = settings.ocrLanguage || 'eng';
    const autoRead = !!settings.ocrAutoRead;

    const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'png' });
    const cropped = await cropImage(dataUrl, selection);
    const result = await performLocalOCR(cropped, language);

    chrome.runtime.sendMessage({
      type: 'OCR_RESULT',
      result,
      image: cropped,
      tabId
    }).catch(() => {});

    if (autoRead && result?.text?.trim()) {
      startReading(result.text);
    }

    // Content-script overlay expects text/image for local storage + any UI.
    return {
      success: true,
      text: result?.text || '',
      image: cropped,
      confidence: result?.confidence ?? 0
    };
  } catch (error) {
    chrome.runtime.sendMessage({
      type: 'OCR_ERROR',
      error: error.message || 'OCR capture failed',
      tabId
    }).catch(() => {});
    return { success: false, error: error.message };
  }
}
