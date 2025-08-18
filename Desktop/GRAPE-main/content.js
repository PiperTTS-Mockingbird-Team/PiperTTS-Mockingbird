import { log } from './src/logger.js';

// content.js
log("✅ Clean content.js loaded");

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "getSnippet") {
    chrome.storage.local.get({
      charLimit: 1000,
      focusMode: "onAllDay",
      focusPhaseMode: null,
      focusPhaseStart: 0,
      G: 5,
    }, ({ charLimit, focusMode, focusPhaseMode, focusPhaseStart, G }) => {
      log("📩 getSnippet received");

      // Handle focus mode logic
      if (focusMode === "off") {
        sendResponse({ snippet: "[Focus mode is off]" });
        return;
      }

      if (focusMode === "cycle" && focusPhaseMode === "cycle") {
        const now = Date.now();
        const relaxMs = parseFloat(G || 5) * 60 * 1000;
        if (now < focusPhaseStart + relaxMs) {
          sendResponse({ snippet: "[In relax phase]" });
          return;
        }
      }

        // Poll for content a few times; a MutationObserver could replace polling later
      let attempts = 0;
      const maxAttempts = 5;
      const delay = 400; // ms

      function tryCollectSnippet() {
        const els = Array.from(document.querySelectorAll('.markdown.prose'));
        const texts = els.map(el => el.innerText.trim()).filter(Boolean);

        if (texts.length > 0) {
          const raw = texts.join(' ');
          const snippet = raw.slice(-charLimit);
          log("📦 Snippet collected:", snippet.slice(0, 80) + "...");
          sendResponse({ snippet });
        } else if (++attempts < maxAttempts) {
          console.warn(`⚠️ No content yet, retrying (${attempts})...`);
          setTimeout(tryCollectSnippet, delay);
        } else {
          console.error("❌ Gave up after retries");
          sendResponse({ snippet: "[No content found]" });
        }
      }

      tryCollectSnippet();
    });

    return true; // Keeps the message channel open for async response
  }

  if (request.action === "settingsUpdated") {
    chrome.storage.local.get([
      "charLimit", "gptScanInterval", "scanInterval", "blockDuration", "blockThreshold"
    ], (settings) => {
      log("🔧 Settings updated:", settings);
    });
  }
});

setInterval(async () => {
  const keys = [
    "score",
    "lockoutUntil",
    "focusMode",
    "manualUILockUntil",
    "focusPhaseMode",
    "focusPhaseStart",
    "G",
    "H"
  ];

  const data = await chrome.storage.local.get(keys);
  chrome.runtime.sendMessage({
    action: "refreshBadge",
    payload: data
  });
}, 2000);
