import { RuleIds, RULE_ID_RANGES } from '../src/background/rule-ids.js';

describe('RuleIds', () => {
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

  test('allocates ids within feature range and reuses freed ids', async () => {
    const start = RULE_ID_RANGES.lockout[0];
    let ids = await RuleIds.allocate('lockout', 2);
    expect(ids).toEqual([start, start + 1]);
    await RuleIds.release('lockout', [start]);
    ids = await RuleIds.allocate('lockout', 1);
    expect(ids).toEqual([start]);
  });

  test('errors when out of space', async () => {
    const prev = RULE_ID_RANGES.lockout;
    RULE_ID_RANGES.lockout = [10000, 10002];
    try {
      const ids = await RuleIds.allocate('lockout', 3);
      expect(ids).toEqual([10000, 10001, 10002]);
      await expect(RuleIds.allocate('lockout', 1))
        .rejects.toThrow('Insufficient rule IDs in lockout range');
      expect(storage['activeRuleIds:lockout']).toEqual([10000, 10001, 10002]);
      expect(storage['freeRuleIds:lockout']).toEqual([]);
    } finally {
      RULE_ID_RANGES.lockout = prev;
    }
  });

  test('feature isolation for active lists', async () => {
    const startLock = RULE_ID_RANGES.lockout[0];
    const startWord = RULE_ID_RANGES.wordBlocker[0];
    await RuleIds.allocate('lockout', 1);
    await RuleIds.allocate('wordBlocker', 1);
    expect(storage['activeRuleIds:lockout']).toEqual([startLock]);
    expect(storage['activeRuleIds:wordBlocker']).toEqual([startWord]);
  });

  test('updateDynamicRules releases removed ids to free list', async () => {
    const start = RULE_ID_RANGES.lockout[0];
    storage['activeRuleIds:lockout'] = [start];
    await RuleIds.updateDynamicRules({ removeRuleIds: [start] });
    expect(updateDynamicRules).toHaveBeenCalledWith({ removeRuleIds: [start] });
    expect(storage['activeRuleIds:lockout']).toBeUndefined();
    expect(storage['freeRuleIds:lockout']).toEqual([start]);
  });

  test('setActive overwrites active list', async () => {
    const start = RULE_ID_RANGES.lockout[0];
    await RuleIds.setActive('lockout', [start]);
    expect(storage['activeRuleIds:lockout']).toEqual([start]);
    await RuleIds.setActive('lockout', []);
    expect(storage['activeRuleIds:lockout']).toBeUndefined();
  });
});

