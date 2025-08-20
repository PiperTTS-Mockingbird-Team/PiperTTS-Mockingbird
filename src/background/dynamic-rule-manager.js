import { log } from '../utils/logger.js';
import { RuleIds } from './rule-ids.js';
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
    const ids = await RuleIds.getActive('lockout');
    if (ids.length) {
      await RuleIds.updateDynamicRules({ removeRuleIds: ids });
    }
    await RuleIds.setActive('lockout', []);
    return;
  }

  const oldIds = await RuleIds.getActive('lockout');
  const newIds = await RuleIds.allocate('lockout', sites.length);

  const addRules = sites.map((site, i) => ({
    id: newIds[i],
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

  await RuleIds.updateDynamicRules({ addRules, removeRuleIds: oldIds });
  log(`\uD83D\uDD27 updateDynamicRules: removed ${oldIds.length}, added ${addRules.length}`);

  await RuleIds.setActive('lockout', newIds);
}

export async function manageDynamicRules(action, sites) {
  if (action === 'clear') {
    const activeRuleIds = await RuleIds.getActive('lockout');
    if (activeRuleIds.length) {
      await RuleIds.updateDynamicRules({ removeRuleIds: activeRuleIds });
      log(`\uD83D\uDD27 updateDynamicRules: removed ${activeRuleIds.length}`);
    }
    await RuleIds.setActive('lockout', []);
    return activeRuleIds.length;
  }

  if (typeof sites === 'undefined') {
    sites = await getBlockedSites();
  }
  await applyDynamicRules(sites);
}

export { migrateBadDynamicRuleIds };
