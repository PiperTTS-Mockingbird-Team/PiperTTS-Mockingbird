import { applyDynamicRules } from '../src/background/dynamic-rule-manager.js';
import { START_ID } from '../src/background/rule-ids.js';

describe('applyDynamicRules DNR', () => {
  let updateDynamicRules;
  let getDynamicRules;
  beforeEach(() => {
    updateDynamicRules = jest.fn().mockResolvedValue();
    getDynamicRules = jest.fn().mockResolvedValue([]);
    globalThis.chrome = {
      declarativeNetRequest: { updateDynamicRules, getDynamicRules },
      storage: { local: {
        set: jest.fn().mockResolvedValue(),
        get: jest.fn().mockResolvedValue({}),
        remove: jest.fn().mockResolvedValue()
      } }
    };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('builds rules with ids, priorities, filters and single update call', async () => {
    await applyDynamicRules(['https://a.com', 'b.com']);
    expect(updateDynamicRules).toHaveBeenCalledTimes(1);
    const arg = updateDynamicRules.mock.calls[0][0];
    expect(arg.removeRuleIds).toEqual([]);
    expect(arg.addRules).toHaveLength(2);
    expect(arg.addRules[0]).toEqual(expect.objectContaining({
      id: START_ID,
      priority: 2,
      condition: expect.objectContaining({ urlFilter: '||a.com^' })
    }));
    expect(arg.addRules[1]).toEqual(expect.objectContaining({
      id: START_ID + 1,
      priority: 2,
      condition: expect.objectContaining({ urlFilter: '||b.com^' })
    }));
  });
});
