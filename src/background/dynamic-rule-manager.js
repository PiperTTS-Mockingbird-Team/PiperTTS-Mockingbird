import { log } from '../utils/logger.js';
import { RuleIds } from './rule-ids.js';
import { migrateBadDynamicRuleIds } from './migration-dnr.js';

export const STATIC_RULE_DOMAINS = ['chat.openai.com', 'chatgpt.com'];

function extractHostname(site) {
  if (typeof site !== 'string') return '';
  const trimmed = site.trim();
  if (!trimmed) return '';
  try {
    const url = new URL(trimmed.includes('://') ? trimmed : `https://${trimmed}`);
    return url.hostname;
  } catch {
    return '';
  }
}

function getReservedHostnames() {
  const hosts = [...STATIC_RULE_DOMAINS];
  try {
    if (chrome?.runtime?.getURL) {
      hosts.push(new URL(chrome.runtime.getURL('')).hostname);
    }
  } catch {}
  return new Set(hosts);
}

export async function getBlockedSites() {
  const { blockedSites } = await chrome.storage.local.get('blockedSites');
  if (!Array.isArray(blockedSites)) return [];
  const reserved = getReservedHostnames();
  return blockedSites
    .filter(site => typeof site === 'string')
    .map(extractHostname)
    .filter(host => host && !reserved.has(host));
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

  const reserved = getReservedHostnames();
  const filtered = [];
  for (const site of sites) {
    const host = extractHostname(site);
    if (!host || reserved.has(host)) {
      log(`\u26A0\uFE0F ignoring blocked site: ${site}`);
      continue;
    }
    filtered.push(host);
  }

  const oldIds = await RuleIds.getActive('lockout');
  const newIds = filtered.length ? await RuleIds.allocate('lockout', filtered.length) : [];

  const addRules = filtered.map((host, i) => ({
    id: newIds[i],
    priority: 2,
    action: {
      type: 'redirect',
      redirect: { extensionPath: '/pages/lockout.html' }
    },
    condition: {
      urlFilter: `||${host}^`,
      resourceTypes: ['main_frame'],
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

