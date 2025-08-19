import { RuleIds } from '../src/background/ruleIds.js';

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
    expect(ids).toEqual([10000, 10001]);
    expect(storageSet).toHaveBeenCalledWith({ ruleIds_lock: true });
    expect(storageSet).toHaveBeenCalledWith({ activeRuleIds: [10000, 10001] });
    expect(storageRemove).toHaveBeenCalledWith('ruleIds_lock');
  });

  test('release removes ids and releases lock', async () => {
    storageGet = jest.fn((key) => {
      if (key === 'activeRuleIds') return Promise.resolve({ activeRuleIds: [10000, 10001] });
      return Promise.resolve({});
    });
    globalThis.chrome.storage.local.get = storageGet;
    await RuleIds.release([10000, 10001]);
    expect(storageSet).toHaveBeenCalledWith({ ruleIds_lock: true });
    expect(storageRemove).toHaveBeenCalledWith('activeRuleIds');
    expect(storageRemove).toHaveBeenCalledWith('ruleIds_lock');
  });

  test('updateDynamicRules releases removed ids', async () => {
    const updateDynamicRules = jest.fn().mockResolvedValue();
    storageGet = jest.fn((key) => {
      if (key === 'activeRuleIds') return Promise.resolve({ activeRuleIds: [10000] });
      return Promise.resolve({});
    });
    globalThis.chrome.declarativeNetRequest = { updateDynamicRules };
    globalThis.chrome.storage.local.get = storageGet;
    await RuleIds.updateDynamicRules({ removeRuleIds: [10000] });
    expect(updateDynamicRules).toHaveBeenCalledWith({ removeRuleIds: [10000] });
    expect(storageRemove).toHaveBeenCalledWith('activeRuleIds');
  });
});
