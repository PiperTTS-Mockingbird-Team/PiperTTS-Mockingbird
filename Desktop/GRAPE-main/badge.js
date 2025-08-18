// badge.js

export function badgeColor(score) {
  if (isNaN(score))          return '#9E9E9E'; // grey
  if (score >= 8)            return '#4CAF50'; // green
  if (score >= 5)            return '#FFEB3B'; // yellow
  if (score >= 0)            return '#FF9800'; // orange
  return '#F44336';                              // red
}

// ⬇️ Underlines badge when UI is manually locked
function underline(text) {
  return [...text].map(ch => ch + '\u0332').join('');
}

function focusModeEmoji(mode) {
  switch (mode) {
    case "off": return "🚫";
    case "onAllDay": return "🧠";
    case "timer": return "🕒";
    case "cycle": return "☕";
    case "cycleFocus": return "💼";
    default: return "❓";
  }
}

export async function setBadge(_ignoredScore, chromeStorage = chrome.storage.local) {
  // ── Enforcer: always read the true score from storage ──
  const { score: realScore = 5 } = await chromeStorage.get("score");
  const clampedScore = Math.max(-5, realScore);

  // ── Then read the other flags ──
  const {
    lockoutUntil = 0,
    focusMode = "onAllDay",
    manualUILockUntil = 0
  } = await chromeStorage.get([
    "lockoutUntil",
    "focusMode",
    "manualUILockUntil"
  ]);

  const now = Date.now();
  const isInLockout    = lockoutUntil    > now;
  const isManualLocked = manualUILockUntil > now;

  const icon = isInLockout ? "⛔" : focusModeEmoji(focusMode);

  const display = isManualLocked
    ? icon + underline(String(clampedScore))
    : icon + String(clampedScore);

  chrome.action.setBadgeBackgroundColor({
    color: isInLockout ? badgeColor(-1) : badgeColor(clampedScore)
  });

  chrome.action.setBadgeText({ text: display });
}


