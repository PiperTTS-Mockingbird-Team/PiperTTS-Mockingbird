import { setBadge } from './badge.js';

export async function resetFocusModeOnStartup(storage = chrome.storage.local) {
  const {
    resetFocusOnRestart = true,
    focusMode, // read existing value so it can be preserved when flag is false
    score = 5
  } = await storage.get(["resetFocusOnRestart", "focusMode", "score"]);

  if (resetFocusOnRestart) {
    await storage.set({ focusMode: "onAllDay" });
  } else {
    // keeping stored focusMode (value already read above)
  }

  await setBadge(score, storage);
}
