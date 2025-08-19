import { log, isDebug } from '../utils/logger.js';
import { formatTime } from '../utils/utils.js';

/****************************************************************
 * GPT Productivity Enforcer – background.js (MV3, ES-module)
 * - periodic alarms (poll, focusCheck, banned-word checks)
 * - pulls conversation snippets from content.js
 * - GPT API evaluates productivity
 * - updates score/badge and enforces dynamic block/lockout
 ****************************************************************/

log("🛠️ Service worker loaded");

// Debug: Log focus timing state on startup
chrome.storage.local.get(["focusPhaseMode", "focusPhaseStart", "D", "G", "H"], (data) => {

  if (isDebug()) {
    console.group("📊 Initial Focus Timing State");
    log("🔍 Focus Phase Mode:", data.focusPhaseMode);
    log("🕒 Focus Phase Start:", data.focusPhaseStart);
    log("⏱️ Timer Duration (D):", data.D * 60 * 1000);
    log("☕ Relax Duration (G):", data.G * 60 * 1000);
    log("🔁 Cycle Duration (G + H):", (data.G + data.H) * 60 * 1000);

    const now = Date.now();
    const remaining = data.focusPhaseStart
      ? (data.focusPhaseStart + (data.D * 60 * 1000) - now)
      : 0;

    log("📉 Remaining Time (in ms):", remaining);
    log("📆 Formatted Remaining Time:", formatTime(remaining));
    console.groupEnd();
  }
});

chrome.alarms.create("focusCheck", { periodInMinutes: 0.25 }); // check every 15s

chrome.alarms.create("focusDebug", { periodInMinutes: 0.0333 }); // every 2 sec


chrome.runtime.onInstalled.addListener(() => {
  chrome.notifications.create({
  type: "basic",
  iconUrl: chrome.runtime.getURL("assets/icons/128.png"),  // ← this line is required
  title: "🔔 GRAPE Extension Installed",
  message: "Notifications are working properly.",
  priority: 2
});
});

chrome.runtime.onInstalled.addListener(async (details) => {
  if (details.reason === "install") {
    const now = Date.now();
    await chrome.storage.local.set({ extensionInstallDate: now, gptScanInterval: 0, scanInterval: 0 });
    const defaultProviders = [
      { name: 'openai', key: '', order: 0 },
      { name: 'gemini', key: '', order: 1 }
    ];
    await chrome.storage.sync.set({ providers: defaultProviders });
    chrome.tabs.create({ url: chrome.runtime.getURL('pages/guide.html') });
  } else if (details.reason === 'update') {
    const { gptScanInterval, scanInterval } = await chrome.storage.local.get(['gptScanInterval','scanInterval']);
    if (gptScanInterval === undefined && scanInterval !== undefined) {
      await chrome.storage.local.set({ gptScanInterval: scanInterval });
    }
    const sync = await chrome.storage.sync.get('providers');
    if (!sync.providers) {
      const { apiKey = '' } = await chrome.storage.local.get('apiKey');
      const defaults = [
        { name: 'openai', key: apiKey, order: 0 },
        { name: 'gemini', key: '', order: 1 }
      ];
      await chrome.storage.sync.set({ providers: defaults });
    }
  }
});



/*chrome.runtime.onStartup.addListener(() => {
  chrome.notifications.create('test-key-missing', {
    type: "basic",
    iconUrl: chrome.runtime.getURL("assets/icons/128.png"),
    title: "🔔 Test Notification",
    message: "You should see this if notifications are working.",
    priority: 2
  });
});*/

// listen for forwarded debug messages from redirector.js
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.debug) {
    log('🔁 [redirector message]', ...msg.debug);
  }

  // 👉 Add your other handlers here, e.g.
  if (msg.action === "refreshBadge" && msg.payload) {
    const fakeStorage = {
      get: async (keys) => {
        if (!Array.isArray(keys)) return msg.payload;
        const result = {};
        for (const key of keys) {
          result[key] = msg.payload[key];
        }
        return result;
      }
    };

    const { score = 5 } = msg.payload;
    setBadge(score, fakeStorage);  // ✅ Just use already-imported setBadge
  }

  if (msg?.type === 'DNR_SNAPSHOT') {
    Promise.all([
      chrome.declarativeNetRequest.getDynamicRules(),
      RuleIds.getActive()
    ]).then(([dynamicRules, ids]) => {
      sendResponse({ dynamicRules, snapshot: { ruleIds: ids } });
    });
    return true; // keep message channel open for async response
  }
});


