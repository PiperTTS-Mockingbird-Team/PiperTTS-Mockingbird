import { logger } from './logger.js';

const log = logger('content');

export function insertText(el, text) {
  if (!el) return;
  try { el.focus(); } catch {}
  const isCE = el.isContentEditable || el.getAttribute?.('contenteditable') === 'true';
  if (isCE) {
    try {
      document.execCommand('insertText', false, text);
    } catch {
      el.textContent = text;
      el.dispatchEvent(
        new InputEvent('input', { bubbles: true, data: text, inputType: 'insertText' })
      );
    }
    el.dispatchEvent(new Event('input', { bubbles: true }));
  } else if ('value' in el) {
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    el.value = el.value.slice(0, start) + text + el.value.slice(end);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }
}

export function sendMessage(el) {
  const root = el.closest('form') || document;
  const q = (s) => root.querySelector(s);
  const btn =
    q("button[data-testid='send-button']") ||
    q("button[aria-label*='Send' i]") ||
    q("button[type='submit']") ||
    (q("svg[aria-label*='Send' i],svg[aria-label*='submit' i]")?.closest('button'));

  if (btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
    try { btn.click(); } catch {}
    return true;
  }

  if (el.isContentEditable) {
    ['keydown','keypress','keyup'].forEach(type =>
      el.dispatchEvent(
        new KeyboardEvent(type, {
          key: 'Enter',
          code: 'Enter',
          which: 13,
          keyCode: 13,
          bubbles: true,
        })
      )
    );
    return true;
  }

  if (root && typeof root.requestSubmit === 'function') {
    root.requestSubmit();
    return true;
  }

  return false;
}

export async function typeAndSend(el, text) {
  const existing = el.isContentEditable
    ? (el.textContent || '').trim()
    : (('value' in el ? el.value : '') || '').trim();
  const placeholder = (
    el.getAttribute('placeholder') ||
    el.getAttribute('data-placeholder') ||
    ''
  ).trim();
  if (existing && existing !== placeholder) {
    log('existing text differs, skipping');
    return false;
  }
  insertText(el, text);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  await sendMessage(el);
  return true;
}

export function waitForComposer({ timeout = 60000 } = {}) {
  const selectors = [
    'textarea[placeholder]',
    '[data-testid="composer"]',
    '[data-id="composer"]',
    'main [contenteditable="true"], form [contenteditable="true"], [role="main"] [contenteditable="true"]'
  ];
  return new Promise((resolve) => {
    const tryFind = () => {
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el) {
          console.log('[primer] FOUND via', sel);
          resolve(el);
          return true;
        }
      }
      return false;
    };
    if (tryFind()) return;
    const observer = new MutationObserver(() => {
      if (tryFind()) observer.disconnect();
    });
    observer.observe(document.documentElement || document.body, {
      childList: true,
      subtree: true,
    });
    setTimeout(() => {
      observer.disconnect();
      resolve(null);
    }, timeout);
  });
}
