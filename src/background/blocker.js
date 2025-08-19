import { log } from '../utils/logger.js';
import { RuleIds } from './ruleIds.js';

// blocker.js
const BLOCK_RULE_ID   = 'block-chatgpt';      // your static rules.json ID
const DYNAMIC_RULE_START = 10_000;             // high offset for user rules

// —————————————————————————————————————————————————————————————————————
// 1. Build / remove user‐list rules at runtime
export async function applyDynamicBlockRules(sites) {
  // If sites is not a valid array, clear any existing dynamic rules
  if (!Array.isArray(sites)) {
    const ids = await RuleIds.getActive();
    await RuleIds.updateDynamicRules({ removeRuleIds: ids });
    await RuleIds.update([]);
    return;
  }

  // Build a rule for each site, giving each a unique but consistent ID
  const addRules = sites.map((site, i) => ({
    id: DYNAMIC_RULE_START + i, // reuses the same ID for each site every time
    priority: 2,                // rule priority (higher = wins if conflicts)
    action: {
      type: 'redirect',
      redirect: { extensionPath: '/pages/lockout.html' } // redirect to lockout screen
    },
    condition: {
      // Clean the site string and match the domain
      urlFilter: `||${site.replace(/^https?:\/\//, '')}^`,
      resourceTypes: ['main_frame'] // only block top-level page loads
    }
  }));

  // Extract the rule IDs we're going to use
  const ruleIds = addRules.map(r => r.id);

  // Fetch existing dynamic rule IDs so we can clean up stale ones
  const existing = await chrome.declarativeNetRequest.getDynamicRules();
  const existingIds = existing.map(r => r.id);
  const reserved = existingIds.filter(id => id >= DYNAMIC_RULE_START);
  const staleIds = reserved.filter(id => !ruleIds.includes(id));
  const removeRuleIds = staleIds.concat(ruleIds);

  // Replace the rules in a single call and release any stale IDs
  await RuleIds.updateDynamicRules({ removeRuleIds, addRules });
  log(`🔧 updateDynamicRules: removed ${removeRuleIds.length}, added ${addRules.length}`);

  // Save the list of active IDs so we can reference or clear them later
  await RuleIds.update(ruleIds);
}





export async function clearDynamicBlockRules() {
  const activeRuleIds = await RuleIds.getActive();
  if (activeRuleIds.length) {
    await RuleIds.updateDynamicRules({
      removeRuleIds: activeRuleIds
    });
    log(`🔧 updateDynamicRules: removed ${activeRuleIds.length}`);
  }
}

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
  await clearDynamicBlockRules();
}

// —————————————————————————————————————————————————————————————————————
// 3. URL matcher (unchanged)
export async function shouldBlockUrl(url) {
  const { blockedSites = [] } = await chrome.storage.local.get('blockedSites');
  return (
    blockedSites.some(domain => url.includes(domain))
  );
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
  const { blockedSites = [] } = await chrome.storage.local.get("blockedSites");
  const host = new URL(origUrl).hostname;
  const filtered = blockedSites.filter(s => !host.includes(s));
  await applyDynamicBlockRules(filtered);
  await enableBlockRules();

  /* 5️⃣ schedule the unlock alarm */
  chrome.alarms.create('unlock', { when: Date.now() + duration });
}
/* end PATCH */