import { setBadge, badgeColor } from './badge.js';

import { fetchGPTJudgment } from '../utils/gpt-api.js';

import {
  enableBlockRules,
  disableBlockRules,
  shouldBlockUrl,
  lockOutTab,
  applyDynamicBlockRules    // ← add this
} from './blocker.js';

import { RuleIds } from './ruleIds.js';

async function clearAllDNRules() {
  const ids = await RuleIds.getActive();
  if (!ids.length) return;
  await RuleIds.updateDynamicRules({ removeRuleIds: ids });
  log(`✅ Cleared ${ids.length} dynamic rules on startup:`, ids);
}

// DEBUG: listen for *every* rule match
if (isDebug() && chrome.declarativeNetRequest?.onRuleMatchedDebug) {
  chrome.declarativeNetRequest.onRuleMatchedDebug.addListener(info => {
    console.groupCollapsed('🔍 DNR rule matched');
    log('ruleId:', info.rule.ruleId);
    log('request:', info.request);
    console.groupEnd();
  });
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && (changes.score || changes.focusMode)) {
    chrome.storage.local.get("score").then(({ score = 5 }) => {
      setBadge(score);
    });
  }
});





// ─────────────────────────────────────────────────────────────────────────────
// 1) On startup, load the user’s blocklist rules into DNR
chrome.runtime.onStartup.addListener(async () => {
  await clearAllDNRules(); // Wipe stale rules first

  const { blockedSites = [], lockoutUntil = 0 } =
    await chrome.storage.local.get(['blockedSites', 'lockoutUntil']);

  await applyDynamicBlockRules(blockedSites); // Then re-apply clean

  // ✅ Auto-clear dynamic rules if lockout is over (post-restart safety)
  if (Date.now() >= lockoutUntil) {
    const ids = await RuleIds.getActive();
    if (!ids.length) {
      log("🧹 No stale rules to auto-clear.");
    } else {
      await RuleIds.updateDynamicRules({ removeRuleIds: ids });
      log(`🧹 Auto-cleared ${ids.length} dynamic rules on startup:`, ids);
    }
  } else {
    log("⏳ Lockout still active — dynamic rules not cleared.");
  }
});



// ─────────────────────────────────────────────────────────────────────────────
// 2) Rebuild dynamic rules any time the user edits their blocklist
chrome.storage.onChanged.addListener(async (changes, area) => {
  if (area === 'local' && changes.blockedSites) {
    await applyDynamicBlockRules(changes.blockedSites.newValue);
  }
});


chrome.storage.local.set({ focusMode: "onAllDay" }).then(() => {
  chrome.storage.local.get("score").then(({ score = 5 }) => {
    setBadge(score); // show 🧠 badge immediately
  });
});




/* === Constants === */
const MAX_SCORE = 10;
const MIN_SCORE = -5;
let LOCKOUT_THRESHOLD = 4;
(async () => {
  const { blockThreshold = 4 } = await chrome.storage.local.get("blockThreshold");
  LOCKOUT_THRESHOLD = parseInt(blockThreshold);
})();                      // Lock out if score <= 4

let lastSnippet = "";
let CHECK_INTERVAL_MS = 5 * 60_000;       // 5 min default; will be overwritten
let BLOCK_DURATION    = 5 * 60_000;   // 5 min default; will be overwritten

/* ── pull user settings for scan / block durations (supports decimals) ── */
(async () => {
  const { gptScanInterval, scanInterval = 5, blockDuration = 5 } =
        await chrome.storage.local.get(["gptScanInterval", "scanInterval", "blockDuration"]);

  const interval = gptScanInterval ?? scanInterval ?? 0;
  CHECK_INTERVAL_MS = parseFloat(interval)  * 60_000;
  BLOCK_DURATION    = parseFloat(blockDuration) * 60_000;

  scheduleAlarm(parseFloat(interval));
})();

