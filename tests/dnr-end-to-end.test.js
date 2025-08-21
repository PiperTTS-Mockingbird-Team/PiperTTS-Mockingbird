import { applyDynamicRules } from '../src/background/dynamic-rule-manager.js';
import { RuleIds, RULE_ID_RANGES } from '../src/background/rule-ids.js';

jest.mock('../src/utils/logger.js', () => ({ log: jest.fn() }));

describe('DNR end-to-end', () => {
  let storage;
  let dynamicRules;

  beforeEach(() => {
    storage = {};
    dynamicRules = [];
    const get = jest.fn((keys) => {
      if (Array.isArray(keys)) {
        const res = {};
        for (const k of keys) res[k] = storage[k];
        return Promise.resolve(res);
      }
      return Promise.resolve({ [keys]: storage[keys] });
    });
    const set = jest.fn(obj => { Object.assign(storage, obj); return Promise.resolve(); });
    const remove = jest.fn(keys => {
      if (Array.isArray(keys)) keys.forEach(k => delete storage[k]);
      else delete storage[keys];
      return Promise.resolve();
    });
    const updateDynamicRules = jest.fn(async ({ addRules = [], removeRuleIds = [] }) => {
      dynamicRules = dynamicRules.filter(r => !removeRuleIds.includes(r.id));
      dynamicRules.push(...addRules);
    });
    const getDynamicRules = jest.fn(async () => dynamicRules);
    globalThis.chrome = {
      storage: { local: { get, set, remove } },
      declarativeNetRequest: { updateDynamicRules, getDynamicRules }
    };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('lockout redirect coexists with wordBlocker rules', async () => {
    const wbId = (await RuleIds.allocate('wordBlocker', 1))[0];
    const wbRule = {
      id: wbId,
      priority: 1,
      action: { type: 'redirect', redirect: { extensionPath: '/pages/other.html' } },
      condition: { urlFilter: '||wb.com^', resourceTypes: ['main_frame'] }
    };
    await RuleIds.updateDynamicRules({ addRules: [wbRule] });

    await applyDynamicRules(['a.com']);

    const lockoutId = RULE_ID_RANGES.lockout[0];
    expect(dynamicRules).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: wbId }),
      expect.objectContaining({
        id: lockoutId,
        action: expect.objectContaining({ redirect: expect.objectContaining({ extensionPath: '/pages/lockout.html' }) })
      })
    ]));
    await expect(RuleIds.getActive('wordBlocker')).resolves.toEqual([wbId]);
    await expect(RuleIds.getActive('lockout')).resolves.toEqual([lockoutId]);
  });
});

