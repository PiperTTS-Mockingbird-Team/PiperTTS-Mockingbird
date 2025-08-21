import { logger } from '../utils/logger.js';
import { RuleIds } from '../background/rule-ids.js';

const log = logger('lockout');

// lockout.js — updated layout (reason chip in controls), custom message, buzzer autoplay

const params = new URLSearchParams(window.location.search);
log("🔍 [Lockout] orig-param =", params.get("orig"));
window.finishLockout = finishLockout;
log("🔑 finishLockout() is now available on window");

function startImageOnce() {
  const imageElement = document.getElementById("mascot");
  if (!imageElement) return;
  const images = ["doge.png", "cat.png"];
  const lastUsed = localStorage.getItem("lastImage");
  const available = images.filter(img => img !== lastUsed);
  const chosen = available[Math.floor(Math.random() * available.length)] || images[0];
  imageElement.src = chrome.runtime.getURL(`assets/images/${chosen}`);
  localStorage.setItem("lastImage", chosen);
}

async function finishLockout() {
  const { lockoutUntil = 0 } = await chrome.storage.local.get("lockoutUntil");
  if (Date.now() < lockoutUntil) {
    console.warn("🔁 Still locked out—no redirect yet.");
    return;
  }
  try {
    await manageDynamicRules('clear');
    await chrome.declarativeNetRequest.updateEnabledRulesets({
      disableRulesetIds: ["block-chatgpt"]
    });
  } catch (err) {
    console.warn("Lockout cleanup failed:", err);
  }

  await chrome.storage.local.remove("lockoutUntil");
  await chrome.storage.local.remove("lockoutReason");

  const { getRedirectTarget } = await import("./redirector.js");

  setTimeout(async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const orig = urlParams.get("orig") || "";
    const tabId = urlParams.get("tabId");
    const target = await getRedirectTarget(orig, tabId);

    if (target) {
      log("Redirecting to:", target);
      try {
        const settings = await chrome.storage.local.get([
          "insertOnRedirect", "redirectTemplate", "goal"
        ]);
        const insert = settings.insertOnRedirect ?? true;
        if (insert && target && (target.includes("chat.openai.com") || target.includes("chatgpt.com"))) {
          const goal = settings.goal || "MCAT";
          const tmpl = settings.redirectTemplate || "My current goal is: {goal}";
          const msg  = tmpl.replaceAll("{goal}", goal);
          await chrome.storage.local.set({
            primedMessage: msg,
            redirectPriming: true,
            primeExpiresAt: Date.now() + 120_000
          });
        }
      } catch (e) {
        console.warn("Priming message setup failed:", e);
      }
      window.location.href = target;
    } else {
      console.warn("No redirect target found — using history.back()");
      window.history.back();
    }
  }, 100);
}

async function initLockoutInfo() {
  const { lockoutUntil = 0, goal = "Stay focused" } =
    await chrome.storage.local.get(["lockoutUntil", "goal"]);
  const goalEl = document.getElementById("goal");
  if (goalEl) goalEl.textContent = "Your current goal: " + goal;

  const reasonEl = document.getElementById("reason");
  const messageEl = document.getElementById("customMessage");

  // Reason chip
  const { lockoutReason = "" } = await chrome.storage.local.get("lockoutReason");
  if (lockoutReason && reasonEl) {
    reasonEl.textContent = lockoutReason;
    reasonEl.hidden = false;
  }

  // Accountability Intervention banner (kept simple in the chip area)
  try {
    if (lockoutReason === "Accountability Intervention" && reasonEl) {
      const { blockLimit = "X", blockWindowMinutes = "Y" } =
        await chrome.storage.local.get(["blockLimit","blockWindowMinutes"]); 
      reasonEl.textContent =
        `Accountability Intervention — ${blockLimit} blocks in ${blockWindowMinutes} min triggered a longer lock.`;
      reasonEl.hidden = false;
    }
  } catch (e) { console.warn("AI banner setup failed", e); }

  // Custom lockout message → goes into the card
  try {
    const { lockoutCustomText = "" } = await chrome.storage.local.get("lockoutCustomText");
    if (messageEl) {
      messageEl.textContent = lockoutCustomText
        ? lockoutCustomText
        : "Stay focused—back to your task when the timer ends.";
    }
  } catch (e) { console.warn("lockoutCustomText fetch failed", e); }

  // Timer
  const timerEl = document.getElementById("timer");
  function updateTimer() {
    const msLeft = lockoutUntil - Date.now();
    const totalSecs = Math.max(0, Math.ceil(msLeft / 1000));
    const mins = Math.floor(totalSecs / 60);
    const secs = String(totalSecs % 60).padStart(2, "0");

    if (msLeft <= 0) {
      timerEl.textContent = "✅ Lockout’s over — taking you back!";
      clearInterval(intervalId);
      setTimeout(finishLockout, 1500);
    } else {
      timerEl.textContent = `Time remaining: ${mins}:${secs}`;
    }
  }
  updateTimer();
  const intervalId = setInterval(updateTimer, 1000);
}

// Buzzer autoplay with graceful fallback
async function playBuzzer() {
  const el = document.getElementById("buzzer");
  if (!el) return;
  try {
    await el.play();
    log("🔊 Buzzer played.");
  } catch (err) {
    console.warn("Autoplay blocked. Showing Play button.", err);
    const btn = document.getElementById("playSoundBtn");
    if (btn) btn.style.display = "inline-block";
  }
}

function showToast(message) {
  if (typeof window !== 'undefined' && typeof window.toast === 'function') {
    window.toast(message);
  } else {
    console.log(message);
  }
}

export async function clearNow() {
  const ids = await RuleIds.getActive('lockout');
  if (ids.length === 0) {
    showToast('No rules to clear.');
    return;
  }
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await RuleIds.updateDynamicRules({ removeRuleIds: ids });
      await RuleIds.setActive('lockout', []);
      showToast('Cleared lockout rules.');
      return;
    } catch (err) {
      if (attempt === 2) throw err;
      await new Promise(res => setTimeout(res, 100));
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  startImageOnce();
  initLockoutInfo();
  playBuzzer();

  const playBtn = document.getElementById("playSoundBtn");
  if (playBtn) playBtn.addEventListener("click", playBuzzer);

  const dbg = document.getElementById("debugBtn");
  if (dbg) {
    dbg.addEventListener("click", async () => {
      const { lockoutUntil = 0 } = await chrome.storage.local.get("lockoutUntil");
      if (Date.now() < lockoutUntil) {
        alert("⛔ You're still in the lockout period.\nWait until the timer ends.");
        return;
      }
      log("🛠️ Debug button pressed");
      dbg.disabled = true;
      const originalText = dbg.textContent;
      dbg.textContent = "⏳ Clearing…";
      clearNow();
      dbg.textContent = "✅ Cleared";
      alert("✅ Block cleared. You can reload the page now.");
      setTimeout(() => {
        dbg.textContent = originalText;
        dbg.disabled = false;
      }, 1500);
    });
  }
});