/* ── listen for future changes ───────────────── */
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== 'local') return;

  // 1) handle scan-interval, block-duration, threshold as before…
  if (changes.gptScanInterval || changes.scanInterval) {
    const v = changes.gptScanInterval?.newValue ?? changes.scanInterval?.newValue;
    scheduleAlarm(parseFloat(v));
  }
  if (changes.blockDuration)
    BLOCK_DURATION = parseFloat(changes.blockDuration.newValue) * 60_000;
  if (changes.blockThreshold)
    LOCKOUT_THRESHOLD = parseInt(changes.blockThreshold.newValue);

  // 2) focusMode => only touch the *poll* alarm
  if (changes.focusMode) {
    const newMode = changes.focusMode.newValue;
    if (newMode === 'off') {
      // stop the API scanner
      chrome.alarms.clear('poll');
      log('⛔ Focus Mode OFF — API polling stopped');
      // (don’t touch banned-words! it’ll keep running)
    } else {
      // resume API scanner
      chrome.storage.local.get(['gptScanInterval','scanInterval','score']).then(({gptScanInterval, scanInterval=5, score=5})=>{
        const interval = gptScanInterval ?? scanInterval;
        scheduleAlarm(parseFloat(interval));
        setBadge(score);
        log('✅ Focus Mode ON — API polling restarted');
        if (interval > 0) checkChatProductivity();
      });
    }
  }
});








/* === Escalation settings helpers (UI-driven) === */
async function getEscalationSettings() {
  const {
    blockLimit = 3,
    blockWindowMinutes = 10,
    useAccountabilityIntervention = false,
    blockTimeMultiplier = 1,
    blockDuration = 5
  } = await chrome.storage.local.get([
    "blockLimit","blockWindowMinutes","useAccountabilityIntervention","blockTimeMultiplier","blockDuration"
  ]);
  return { blockLimit, blockWindowMinutes, useAccountabilityIntervention, blockTimeMultiplier, blockDuration };
}
async function recordBlockEvent() {
  const now = Date.now();
  const { blockEvents = [] } = await chrome.storage.local.get("blockEvents");
  const { blockLimit, blockWindowMinutes } = await getEscalationSettings();

  const updated = [...blockEvents, now];
  const cutoff = now - blockWindowMinutes * 60 * 1000;
  const recent = updated.filter(ts => ts >= cutoff);

  await chrome.storage.local.set({ blockEvents: recent });

  if (recent.length >= blockLimit) {
    console.warn(`🚨 ${recent.length} blocks in ${blockWindowMinutes}m → extended lock`);
    await triggerExtendedLock();
  }
}

async function triggerExtendedLock() {
  const { useAccountabilityIntervention, blockTimeMultiplier, blockDuration } = await getEscalationSettings();
  if (!useAccountabilityIntervention) { log("⚪ Accountability Intervention disabled — skipping extended lock."); return; }
  const baseMinutes = Number(blockDuration);
  const maxBlockTimeMinutes = 720;
  const adjustedMinutes = Math.min(baseMinutes * (Number(blockTimeMultiplier) || 1), maxBlockTimeMinutes);
  const durationMs = Math.max(1, Math.round(adjustedMinutes * 60 * 1000));
  await chrome.storage.local.set({ lockoutUntil: Date.now() + durationMs, lockoutReason: "Accountability Intervention" });
  await lockUserOut();
}

/* ── helper: lock out every blocked tab ─────────────────────────────── */
async function lockUserOut() {
  const duration = BLOCK_DURATION;

  // 1) Grab every open tab across all windows
  const tabs = await chrome.tabs.query({});

  // 2) Redirect any that match your block rules
  for (const tab of tabs) {
    if (!tab.id || !tab.url) continue;
    if (await shouldBlockUrl(tab.url)) {
      await lockOutTab(tab, duration);
    }
  }

  // 3) Refresh your badge a single time
  const { score = 5 } = await chrome.storage.local.get('score');
  setBadge(score);
}


