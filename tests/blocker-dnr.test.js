import { applyDynamicRules } from '../src/background/dynamic-rule-manager.js';
import { RuleIds } from '../src/background/rule-ids.js';

jest.mock('../src/background/rule-ids.js', () => ({
  RuleIds: {
    getActive: jest.fn().mockResolvedValue([]),
    allocate: jest.fn().mockResolvedValue([10000, 10001]),
    updateDynamicRules: jest.fn().mockResolvedValue(),
    setActive: jest.fn().mockResolvedValue()
  },
  RULE_ID_RANGES: { lockout: [10000, 19999] }
}));

describe('applyDynamicRules DNR', () => {
  test('builds rules with ids, priorities, filters and single update call', async () => {
    await applyDynamicRules(['https://a.com', 'b.com']);
    expect(RuleIds.allocate).toHaveBeenCalledWith('lockout', 2);
    expect(RuleIds.updateDynamicRules).toHaveBeenCalledTimes(1);
    const arg = RuleIds.updateDynamicRules.mock.calls[0][0];
    expect(arg.removeRuleIds).toEqual([]);
    expect(arg.addRules).toHaveLength(2);
    expect(arg.addRules[0]).toEqual(expect.objectContaining({
      id: 10000,
      priority: 2,
      condition: expect.objectContaining({ urlFilter: '||a.com^' })
    }));
    expect(arg.addRules[1]).toEqual(expect.objectContaining({
      id: 10001,
      priority: 2,
      condition: expect.objectContaining({ urlFilter: '||b.com^' })
    }));
    expect(RuleIds.setActive).toHaveBeenCalledWith('lockout', [10000, 10001]);
  });
});

