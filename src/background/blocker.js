import { log } from '../utils/logger.js';
import {
  getBlockedSites,
  rebuildDynamicRules,
  clearDynamicRules
} from './dynamic-rule-manager.js';

// blocker.js
const BLOCK_RULE_ID   = 'block-chatgpt';      // your static rules.json ID

// —————————————————————————————————————————————————————————————————————
// 2. Static ChatGPT rule toggles (unchanged)
export async function enableBlockRules() {
  await chrome.declarativeNetRequest.updateEnabledRulesets({
    enableRulesetIds: [BLOCK_RULE_ID]
  });
}
export async function disableBlockRules() {
  await chrome.declarativeNetRequest.updateEnabledRulesets({
    disableRulesetIds: [BLOCK_RULE_ID]
  });
  // also tear down any user rules
  await clearDynamicRules();
}

// —————————————————————————————————————————————————————————————————————
// 3. URL matcher (unchanged)
export async function shouldBlockUrl(url) {
  const blockedSites = await getBlockedSites();
  return blockedSites.some(domain => url.includes(domain));
}

/* PATCHED — replace your entire lockOutTab() with this */
export async function lockOutTab(tab, duration) {
  const origUrl    = tab.url;
  const tabId      = tab.id;
  const lockoutUrl = chrome.runtime.getURL("pages/lockout.html");

  // Don’t double-redirect if we’re already on lockout.html
  if (origUrl.startsWith(lockoutUrl)) {
    log("🔁 Tab already on lockout.html — skipping re-redirect");
    return;
  }

  /* 1️⃣ grab the current goal so the lockout page can display it */
  const { goal = "Stay focused" } = await chrome.storage.local.get("goal");

  /* 2️⃣ save lockout meta (incl. goal) */
  await chrome.storage.local.set({
    [`origUrl_${tabId}`]: origUrl,
    lockoutUntil: Date.now() + duration,
    goal
  });

  /* 3️⃣ build and perform the redirect FIRST */
  const redirectUrl =
    `${lockoutUrl}?tabId=${tabId}&orig=${encodeURIComponent(origUrl)}`;
  await chrome.tabs.update(tabId, { url: redirectUrl });

  /* 4️⃣ re-apply dynamic rules but skip the site we just locked */
  const blockedSites = await getBlockedSites();
  const host = new URL(origUrl).hostname;
  const filtered = blockedSites.filter(s => !host.includes(s));
  await rebuildDynamicRules(filtered);
  await enableBlockRules();

  /* 5️⃣ schedule the unlock alarm */
  chrome.alarms.create('unlock', { when: Date.now() + duration });
}
/* end PATCH */