/* ── helper: score bookkeeping ────────────────────────────── */
async function changeScore(judgment /* "Yes" | "No" */) {
  const { score = 5 } = await chrome.storage.local.get('score');
  const delta = judgment === 'Yes' ? 1 : -1;
  const unclamped = score + delta;
  const newScore = Math.min(MAX_SCORE, Math.max(-6, unclamped)); // allow down to -6

  await chrome.storage.local.set({ score: newScore });
  log(`📉 score changed: ${score} → ${newScore}`);

  // auto-bounce -6 → -5 after 1 second
  if (newScore === -6) {
    setTimeout(() => {
      chrome.storage.local.get('score').then(({ score }) => {
        if (score === -6) {
          chrome.storage.local.set({ score: -5 });
          log('⏫ auto-bounced -6 → -5 after 1s');
          setBadge(-5);
        }
      });
    }, 1000);
  }

  return { previous: score, current: newScore };
}


/* ── main periodic routine ────────────────────────────────── */
async function checkChatProductivity() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  if (!tab || (!tab.url.includes("chat.openai.com") && !tab.url.includes("chatgpt.com"))) {
    log('❌ Not on a ChatGPT tab');
    return;
  }

const { focusMode = true } = await chrome.storage.local.get("focusMode");
if (!focusMode) {
  log("⛔ Focus Mode OFF — skipping scan.");
  return;
}


  if (tab.status !== "complete") {
    log("⏳ Tab is still loading, try again later.");
    return;
  }

  // optional: inject a sanity test script
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => log("🧪 Sanity check: injected!"),
  });

  // send message to content script
// ✅ Single request to content script
const response = await chrome.tabs.sendMessage(tab.id, { action: 'getSnippet' }).catch(() => null);
if (!response?.snippet) {
  console.warn('⚠️ no snippet received');
  return;
}

  // NEW – neutral if snippet is too short
  if (response.snippet.trim().length < 30) {
   log('🟡 snippet <30 chars → neutral (no score change)');
   lastSnippet = response.snippet;   // remember it so we don’t loop
   return;
}

  if (response.snippet === lastSnippet) {
  log('🟡 snippet unchanged, skipping');
  return;
}
lastSnippet = response.snippet;
log('📚 new snippet:', response.snippet);


  /* ── AI judgment using GPT API ── */
  let result;
  try {
    result = await fetchGPTJudgment(response.snippet);
  } catch (error) {
    await chrome.storage.local.set({ lastApiError: String(error) });
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (activeTab?.id) {
      chrome.tabs.update(activeTab.id, { url: chrome.runtime.getURL("api-error.html") });
    }
    return; // 🚫 stop processing on API error
  }
  const noKey = result?.missingKey === true;
  if (noKey) {
    const errorUrl = chrome.runtime.getURL("api-error.html");
    await chrome.storage.local.set({ lastApiError: "❌ No API key found" });

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.id) {
      chrome.tabs.update(tab.id, { url: errorUrl });
    }

    console.warn("❌ No API key found — redirected to error page");
    return; // 🛑 STOP here — don't take point or block
  }

  if (result?.error) {
    await chrome.storage.local.set({ lastApiError: result.error });
    const errorUrl = chrome.runtime.getURL("api-error.html");

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.id) {
      chrome.tabs.update(tab.id, { url: errorUrl });
    }

    console.warn("❌ API error:", result.error);
    return; // 🛑 STOP here — don't take point or block
  }

  let judgment = result?.judgment;


if (judgment !== "Yes" && judgment !== "No") {
  console.warn("❌ Invalid or missing response from GPT API");

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];
    if (!tab?.id) return;

    chrome.tabs.update(tab.id, {
      url: chrome.runtime.getURL("api-error.html")
    });

    chrome.storage.local.set({
  lastApiError: "❌ API Error: check your key and OpenAI credits"
});

  });

  return; // ⛔ Stop here — don't score or lock out
}
log('🤖 GPT says:', judgment);


const { goal = "MCAT" } = await chrome.storage.local.get("goal");
log(`🎯 Goal: ${goal}`);
log(`🧠 GPT Model: gpt-4o-mini`);



  /* update score + badge, maybe lock out */
  const { previous, current } = await changeScore(judgment);
