import { log } from '../utils/logger.js';
import { RuleIds, START_ID } from './rule-ids.js';

// blocker.js
const BLOCK_RULE_ID   = 'block-chatgpt';      // your static rules.json ID

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

  // Fetch existing dynamic rule IDs in the reserved range and release them
  const existing = await chrome.declarativeNetRequest.getDynamicRules();
  const reserved = existing.map(r => r.id).filter(id => id >= START_ID);
  if (reserved.length) {
    await RuleIds.release(reserved);
  }

  // Allocate fresh IDs for the incoming rules
  const ruleIds = await RuleIds.allocate(sites.length);

  // Build a rule for each site using the allocated IDs
  const addRules = sites.map((site, i) => ({
    id: ruleIds[i],
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

  // Replace the rules in a single call and release any stale IDs
  const removeRuleIds = reserved;
  await RuleIds.updateDynamicRules({ removeRuleIds, addRules });
  log(`🔧 updateDynamicRules: removed ${removeRuleIds.length}, added ${addRules.length}`);

  // Save the list of active IDs so we can reference or clear them later
  await RuleIds.update(ruleIds);
}


// Convenience helper: rebuild the dynamic rules from a supplied list or
// from storage if no list is provided
export async function rebuildDynamicRules(sites) {
  if (typeof sites === 'undefined') {
    const { blockedSites } = await chrome.storage.local.get('blockedSites');
    sites = blockedSites;
  }
  await applyDynamicBlockRules(sites);
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
  await rebuildDynamicRules(filtered);
  await enableBlockRules();

  /* 5️⃣ schedule the unlock alarm */
  chrome.alarms.create('unlock', { when: Date.now() + duration });
}
/* end PATCH */
