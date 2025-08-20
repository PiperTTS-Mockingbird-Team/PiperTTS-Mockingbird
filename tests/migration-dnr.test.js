import { migrateBadDynamicRuleIds } from '../src/background/migration-dnr.js';
import { RuleIds } from '../src/background/rule-ids.js';

jest.mock('../src/background/rule-ids.js', () => ({
  RuleIds: {
    allocate: jest.fn().mockResolvedValue([10000]),
    updateDynamicRules: jest.fn().mockResolvedValue(),
    setActive: jest.fn().mockResolvedValue()
  },
  RULE_ID_RANGES: { lockout: [10000, 19999] }
}));

function makeRule(id, host, ext = '/pages/lockout.html') {
  return {
    id,
    priority: 2,
    action: { type: 'redirect', redirect: { extensionPath: ext } },
    condition: { urlFilter: `||${host}^`, resourceTypes: ['main_frame'] }
  };
}

describe('migrateBadDynamicRuleIds', () => {
  test('migrates out-of-range ids and preserves other features', async () => {
    const rules = [
      makeRule(500, 'a.com'), // bad lockout
      makeRule(10005, 'b.com'), // good lockout
      makeRule(20000, 'c.com', '/pages/other.html') // unrelated feature
    ];
    const index = { 'a.com': 500, 'b.com': 10005 };
    const result = await migrateBadDynamicRuleIds(rules, index);
    expect(RuleIds.allocate).toHaveBeenCalledWith('lockout', 1);
    expect(RuleIds.updateDynamicRules).toHaveBeenCalledWith({
      removeRuleIds: [500],
      addRules: [expect.objectContaining({ id: 10000 })]
    });
    expect(RuleIds.setActive).toHaveBeenCalledWith('lockout', [10005, 10000]);
    expect(result).toEqual({ 'a.com': 10000, 'b.com': 10005 });
  });
});

