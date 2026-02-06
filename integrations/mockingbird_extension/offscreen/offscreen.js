/**
 * Mockingbird Browser Extension - Offscreen OCR Processor
 * Licensed under the MIT License.
 * Copyright (c) 2026 PiperTTS Mockingbird Developers
 */

console.log('[Mockingbird OCR] Offscreen document loaded');

let tesseractWorker = null;
let currentLanguage = null;
let isInitializing = false;

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

async function createSelfTestImageDataUrl(text = 'TEST 123') {
  const width = 520;
  const height = 160;

  // Prefer OffscreenCanvas (works in offscreen documents) but fall back to DOM canvas.
  if (typeof OffscreenCanvas !== 'undefined') {
    const canvas = new OffscreenCanvas(width, height);
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = '#000000';
    ctx.font = 'bold 64px Arial';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, 20, Math.floor(height / 2));

    const blob = await canvas.convertToBlob({ type: 'image/png' });
    return await blobToDataUrl(blob);
  }

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = '#000000';
  ctx.font = 'bold 64px Arial';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 20, Math.floor(height / 2));
  return canvas.toDataURL('image/png');
}

function cleanupText(text) {
  if (!text) return '';
  return text
    .replace(/\n\s*\n\s*\n/g, '\n\n')
    .replace(/[ \t]+/g, ' ')
    .replace(/^\s+|\s+$/gm, '')
    .trim();
}

async function initTesseract(language = 'eng') {
  if (tesseractWorker && currentLanguage === language) {
    return tesseractWorker;
  }

  if (isInitializing) {
    while (isInitializing) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    if (tesseractWorker && currentLanguage === language) return tesseractWorker;
  }

  try {
    isInitializing = true;

    if (tesseractWorker) {
      try {
        await tesseractWorker.terminate();
      } catch {}
      tesseractWorker = null;
      currentLanguage = null;
    }

    if (typeof Tesseract === 'undefined') {
      throw new Error('Tesseract library not loaded');
    }

    console.log('[Mockingbird OCR] Initializing Tesseract worker...');

    tesseractWorker = await Tesseract.createWorker(language, 1, {
      logger: (m) => {
        if (m?.status === 'recognizing text') {
          chrome.runtime.sendMessage({ type: 'OCR_PROGRESS', progress: m.progress }).catch(() => {});
        }
      },
      // MV3/offscreen can be finicky with Blob workers + importScripts().
      // Force a normal Worker(workerPath) to avoid "importScripts ... worker.min.js failed to load".
      workerBlobURL: false,
      workerPath: chrome.runtime.getURL('offscreen/worker.min.js'),
      corePath: chrome.runtime.getURL('offscreen/tesseract-core.wasm.js'),
      langPath: 'https://tessdata.projectnaptha.com/4.0.0'
    });

    currentLanguage = language;
    console.log('[Mockingbird OCR] Tesseract worker ready');
    return tesseractWorker;
  } finally {
    isInitializing = false;
  }
}

async function performOCR(imageDataUrl, language = 'eng') {
  console.log('[Mockingbird OCR] Starting OCR processing...');
  const worker = await initTesseract(language);
  const { data } = await worker.recognize(imageDataUrl);

  return {
    text: cleanupText(data?.text || ''),
    rawText: data?.text || '',
    confidence: data?.confidence ?? 0,
    language
  };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === 'OCR_SELF_TEST') {
    const { language = 'eng' } = message;
    (async () => {
      const imageDataUrl = await createSelfTestImageDataUrl('TEST 123');
      const result = await performOCR(imageDataUrl, language);
      const recognized = (result?.text || '').toUpperCase();
      const ok = recognized.includes('TEST') || recognized.includes('123');

      return {
        success: true,
        ok,
        expected: 'TEST 123',
        recognized: result?.text || '',
        confidence: result?.confidence ?? 0,
        language
      };
    })()
      .then(sendResponse)
      .catch(error => {
        const msg = (error && typeof error === 'object' && 'message' in error && error.message)
          ? error.message
          : String(error);
        console.error('[Mockingbird OCR] OCR_SELF_TEST failed:', error);
        sendResponse({ success: false, error: msg || 'OCR self-test failed' });
      });
    return true;
  }

  if (message?.type === 'OCR_PROCESS') {
    const { imageData, language = 'eng' } = message;
    performOCR(imageData, language)
      .then(result => sendResponse({ success: true, result }))
      .catch(error => {
        const msg = (error && typeof error === 'object' && 'message' in error && error.message)
          ? error.message
          : String(error);
        console.error('[Mockingbird OCR] OCR_PROCESS failed:', error);
        sendResponse({ success: false, error: msg || 'OCR failed' });
      });
    return true;
  }

  // Backwards compatibility (older message types)
  if (message?.type === 'PROCESS_OCR') {
    const { imageDataUrl, language = 'eng' } = message;
    performOCR(imageDataUrl, language)
      .then(result => sendResponse({ success: true, ...result }))
      .catch(error => {
        const msg = (error && typeof error === 'object' && 'message' in error && error.message)
          ? error.message
          : String(error);
        console.error('[Mockingbird OCR] PROCESS_OCR failed:', error);
        sendResponse({ success: false, error: msg || 'OCR failed' });
      });
    return true;
  }

  if (message?.type === 'OCR_TERMINATE' || message?.type === 'TERMINATE_OCR') {
    (async () => {
      if (tesseractWorker) {
        try {
          await tesseractWorker.terminate();
        } catch {}
        tesseractWorker = null;
        currentLanguage = null;
      }
    })()
      .then(() => sendResponse({ success: true }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }
});

console.log('[Mockingbird OCR] Offscreen ready');

