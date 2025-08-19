import { RuleIds, START_ID } from '../src/background/rule-ids.js';

describe('RuleIds', () => {
  let storageGet;
  let storageSet;
  let storageRemove;

  beforeEach(() => {
    storageGet = jest.fn((key) => {
      if (key === 'activeRuleIds') return Promise.resolve({ activeRuleIds: [] });
      return Promise.resolve({});
    });
    storageSet = jest.fn().mockResolvedValue();
    storageRemove = jest.fn().mockResolvedValue();
    globalThis.chrome = { storage: { local: { get: storageGet, set: storageSet, remove: storageRemove } } };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('allocate acquires lock and stores ids', async () => {
    const ids = await RuleIds.allocate(2);
    expect(ids).toEqual([START_ID, START_ID + 1]);
    expect(storageSet).toHaveBeenCalledWith({ ruleIds_lock: true });
    expect(storageSet).toHaveBeenCalledWith({ activeRuleIds: [START_ID, START_ID + 1] });
    expect(storageRemove).toHaveBeenCalledWith('ruleIds_lock');
  });

  test('release removes ids and releases lock', async () => {
    storageGet = jest.fn((key) => {
      if (key === 'activeRuleIds') return Promise.resolve({ activeRuleIds: [START_ID, START_ID + 1] });
      return Promise.resolve({});
    });
    globalThis.chrome.storage.local.get = storageGet;
    await RuleIds.release([START_ID, START_ID + 1]);
    expect(storageSet).toHaveBeenCalledWith({ ruleIds_lock: true });
    expect(storageRemove).toHaveBeenCalledWith('activeRuleIds');
    expect(storageRemove).toHaveBeenCalledWith('ruleIds_lock');
  });

  test('updateDynamicRules releases removed ids', async () => {
    const updateDynamicRules = jest.fn().mockResolvedValue();
    storageGet = jest.fn((key) => {
      if (key === 'activeRuleIds') return Promise.resolve({ activeRuleIds: [START_ID] });
      return Promise.resolve({});
    });
    globalThis.chrome.declarativeNetRequest = { updateDynamicRules };
    globalThis.chrome.storage.local.get = storageGet;
    await RuleIds.updateDynamicRules({ removeRuleIds: [START_ID] });
    expect(updateDynamicRules).toHaveBeenCalledWith({ removeRuleIds: [START_ID] });
    expect(storageRemove).toHaveBeenCalledWith('activeRuleIds');
  });
});
