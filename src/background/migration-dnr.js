import { logger } from '../utils/logger.js';
import { RuleIds, RULE_ID_RANGES } from './rule-ids.js';

// Migrate lockout rules with IDs outside the reserved range
const log = logger('background');

export async function migrateBadDynamicRuleIds(rules, index, range = RULE_ID_RANGES.lockout) {
  const [start, end] = range;
  const lockoutRules = rules.filter(r => r.action?.redirect?.extensionPath === '/pages/lockout.html');
  const goodRules = lockoutRules.filter(r => r.id >= start && r.id <= end);
  const badRules = lockoutRules.filter(r => r.id < start || r.id > end);

  let newIds = [];
  if (badRules.length) {
    newIds = await RuleIds.allocate('lockout', badRules.length);
  }

  const removeRuleIds = [];
  const addRules = [];
  let i = 0;
  for (const rule of lockoutRules) {
    const host = rule.condition?.urlFilter?.replace(/^\|\|/, '').replace(/\^$/, '');
    if (rule.id < start || rule.id > end) {
      const newId = newIds[i++];
      removeRuleIds.push(rule.id);
      addRules.push({ ...rule, id: newId });
      if (host) index[host] = newId;
    } else {
      if (host) index[host] = rule.id;
    }
  }

  if (removeRuleIds.length || addRules.length) {
    await RuleIds.updateDynamicRules({ removeRuleIds, addRules });
    log(`🔧 migrateBadDynamicRuleIds: removed ${removeRuleIds.length}, added ${addRules.length}`);
  }

  const finalIds = [...goodRules.map(r => r.id), ...newIds];
  await RuleIds.setActive('lockout', finalIds);
  return index;
}
