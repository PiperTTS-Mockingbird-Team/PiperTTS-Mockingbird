// content.js
// Inline logging helper and robust snippet collection for ChatGPT pages.

console.log('[GRAPE] content script alive', location.href);

let debugEnabled = false;
let debugSnippet = false;

chrome.storage.local.get({ debug: {}, debugSnippet: false }, ({ debug, debugSnippet: ds }) => {
  debugEnabled = !!(debug?.content || debug?.all);
  debugSnippet = !!ds;
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== 'local') return;
  if ('debug' in changes) {
    const dbg = changes.debug.newValue;
    debugEnabled = !!(dbg?.content || dbg?.all);
  }
  if ('debugSnippet' in changes) debugSnippet = !!changes.debugSnippet.newValue;
});

function log(...args) {
  if (debugEnabled) console.log('[grape]', ...args);
}

let currentCharLimit = 1000;
let latestSnippet = '';

function isVisible(el) {
  return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
}

function getChatGPTSnippet(charLimit) {
  const main = document.querySelector('main');
  if (!main) return '';

  const convSelectors = [
    '.prose',
    '.markdown',
    '[data-message-author-role]',
    'article',
    'div[data-testid="conversation-turn"]'
  ];

  const inputSelectors = [
    'textarea#prompt-textarea',
    'textarea[placeholder*="Message" i]',
    'div[contenteditable="true"][data-lexical-editor]'
  ];

  const selectors = convSelectors.concat(inputSelectors).join(',');
  const els = Array.from(main.querySelectorAll(selectors));

  const parts = [];
  for (const el of els) {
    if (!isVisible(el)) continue;
    if (el.closest('aside, [role="complementary"], [data-testid*="side"]')) continue;
    const text = el.innerText || el.textContent || '';
    if (text) parts.push(text.trim());
  }

  let text = parts.join(' ');
  if (!text) text = main.innerText || '';

  text = text
    .toLowerCase()
    .replace(/[\u200B-\u200D\uFEFF]/g, '')
    .replace(/\s+/g, ' ')
    .trim();

  const limit = Math.max(charLimit || 0, 120);
  return text.slice(-limit);
}

function updateSnippet() {
  latestSnippet = getChatGPTSnippet(currentCharLimit);
}

let throttleTimer = null;
const observer = new MutationObserver(() => {
  if (throttleTimer) return;
  throttleTimer = setTimeout(() => {
    throttleTimer = null;
    updateSnippet();
  }, 200);
});

function startObserver() {
  const main = document.querySelector('main');
  if (!main) return;
  observer.observe(main, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  updateSnippet();
}

if (document.readyState === 'loading') {
  window.addEventListener('DOMContentLoaded', startObserver);
} else {
  startObserver();
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getSnippet') {
    chrome.storage.local.get({
      charLimit: 1000,
      focusMode: 'onAllDay',
      focusPhaseMode: null,
      focusPhaseStart: 0,
      G: 5,
    }, ({ charLimit, focusMode, focusPhaseMode, focusPhaseStart, G }) => {
      log('📩 getSnippet received');

      const { type = 'context' } = request;

      // ── status requests return short status strings ────────────
      if (type === 'status') {
        if (focusMode === 'off') {
          sendResponse({ snippet: '[Focus mode is off]' });
          return;
        }

        if (focusMode === 'cycle' && focusPhaseMode === 'cycle') {
          const now = Date.now();
          const relaxMs = parseFloat(G || 5) * 60 * 1000;
          if (now < focusPhaseStart + relaxMs) {
            sendResponse({ snippet: '[In relax phase]' });
            return;
          }
        }

        sendResponse({ snippet: '[Focus mode active]' });
        return;
      }

      // ── context requests gather real page text ────────────────
      currentCharLimit = charLimit;
      updateSnippet();

        if (latestSnippet) {
          if (debugSnippet) {
            log('📦 Context snippet:', latestSnippet.slice(0, 80) + '...');
          }
          sendResponse({ snippet: latestSnippet });
          return;
        }

      let attempts = 0;
      const maxAttempts = 4;
      const delay = 400; // ms
      let timeoutId = null;
      let done = false;

        const finish = (snippet) => {
          if (done) return;
          done = true;
          observer2.disconnect();
          if (timeoutId) clearTimeout(timeoutId);
          if (debugSnippet) {
            log('📦 Context snippet:', snippet.slice(0, 80) + '...');
          }
          sendResponse({ snippet });
        };

      const check = () => {
        attempts++;
        if (latestSnippet) {
          finish(latestSnippet);
        } else if (attempts < maxAttempts) {
          timeoutId = setTimeout(check, delay);
        } else {
          finish('');
        }
      };

      const observer2 = new MutationObserver(() => {
        if (latestSnippet) {
          finish(latestSnippet);
        }
      });

      const main = document.querySelector('main');
      if (main) {
        observer2.observe(main, {
          childList: true,
          subtree: true,
          characterData: true,
        });
      }

      timeoutId = setTimeout(check, delay);
    });

    return true; // Keeps the message channel open for async response
  }

  if (request.action === 'settingsUpdated') {
    chrome.storage.local.get([
      'charLimit', 'gptScanInterval', 'scanInterval', 'blockDuration', 'blockThreshold'
    ], (settings) => {
      log('🔧 Settings updated:', settings);
    });
  }
});

setInterval(async () => {
  const keys = [
    'score',
    'lockoutUntil',
    'focusMode',
    'manualUILockUntil',
    'focusPhaseMode',
    'focusPhaseStart',
    'G',
    'H'
  ];

  const data = await chrome.storage.local.get(keys);
  chrome.runtime.sendMessage({
    action: 'refreshBadge',
    payload: data
  });
}, 2000);

