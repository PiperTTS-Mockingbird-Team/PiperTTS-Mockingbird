import { manageDynamicRules, applyDynamicRules } from '../src/background/dynamic-rule-manager.js';
import { RuleIds, RULE_ID_RANGES } from '../src/background/rule-ids.js';

let storage;
let storageGet;
let storageSet;
let storageRemove;
let updateDynamicRules;

beforeEach(() => {
  storage = {};
  storageGet = jest.fn((keys) => {
    if (Array.isArray(keys)) {
      const res = {};
      for (const k of keys) res[k] = storage[k];
      return Promise.resolve(res);
    }
    return Promise.resolve({ [keys]: storage[keys] });
  });
  storageSet = jest.fn((obj) => { Object.assign(storage, obj); return Promise.resolve(); });
  storageRemove = jest.fn((keys) => {
    if (Array.isArray(keys)) keys.forEach(k => delete storage[k]);
    else delete storage[keys];
    return Promise.resolve();
  });
  updateDynamicRules = jest.fn().mockResolvedValue();
  globalThis.chrome = {
    storage: { local: { get: storageGet, set: storageSet, remove: storageRemove } },
    declarativeNetRequest: { updateDynamicRules }
  };
});

afterEach(() => {
  delete globalThis.chrome;
});

test('manageDynamicRules clear only affects lockout ids', async () => {
  const startLock = RULE_ID_RANGES.lockout[0];
  const startWord = RULE_ID_RANGES.wordBlocker[0];
  await RuleIds.allocate('lockout', 1);
  await RuleIds.allocate('wordBlocker', 1);

  await manageDynamicRules('clear');

  expect(updateDynamicRules).toHaveBeenCalledWith({ removeRuleIds: [startLock] });
  expect(await RuleIds.getActive('lockout')).toEqual([]);
  expect(await RuleIds.getActive('wordBlocker')).toEqual([startWord]);
  expect(storage['freeRuleIds:lockout']).toEqual([startLock]);
});

test('applyDynamicRules race allocates unique ids', async () => {
  await Promise.all([
    applyDynamicRules(['a.com']),
    applyDynamicRules(['b.com'])
  ]);

  const ids = updateDynamicRules.mock.calls.map(([opts]) => opts.addRules[0].id);
  expect(new Set(ids).size).toBe(2);
});