// Don't call setBadge() here — we'll call it once after `poll` decides what emoji to use
if (current <= LOCKOUT_THRESHOLD && current < previous) {
  await recordBlockEvent();
  // record GPT-judgment reason
  await chrome.storage.local.set({ lockoutReason: 'GPT judged you were off focus' });
  const sites = ['chat.openai.com', 'chatgpt.com'];
  const { blockedSites = [] } = await chrome.storage.local.get('blockedSites');
  const updatedSites = [...new Set([...blockedSites, ...sites])];
  await chrome.storage.local.set({ blockedSites: updatedSites });

  await lockUserOut();
}

return current;



}








/* ⏰ alarm-based poller (survives worker suspend) */
function scheduleAlarm(mins) {
  chrome.alarms.clear('poll');
  if (mins > 0) {
    chrome.alarms.create('poll', { periodInMinutes: mins });
  }
}

  // ────────────────────────────────────────────────────────────────────────────────
  // 3) Catch *all* top‐level navigations during a lockout and redirect
chrome.webNavigation.onCommitted.addListener(async (details) => {
  if (details.frameId !== 0) return;

  const { lockoutUntil = 0 } = await chrome.storage.local.get('lockoutUntil');
  const shouldBlock = await shouldBlockUrl(details.url);

  if (isDebug()) {
    console.group('[NAV onCommitted]', details);
    log('now:', Date.now());
    log('lockoutUntil:', lockoutUntil);
    log('incoming URL:', details.url);
    log('shouldBlockUrl →', shouldBlock);
    console.groupEnd();
  }

  // your original logic
  const now = Date.now();
  if (now >= lockoutUntil) return;

  const lockoutUrl = chrome.runtime.getURL("pages/lockout.html");
  if (details.url.startsWith(lockoutUrl)) return; // already on lockout page

  if (shouldBlock) {
    const tab = await chrome.tabs.get(details.tabId);
    await lockOutTab(tab, lockoutUntil - now);
  }
});




// on tab switch, redirect any already-open blocked tab
chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  const now = Date.now();
  const { lockoutUntil = 0 } = await chrome.storage.local.get('lockoutUntil');
  const tab = await chrome.tabs.get(tabId);
  const shouldBlock = tab?.url && await shouldBlockUrl(tab.url);

  if (isDebug()) {
    console.group('[TAB onActivated] tabId:', tabId);
    log('now:', now);
    log('lockoutUntil:', lockoutUntil);
    log('current URL:', tab?.url);
    log('shouldBlockUrl →', shouldBlock);
    console.groupEnd();
  }

  // your original logic
  if (now >= lockoutUntil) return;

  const lockoutUrl = chrome.runtime.getURL("pages/lockout.html");
  if (tab?.url?.startsWith(lockoutUrl)) return; // already on lockout page

  if (shouldBlock) {
    await lockOutTab(tab, lockoutUntil - now);
  }
});








