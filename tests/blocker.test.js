import * as blocker from '../src/background/blocker.js';
import * as dnrManager from '../src/background/dynamic-rule-manager.js';
import { START_ID } from '../src/background/rule-ids.js';

describe('applyDynamicRules', () => {
  let updateDynamicRules;
  let getDynamicRules;
  let storageSet;
  let storageGet;
  let storageRemove;
  let store;

  beforeEach(() => {
    updateDynamicRules = jest.fn().mockResolvedValue();
    getDynamicRules = jest.fn().mockResolvedValue([]);
    store = {};
    storageSet = jest.fn((obj) => { Object.assign(store, obj); return Promise.resolve(); });
    storageGet = jest.fn((key) => {
      if (typeof key === 'string') return Promise.resolve({ [key]: store[key] });
      const result = {};
      for (const k of key) result[k] = store[k];
      return Promise.resolve(result);
    });
    storageRemove = jest.fn((key) => { delete store[key]; return Promise.resolve(); });
    globalThis.chrome = {
      declarativeNetRequest: { updateDynamicRules, getDynamicRules },
      storage: { local: { get: storageGet, set: storageSet, remove: storageRemove } }
    };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('constructs rule IDs starting at START_ID and saves them', async () => {
    await dnrManager.applyDynamicRules(['a.com', 'b.com']);
    const ids = [START_ID, START_ID + 1];
    expect(updateDynamicRules).toHaveBeenCalledWith({
      removeRuleIds: [],
      addRules: expect.arrayContaining([
        expect.objectContaining({ id: START_ID }),
        expect.objectContaining({ id: START_ID + 1 })
      ])
    });
    expect(storageSet).toHaveBeenCalledWith({ activeRuleIds: ids });
  });

  test('formats urlFilter for each site', async () => {
    await dnrManager.applyDynamicRules(['https://a.com']);
    const addRules = updateDynamicRules.mock.calls[0][0].addRules;
    expect(addRules[0].condition.urlFilter).toBe('||a.com^');
  });

  test('clears rules when sites is not an array', async () => {
    storageGet.mockImplementation((key) => {
      if (key === 'activeRuleIds') return Promise.resolve({ activeRuleIds: [START_ID] });
      return Promise.resolve({});
    });
    await dnrManager.applyDynamicRules(null);
    expect(updateDynamicRules).toHaveBeenCalledWith({ removeRuleIds: [START_ID] });
    expect(storageRemove).toHaveBeenCalledWith('activeRuleIds');
  });

  test('removes stale IDs in reserved range before adding', async () => {
    getDynamicRules.mockResolvedValue([{ id: START_ID }, { id: START_ID + 2 }, { id: 5 }]);
    store.activeRuleIds = [START_ID, START_ID + 2];
    await dnrManager.applyDynamicRules(['a.com']);
    const removeIds = updateDynamicRules.mock.calls[0][0].removeRuleIds;
    expect(removeIds).toEqual(expect.arrayContaining([START_ID, START_ID + 2]));
    expect(removeIds).not.toContain(5);
    expect(storageSet).toHaveBeenCalledWith({ activeRuleIds: [START_ID] });
  });
});

describe('manageDynamicRules clear', () => {
  let updateDynamicRules;
  let storageGet;
  let storageRemove;
  let storageSet;

  beforeEach(() => {
    updateDynamicRules = jest.fn().mockResolvedValue();
    storageGet = jest.fn((key) => {
      if (key === 'activeRuleIds') return Promise.resolve({ activeRuleIds: [START_ID, START_ID + 1] });
      return Promise.resolve({});
    });
    storageSet = jest.fn().mockResolvedValue();
    storageRemove = jest.fn().mockResolvedValue();
    globalThis.chrome = {
      declarativeNetRequest: { updateDynamicRules },
      storage: { local: { get: storageGet, set: storageSet, remove: storageRemove } }
    };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('removes stored rule IDs', async () => {
    await dnrManager.manageDynamicRules('clear');
    expect(storageGet).toHaveBeenCalledWith('activeRuleIds');
    expect(updateDynamicRules).toHaveBeenCalledWith({ removeRuleIds: [START_ID, START_ID + 1] });
    expect(storageRemove).toHaveBeenCalledWith('activeRuleIds');
  });

  test('does nothing when no active rule IDs', async () => {
    storageGet.mockImplementation((key) => {
      if (key === 'activeRuleIds') return Promise.resolve({ activeRuleIds: [] });
      return Promise.resolve({});
    });
    await dnrManager.manageDynamicRules('clear');
    expect(storageGet).toHaveBeenCalledWith('activeRuleIds');
    expect(updateDynamicRules).not.toHaveBeenCalled();
    expect(storageRemove).not.toHaveBeenCalled();
  });
});

describe('enableBlockRules', () => {
  let updateEnabledRulesets;

  beforeEach(() => {
    updateEnabledRulesets = jest.fn().mockResolvedValue();
    globalThis.chrome = { declarativeNetRequest: { updateEnabledRulesets } };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('enables static ruleset', async () => {
    await blocker.enableBlockRules();
    expect(updateEnabledRulesets).toHaveBeenCalledWith({
      enableRulesetIds: ['block-chatgpt']
    });
  });
});

describe('disableBlockRules', () => {
  let updateEnabledRulesets;
  let updateDynamicRules;
  let storageGet;
  let storageRemove;
  let storageSet;

  beforeEach(() => {
    updateEnabledRulesets = jest.fn().mockResolvedValue();
    updateDynamicRules = jest.fn().mockResolvedValue();
    storageGet = jest.fn((key) => {
      if (key === 'activeRuleIds') return Promise.resolve({ activeRuleIds: [START_ID] });
      return Promise.resolve({});
    });
    storageSet = jest.fn().mockResolvedValue();
    storageRemove = jest.fn().mockResolvedValue();
    globalThis.chrome = {
      declarativeNetRequest: { updateEnabledRulesets, updateDynamicRules },
      storage: { local: { get: storageGet, set: storageSet, remove: storageRemove } }
    };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('disables static ruleset and clears dynamic rules', async () => {
    await blocker.disableBlockRules();
    expect(updateEnabledRulesets).toHaveBeenCalledWith({
      disableRulesetIds: ['block-chatgpt']
    });
    expect(storageGet).toHaveBeenCalledWith('activeRuleIds');
    expect(updateDynamicRules).toHaveBeenCalledWith({ removeRuleIds: [START_ID] });
    expect(storageRemove).toHaveBeenCalledWith('activeRuleIds');
  });
});

describe('getBlockedSites', () => {
  let storageGet;

  beforeEach(() => {
    storageGet = jest.fn().mockResolvedValue({ blockedSites: [' a.com ', '', 5, 'b.com'] });
    globalThis.chrome = { storage: { local: { get: storageGet } } };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('returns sanitized array', async () => {
    const result = await dnrManager.getBlockedSites();
    expect(result).toEqual(['a.com', 'b.com']);
    expect(storageGet).toHaveBeenCalledWith('blockedSites');
  });
});

describe('shouldBlockUrl', () => {
  let storageGet;

  beforeEach(() => {
    storageGet = jest.fn().mockResolvedValue({ blockedSites: ['blocked.com'] });
    globalThis.chrome = { storage: { local: { get: storageGet } } };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('returns true for URLs containing blocked domains', async () => {
    const result = await blocker.shouldBlockUrl('https://blocked.com/page');
    expect(result).toBe(true);
    expect(storageGet).toHaveBeenCalledWith('blockedSites');
  });

  test('returns false for URLs without blocked domains', async () => {
    const result = await blocker.shouldBlockUrl('https://allowed.com/page');
    expect(result).toBe(false);
    expect(storageGet).toHaveBeenCalledWith('blockedSites');
  });
});

describe('lockOutTab', () => {
  let storageGet;
  let storageSet;
  let tabsUpdate;
  let alarmsCreate;
  let runtimeGetURL;
  let manageDynamicRulesSpy;
  let enableBlockRulesSpy;
  let lockOutTabWithSpies;
  let log;
  let _logger;

  beforeEach(() => {
    manageDynamicRulesSpy = jest.fn().mockResolvedValue();
    enableBlockRulesSpy = jest.fn().mockResolvedValue();
    const getBlockedSites = dnrManager.getBlockedSites;
    const _dynamicRuleManager = { getBlockedSites };
    log = () => {};
    _logger = { log };
    lockOutTabWithSpies = eval(
      '(' +
      blocker.lockOutTab
        .toString()
        .replace(/_dynamicRuleManager\.manageDynamicRules/g, 'manageDynamicRulesSpy')
        .replace('enableBlockRules', 'enableBlockRulesSpy') +
      ')'
    );

    storageGet = jest.fn((key) => {
      if (key === 'goal') return Promise.resolve({ goal: 'Stay focused' });
      if (key === 'blockedSites') return Promise.resolve({ blockedSites: ['blocked.com', 'other.com'] });
      return Promise.resolve({});
    });
    storageSet = jest.fn().mockResolvedValue();
    tabsUpdate = jest.fn().mockResolvedValue();
    alarmsCreate = jest.fn();
    runtimeGetURL = jest.fn().mockReturnValue('chrome-extension://id/pages/lockout.html');
    globalThis.chrome = {
      storage: { local: { get: storageGet, set: storageSet } },
      tabs: { update: tabsUpdate },
      alarms: { create: alarmsCreate },
      runtime: { getURL: runtimeGetURL },
      declarativeNetRequest: {
        updateDynamicRules: jest.fn().mockResolvedValue(),
        updateEnabledRulesets: jest.fn().mockResolvedValue()
      }
    };
  });

  afterEach(() => {
    jest.restoreAllMocks();
    delete globalThis.chrome;
  });

  test('stores the original URL, schedules unlock, and redirects to lockout page', async () => {
    const tab = { id: 1, url: 'https://blocked.com' };
    await lockOutTabWithSpies(tab, 1000);
    expect(storageSet).toHaveBeenCalledWith(expect.objectContaining({
      [`origUrl_${tab.id}`]: tab.url,
      lockoutUntil: expect.any(Number),
      goal: 'Stay focused'
    }));
    expect(tabsUpdate).toHaveBeenCalledWith(tab.id, {
      url: expect.stringContaining('pages/lockout.html')
    });
    expect(alarmsCreate).toHaveBeenCalledWith('unlock', { when: expect.any(Number) });
    expect(manageDynamicRulesSpy).toHaveBeenCalledWith('apply', ['other.com']);
    expect(enableBlockRulesSpy).toHaveBeenCalledTimes(1);
  });

  test('does not redirect or store when already on lockout page', async () => {
    const lockoutUrl = runtimeGetURL('pages/lockout.html');
    const tab = { id: 1, url: `${lockoutUrl}?tabId=1` };
    await lockOutTabWithSpies(tab, 1000);
    expect(tabsUpdate).not.toHaveBeenCalled();
    expect(storageSet).not.toHaveBeenCalled();
  });
});
