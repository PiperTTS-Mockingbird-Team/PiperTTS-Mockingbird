import { runPrimerOnce } from '../utils/primer-core.js';

(() => {
  const kickoff = () => {
    try {
      runPrimerOnce();
    } catch (e) {
      console.warn('primer: failed to run; ensure module import path and type are correct', e);
    }
  };
  if (document.readyState === 'complete' || document.readyState === 'interactive') kickoff();
  else window.addEventListener('DOMContentLoaded', kickoff, { once: true });
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') kickoff(); });
  window.addEventListener('pageshow', kickoff);
})();