chrome.alarms.onAlarm.addListener(async (alarm) => {
  const now = Date.now();

  const {
    focusMode,
    focusPhaseMode,
    focusPhaseStart,
    D = 1,
    G = 0.1,
    H = 0.1,
    score = 5
  } = await chrome.storage.local.get([
    "focusMode",
    "focusPhaseMode",
    "focusPhaseStart",
    "D",
    "G",
    "H",
    "score"
  ]);

  // 🔁 2s debug timer handler
  if (alarm.name === "focusDebug") {
    /*console.group("📊 [2s DEBUG] Focus Timing");
    log("🔍 focusPhaseMode:", focusPhaseMode);
    log("🔍 focusMode:", focusMode);
    log("🕒 focusPhaseStart:", focusPhaseStart);
    log("⏱️ elapsed:", now - (focusPhaseStart || 0));
    console.groupEnd();*/

    const relaxMs = G * 60 * 1000;
    const focusMs = H * 60 * 1000;
    const totalCycle = relaxMs + focusMs;
    const elapsed = now - (focusPhaseStart || 0);

    if (focusPhaseMode === "timer" && elapsed >= D * 60 * 1000) {
      log("⏱️ Timer ended → focusMode = off");
      await chrome.storage.local.set({
        focusMode: "off",
        focusPhaseMode: null,
        focusPhaseStart: null
      });
      await setBadge("🚫" + score);
      return;
    }

    if (focusPhaseMode === "cycle") {
      if (elapsed < relaxMs) {
        if (focusMode !== "cycle") {
          log("☕ Entering relax phase");
          await chrome.storage.local.set({ focusMode: "cycle" });
        }
        // ✅ Coffee case passing the number
await setBadge(score);
      } else if (elapsed < totalCycle) {
        if (focusMode !== "cycleFocus") {
          log("💼 Entering focus phase");
          await chrome.storage.local.set({ focusMode: "cycleFocus" });

          const { score: newScore = 5 } = await chrome.storage.local.get("score");
          const safeScore = Number.isFinite(newScore) ? newScore : 5;
          await setBadge("💼" + safeScore);
        }
      } else {
        log("🧠 Cycle complete → Always On");
        await chrome.storage.local.set({
          focusMode: "onAllDay",
          focusPhaseMode: null,
          focusPhaseStart: null
        });
        await setBadge("🧠" + score);
      }
    }

    return; // ⛔ skip other logic
  }

  // 🔓 unlock handler
  if (alarm.name === "unlock") {
    await disableBlockRules();
    await chrome.storage.local.remove("lockoutUntil");
    const { score = 5 } = await chrome.storage.local.get("score");
    await setBadge(score);

    const tabs = await chrome.tabs.query({});
    for (const tab of tabs) {
      if (!tab?.id || !tab?.url?.includes("lockout.html")) continue;
      const key = `origUrl_${tab.id}`;
      const store = await chrome.storage.local.get(key);
      const origUrl = store[key];
        // Compute fresh target
        let target = (origUrl?.includes("chat.openai.com") || origUrl?.includes("chatgpt.com"))
          ? "https://chat.openai.com/?fresh=" + Date.now()
          : origUrl;
        
        if (target) {
          // If we’re heading to ChatGPT, set the priming message & flag
          const isChatGPT = (u) => /chatgpt\.com|chat\.openai\.com/i.test(u || "");
          if (isChatGPT(target)) {
            const {
              insertOnRedirect = true,
              redirectTemplate = "Strict Mode Enforcer… {goal}"
            } = await chrome.storage.local.get(["insertOnRedirect", "redirectTemplate"]);
            const { goal = "" } = await chrome.storage.local.get("goal");
        
            if (insertOnRedirect && redirectTemplate && redirectTemplate.trim()) {
                const primedMessage = String(redirectTemplate).replace("{goal}", goal || "");
                const primeExpiresAt = Date.now() + 120_000; // expire after 2 minutes
                await chrome.storage.local.set({ primedMessage, redirectPriming: true, primeExpiresAt });
                log("🍇 priming set before redirect");

            } else {
              await chrome.storage.local.set({ redirectPriming: false });
            }
          }
        
          await chrome.tabs.update(tab.id, { url: target });
          await chrome.storage.local.remove(key);
        }

    }
    return;
  }

  // ⏳ fallback checker
  if (alarm.name === "focusCheck") {
    let duration = 0;
    if (focusPhaseMode === "timer") duration = D * 60 * 1000;
    else if (focusPhaseMode === "cycle") duration = (G + H) * 60 * 1000;

    const remaining = focusPhaseStart ? (focusPhaseStart + duration - now) : 0;

    if (focusPhaseStart && remaining <= 0) {
      const newMode = focusPhaseMode === "timer" ? "off" : "onAllDay";
      log(`⏳ focusCheck expired → focusMode → '${newMode}'`);
      await chrome.storage.local.set({
        focusMode: newMode,
        focusPhaseMode: null,
        focusPhaseStart: null
      });
      await setBadge(score);
    }

    return; // ✅ skip GPT scan
  }

  // ✅ 🧠 ONLY run checkChatProductivity() from the correct "poll" alarm
  if (alarm.name === "poll") {
const newScore = await checkChatProductivity();
const {
  focusMode,
  focusPhaseMode,
  focusPhaseStart,
  G = 0.1,
  H = 0.1
} = await chrome.storage.local.get([
  "focusMode",
  "focusPhaseMode",
  "focusPhaseStart",
  "G",
  "H"
]);

const now = Date.now();
const relaxMs = G * 60 * 1000;
const elapsed = now - (focusPhaseStart || 0);

// 🕵️‍♂️ Check phase and show correct emoji with latest score
if (focusPhaseMode === "cycle" && elapsed < relaxMs) {
  await setBadge("☕" + newScore);
} else if (focusPhaseMode === "cycle" && elapsed < relaxMs + H * 60 * 1000) {
  await setBadge("💼" + newScore);
} else {
  await setBadge(newScore);
}

  }
});







