import { runPrimerOnce } from './src/primer-core.js';

(() => {
  const kickoff = () => { try { runPrimerOnce(); } catch (e) { console.error(e); } };
  if (document.readyState === 'complete' || document.readyState === 'interactive') kickoff();
  else window.addEventListener('DOMContentLoaded', kickoff, { once: true });
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') kickoff(); });
  window.addEventListener('pageshow', kickoff);
})();
