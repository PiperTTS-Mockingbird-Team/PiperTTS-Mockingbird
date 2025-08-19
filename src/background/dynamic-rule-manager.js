import { log } from '../utils/logger.js';
import { RuleIds, START_ID } from './rule-ids.js';
import { migrateBadDynamicRuleIds } from './migration-dnr.js';

export async function getBlockedSites() {
  const { blockedSites } = await chrome.storage.local.get('blockedSites');
  if (!Array.isArray(blockedSites)) return [];
  return blockedSites
    .filter(site => typeof site === 'string')
    .map(site => site.trim())
    .filter(Boolean);
}

export async function applyDynamicRules(sites) {
  if (!Array.isArray(sites)) {
    const ids = await RuleIds.getActive();
    await RuleIds.updateDynamicRules({ removeRuleIds: ids });
    await RuleIds.update([]);
    return;
  }

  const existing = await chrome.declarativeNetRequest.getDynamicRules();
  const reserved = existing.map(r => r.id).filter(id => id >= START_ID);
  if (reserved.length) {
    await RuleIds.release(reserved);
  }

  const ruleIds = await RuleIds.allocate(sites.length);

  const addRules = sites.map((site, i) => ({
    id: ruleIds[i],
    priority: 2,
    action: {
      type: 'redirect',
      redirect: { extensionPath: '/pages/lockout.html' }
    },
    condition: {
      urlFilter: `||${site.replace(/^https?:\/\//, '')}^`,
      resourceTypes: ['main_frame']
    }
  }));

  const removeRuleIds = reserved;
  await RuleIds.updateDynamicRules({ removeRuleIds, addRules });
  log(`\uD83D\uDD27 updateDynamicRules: removed ${removeRuleIds.length}, added ${addRules.length}`);

  await RuleIds.update(ruleIds);
}

export async function rebuildDynamicRules(sites) {
  if (typeof sites === 'undefined') {
    sites = await getBlockedSites();
  }
  await applyDynamicRules(sites);
}

export async function clearDynamicRules() {
  const activeRuleIds = await RuleIds.getActive();
  if (activeRuleIds.length) {
    await RuleIds.updateDynamicRules({ removeRuleIds: activeRuleIds });
    log(`\uD83D\uDD27 updateDynamicRules: removed ${activeRuleIds.length}`);
  }
  return activeRuleIds.length;
}

export { migrateBadDynamicRuleIds };
