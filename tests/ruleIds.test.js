import { RuleIds, START_ID, RANGES } from '../src/background/rule-ids.js';

describe('RuleIds', () => {
  let storage;
  let storageGet;
  let storageSet;
  let storageRemove;
  let updateDynamicRules;
  let getDynamicRules;

  beforeEach(() => {
    storage = {};
    storageGet = jest.fn((key) => Promise.resolve({ [key]: storage[key] }));
    storageSet = jest.fn((obj) => { Object.assign(storage, obj); return Promise.resolve(); });
    storageRemove = jest.fn((key) => { delete storage[key]; return Promise.resolve(); });
    updateDynamicRules = jest.fn().mockResolvedValue();
    getDynamicRules = jest.fn().mockResolvedValue([]);
    globalThis.chrome = {
      storage: { local: { get: storageGet, set: storageSet, remove: storageRemove } },
      declarativeNetRequest: { updateDynamicRules, getDynamicRules }
    };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('allocate acquires lock and stores ids', async () => {
    const ids = await RuleIds.allocate(2);
    expect(ids).toEqual([START_ID, START_ID + 1]);
    expect(storageSet).toHaveBeenCalledWith({ ruleIds_lock: true });
    expect(storage.activeRuleIds).toEqual([START_ID, START_ID + 1]);
    expect(storageRemove).toHaveBeenCalledWith('ruleIds_lock');
  });

  test('release removes ids and releases lock', async () => {
    storage.activeRuleIds = [START_ID, START_ID + 1];
    await RuleIds.release([START_ID, START_ID + 1]);
    expect(storageSet).toHaveBeenCalledWith({ ruleIds_lock: true });
    expect(storage.activeRuleIds).toBeUndefined();
    expect(storageRemove).toHaveBeenCalledWith('ruleIds_lock');
  });

  test('allocate fills holes within range', async () => {
    storage.activeRuleIds = [START_ID, START_ID + 2];
    const ids = await RuleIds.allocate(1);
    expect(ids).toEqual([START_ID + 1]);
    expect(storage.activeRuleIds).toEqual([START_ID, START_ID + 1, START_ID + 2]);
  });

  test('separate ranges do not overlap', async () => {
    const [lockId] = await RuleIds.allocate(1, 'lockout');
    const [wordId] = await RuleIds.allocate(1, 'wordBlocker');
    expect(lockId).toBe(RANGES.lockout.start);
    expect(wordId).toBe(RANGES.wordBlocker.start);
    expect(storage.activeRuleIds).toEqual([lockId, wordId]);
  });

  test('reconcile syncs storage with dynamic rules', async () => {
    getDynamicRules.mockResolvedValue([{ id: START_ID }, { id: START_ID + 5 }]);
    await RuleIds.reconcile();
    expect(storage.activeRuleIds).toEqual([START_ID, START_ID + 5]);
  });

  test('updateDynamicRules releases removed ids', async () => {
    storage.activeRuleIds = [START_ID];
    await RuleIds.updateDynamicRules({ removeRuleIds: [START_ID] });
    expect(updateDynamicRules).toHaveBeenCalledWith({ removeRuleIds: [START_ID] });
    expect(storage.activeRuleIds).toBeUndefined();
  });
});
