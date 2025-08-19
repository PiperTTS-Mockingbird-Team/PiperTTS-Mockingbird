import { createRuleIdAllocator } from './blocker-ids.js';
import { log } from '../utils/logger.js';

// Migrate rules with IDs below start into reserved range
export async function migrateBadDynamicRuleIds(rules, index, start = 10000) {
  const allocator = createRuleIdAllocator(start);

  const removeRuleIds = [];
  const addRules = [];

  for (const rule of rules) {
    // Extract host from urlFilter of shape ||host^
    const host = rule.condition?.urlFilter?.replace(/^\|\|/, '').replace(/\^$/, '');
    if (rule.id < start) {
      const newId = allocator.allocate(host);
      removeRuleIds.push(rule.id);
      addRules.push({ ...rule, id: newId });
      index[host] = newId;
    } else {
      allocator.allocate(host); // reserve existing good id
    }
  }

  if (removeRuleIds.length || addRules.length) {
    await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds, addRules });
    log(`🔧 migrateBadDynamicRuleIds: removed ${removeRuleIds.length}, added ${addRules.length}`);
  }

  return index;
}
