import { log } from '../utils/logger.js';
import { RuleIds, START_ID } from './ruleIds.js';

// Migrate rules with IDs below start into reserved range
export async function migrateBadDynamicRuleIds(rules, index, start = START_ID) {
  const goodIds = rules.filter(r => r.id >= start).map(r => r.id);
  if (goodIds.length) {
    await RuleIds.update(goodIds);
  }

  const badRules = rules.filter(r => r.id < start);
  const newIds = await RuleIds.allocate(badRules.length);

  const removeRuleIds = [];
  const addRules = [];

  let i = 0;
  for (const rule of rules) {
    const host = rule.condition?.urlFilter?.replace(/^\|\|/, '').replace(/\^$/, '');
    if (rule.id < start) {
      const newId = newIds[i++];
      removeRuleIds.push(rule.id);
      addRules.push({ ...rule, id: newId });
      index[host] = newId;
    } else {
      index[host] = rule.id;
    }
  }

  if (removeRuleIds.length || addRules.length) {
    await RuleIds.updateDynamicRules({ removeRuleIds, addRules });
    log(`🔧 migrateBadDynamicRuleIds: removed ${removeRuleIds.length}, added ${addRules.length}`);
  }

  return index;
}