// No-op listener retained for backwards compatibility
chrome.notifications.onClicked.addListener(() => {});


/* ── initialise badge to current score (or default 5) ────── */
chrome.storage.local.get(['score', 'focusMode']).then(({ score = 5, focusMode }) => {
  setBadge(score); // this now pulls the right icon from focusMode
});


chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== 'bannedCheck') return;

  log('🕵️ Scanning for blocked words...');
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || (!tab.url.includes("chat.openai.com") && !tab.url.includes("chatgpt.com"))) {
    log('🚫 No ChatGPT tab active; skipping scan');
    return;
  }

  const response = await chrome.tabs.sendMessage(tab.id, { action: 'getSnippet' }).catch(() => null);
  const snippet = response?.fullSnippet || response?.snippet || '';
  log(`✂️ Snippet length: ${snippet.length}`);

  if (snippet.length < 30) {
    log('🔍 Snippet too short (<30 chars); skipping');
    return;
  }

  const { blockedWords = [] } = await chrome.storage.local.get("blockedWords");
  if (!Array.isArray(blockedWords) || blockedWords.length === 0) {
    log('ℹ️ No blocked words configured');
    return;
  }

  // Whole-word/phrase match (prevents "ai" matching inside "fountain")
  const hit = blockedWords.find(w => {
    const escaped = w
      .replace(/[.*+?^${}()|[\]\\]/g, '\\$&') // escape regex chars
      .trim()
      .replace(/\s+/g, '\\s+');               // allow flexible spacing
    const re = new RegExp(`\\b${escaped}\\b`, 'i');
    return re.test(snippet);
  });
  if (!hit) {
    log('✔️ No blocked words found');
    return;
  }


  console.warn(`🚫 Blocked word found: "${hit}" — taking action`);
  const { previous, current } = await changeScore("No");
  setBadge(current);

  const { blockThreshold = 4 } = await chrome.storage.local.get("blockThreshold");
 if (current <= blockThreshold && current < previous) {
    // record blocked-word reason
    await chrome.storage.local.set({ lockoutReason: `Detected blocked word: "${hit}"` });
    await lockUserOut();
  }
});



function scheduleBannedCheck(seconds) {
  chrome.alarms.clear('bannedCheck');
  chrome.alarms.create('bannedCheck', { periodInMinutes: seconds / 60 });
}

// Pull user setting for bannedCheckInterval (in seconds)
(async () => {
  const { bannedCheckInterval = 10 } = await chrome.storage.local.get("bannedCheckInterval");
  scheduleBannedCheck(bannedCheckInterval);
})();

// Listen for future changes to bannedCheckInterval
chrome.storage.onChanged.addListener(ch => {
  if (ch.bannedCheckInterval) {
    scheduleBannedCheck(parseFloat(ch.bannedCheckInterval.newValue));
  }
});

// === Diagnostic Rule Logger (Net Request) ===
chrome.runtime.onStartup.addListener(async () => {
  const rules = await chrome.declarativeNetRequest.getDynamicRules();
  log("📋 Existing dynamic rules on startup:", rules);
});

// Also log immediately on reload
(async () => {
  const rules = await chrome.declarativeNetRequest.getDynamicRules();
  log("📋 Immediate dynamic rule check after reload:", rules);
})();