// Core utilities for primer
// Extracted from primer.js for reuse and testing

import { log, isDebug } from './logger.js';

const INTERVAL_MS = 500;
const MAX_MS = 20000; // allow slow SPA mounts

// Tiny inline debug banner (optional, only when DEBUG=true)
const banner = (() => {
  if (!isDebug()) return { set: () => {}, show: () => {}, hide: () => {} };
  let el;
  const ensure = () => {
    if (el) return el;
    el = document.createElement('div');
    el.style.cssText = [
      'position:fixed','z-index:999999','top:6px','left:6px','padding:6px 8px','border-radius:8px',
      'font:12px/1.3 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto','background:rgba(0,0,0,.8)',
      'color:#fff','box-shadow:0 2px 8px rgba(0,0,0,.25)','pointer-events:none'
    ].join(';');
    el.textContent = 'primer: ready';
    document.documentElement.appendChild(el);
    return el;
  };
  return {
    set(msg){ ensure().textContent = `primer: ${msg}`; },
    show(){ ensure().style.display = 'block'; },
    hide(){ if (el) el.style.display = 'none'; }
  };
})();

export function getComposer() {
  return (
    document.querySelector('#prompt-textarea[contenteditable="true"], div[contenteditable="true"]#prompt-textarea') ||
    document.querySelector('textarea#prompt-textarea, textarea[aria-label*="Message" i]')
  );
}

export function insertText(el, text) {
  if (!el) return;

  try { el.focus(); } catch {}

  const isContentEditable =
    el.isContentEditable ||
    el.getAttribute?.('contenteditable') === 'true';

  if ('value' in el && !isContentEditable) {
    // For <input> / <textarea>
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    const before = el.value.slice(0, start);
    const after = el.value.slice(end);
    el.value = before + text + after;
  } else {
    // For <div contenteditable="true"> etc.
    el.textContent = (el.textContent || '') + text;
  }

  // Dispatch an input event so React/Vue/etc. notice the change
  el.dispatchEvent(new InputEvent('input', { bubbles: true }));
}


export function sendMessage(el) {
  const root = el.closest('form') || document;
  const q = (s) => root.querySelector(s);
  const buttonFinders = () => (
    q("button[data-testid='send-button']") ||
    q("button[aria-label*='Send' i]") ||
    q("button[type='submit']") ||
    (q("svg[aria-label*='Send' i],svg[aria-label*='submit' i]")?.closest('button'))
  );

  let waited = 0;
  return new Promise((resolve) => {
    const interval = setInterval(() => {
      const btn = buttonFinders();
      if (btn) {
        const ariaDis = btn.getAttribute('aria-disabled');
        if (!btn.disabled && ariaDis !== 'true') {
          clearInterval(interval);
          setTimeout(() => { try { btn.click(); } catch {} resolve(true); }, 20);
          return;
        }
      }
      waited += 100;
      if (waited >= 2000) {
        clearInterval(interval);
        if (el.isContentEditable) {
          ['keydown','keypress','keyup'].forEach(type =>
            el.dispatchEvent(new KeyboardEvent(type, { key:'Enter', code:'Enter', which:13, keyCode:13, bubbles:true }))
          );
          resolve(true);
        } else if (root && typeof root.requestSubmit === 'function') {
          root.requestSubmit();
          resolve(true);
        } else {
          resolve(false);
        }
      }
    }, 100);
  });
}

export async function _typeAndSend(el, text, originalPrimed) {
  const existing = el.isContentEditable
    ? (el.textContent || '').trim()
    : (('value' in el ? el.value : '') || '').trim();

  if (existing && existing !== String(originalPrimed || '').trim()) {
    chrome.storage.local.remove(['primedMessage', 'redirectPriming', 'primeExpiresAt']);
    banner.set('skipped (user typed)');
    return true;
  }

  insertText(el, text);
  banner.set('inserted, waiting send');
  try { el.focus(); } catch {}
  el.dispatchEvent(new Event('input', { bubbles: true }));
  const ok = await sendMessage(el);
  return ok;
}

export let typeAndSend = _typeAndSend;
export function __setTypeAndSend(fn) { typeAndSend = fn; }

export async function runPrimerOnce() {
  const fresh = new URLSearchParams(location.search).get('fresh') || String(Math.floor(performance.timeOrigin));
  const ranKey = `primer_ran:${location.pathname}:${fresh}`;

  if (sessionStorage.getItem(ranKey) === '1') { log('already ran for this path+fresh'); return; }

  const { primedMessage, redirectPriming, primeExpiresAt, goal, primingGraceUntil, lastPrimedMessage } = await chrome.storage.local.get([
    'primedMessage','redirectPriming','primeExpiresAt','goal','primingGraceUntil','lastPrimedMessage'
  ]);

  const now = Date.now();
  let _redirectPriming = redirectPriming;
  let _primedMessage = primedMessage;

  if ((!_redirectPriming || !_primedMessage) && primingGraceUntil && now < primingGraceUntil && lastPrimedMessage) {
    await chrome.storage.local.set({ primedMessage: lastPrimedMessage, redirectPriming: true });
    _redirectPriming = true;
    _primedMessage = lastPrimedMessage;
    banner.set('grace priming active');
  }

  if (!_redirectPriming || !_primedMessage) { log('nothing to do'); return; }

  if (primeExpiresAt && now > primeExpiresAt) {
    await chrome.storage.local.remove(['primedMessage','redirectPriming','primeExpiresAt']);
    log('expired priming dropped');
    return;
  }

  const finalMessage = String(_primedMessage).replace('{goal}', goal || '');

  banner.show();
  banner.set('waiting for composer…');

  let elapsed = 0;
  const timer = setInterval(async () => {
    elapsed += INTERVAL_MS;
    const el = getComposer();
    if (el) {
      banner.set('composer found');
      const ok = await typeAndSend(el, finalMessage, finalMessage);
      if (ok) {
        clearInterval(timer);
        sessionStorage.setItem(ranKey, '1');
        try {
          // Grace period starts *now*, when priming was successfully inserted/sent
          await chrome.storage.local.set({ primingGraceUntil: Date.now() + 60_000, lastPrimedMessage: finalMessage });
        } catch {}
        chrome.storage.local.remove(['primedMessage','redirectPriming','primeExpiresAt']);
        banner.set('sent ✅');
        setTimeout(() => banner.hide(), 800);
        return;
      }
    }
    if (elapsed >= MAX_MS) {
      clearInterval(timer);
      sessionStorage.setItem(ranKey, '1');
      chrome.storage.local.remove(['primedMessage','primeExpiresAt']);
      chrome.storage.local.set({ redirectPriming: false });
      banner.set('timeout ⏰');
      log('primer timeout');
      setTimeout(() => banner.hide(), 1200);
    }
  }, INTERVAL_MS);
}
