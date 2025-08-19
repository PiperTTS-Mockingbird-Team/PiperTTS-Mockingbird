import { migrateBadDynamicRuleIds } from '../src/background/migration-dnr.js';
import { START_ID } from '../src/background/ruleIds.js';

function makeRule(id, host) {
  return {
    id,
    priority: 2,
    action: { type: 'redirect', redirect: { extensionPath: '/pages/lockout.html' } },
    condition: { urlFilter: `||${host}^`, resourceTypes: ['main_frame'] }
  };
}

describe('migrateBadDynamicRuleIds', () => {
  let updateDynamicRules;
  beforeEach(() => {
    updateDynamicRules = jest.fn().mockResolvedValue();
    globalThis.chrome = { declarativeNetRequest: { updateDynamicRules } };
  });
  afterEach(() => {
    delete globalThis.chrome;
  });

  test('migrates bad ids into reserved range and updates index', async () => {
    const rules = [makeRule(1, 'a.com'), makeRule(2, 'b.com')];
    const index = { 'a.com': 1, 'b.com': 2 };
    const result = await migrateBadDynamicRuleIds(rules, index);
    expect(updateDynamicRules).toHaveBeenCalledTimes(1);
    const args = updateDynamicRules.mock.calls[0][0];
    expect(args.removeRuleIds).toEqual([1, 2]);
    expect(args.addRules.map(r => r.id)).toEqual([START_ID, START_ID + 1]);
    expect(result).toEqual({ 'a.com': START_ID, 'b.com': START_ID + 1 });
  });
});
