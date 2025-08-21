import { waitForComposer, typeAndSend } from '../utils/primer-core.js';

(async () => {
  const getTabId = () => new Promise(resolve => {
    chrome.runtime.sendMessage({ type: 'PRIMER_GET_TAB_ID' }, (res) => resolve(res?.tabId));
  });

  const tabId = await getTabId();
  const host = location.host;
  chrome.runtime.sendMessage({ type: 'PRIMER_READY', tabId, host });

  chrome.runtime.onMessage.addListener(async (msg) => {
    if (msg.type !== 'PRIMER_PAYLOAD') return;
    const el = await waitForComposer({ timeout: 60000 });
    if (!el) {
      console.log('[primer] TIMEOUT waiting for composer');
      return;
    }
    console.log('[primer] TYPE/ENTER start');
    const ok = await typeAndSend(el, msg.primedMessage);
    console.log('[primer] TYPE/ENTER end');
    if (ok) {
      chrome.runtime.sendMessage({ type: 'PRIMER_DONE', tabId });
    }
  });
})();
