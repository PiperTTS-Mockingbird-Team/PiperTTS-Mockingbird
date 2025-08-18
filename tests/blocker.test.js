import * as blocker from '../src/background/blocker.js';

describe('applyDynamicBlockRules', () => {
  let updateDynamicRules;
  let storageSet;

  beforeEach(() => {
    updateDynamicRules = jest.fn().mockResolvedValue();
    storageSet = jest.fn().mockResolvedValue();
    globalThis.chrome = {
      declarativeNetRequest: { updateDynamicRules },
      storage: { local: { set: storageSet } }
    };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('constructs rule IDs starting at 10000 and saves them', async () => {
    await blocker.applyDynamicBlockRules(['a.com', 'b.com']);
    const ids = [10000, 10001];
    expect(updateDynamicRules).toHaveBeenCalledWith({
      removeRuleIds: ids,
      addRules: expect.arrayContaining([
        expect.objectContaining({ id: 10000 }),
        expect.objectContaining({ id: 10001 })
      ])
    });
    expect(storageSet).toHaveBeenCalledWith({ activeRuleIds: ids });
  });
});

describe('clearDynamicBlockRules', () => {
  let updateDynamicRules;
  let storageGet;
  let storageRemove;

  beforeEach(() => {
    updateDynamicRules = jest.fn().mockResolvedValue();
    storageGet = jest.fn().mockResolvedValue({ activeRuleIds: [10000, 10001] });
    storageRemove = jest.fn().mockResolvedValue();
    globalThis.chrome = {
      declarativeNetRequest: { updateDynamicRules },
      storage: { local: { get: storageGet, remove: storageRemove } }
    };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('removes stored rule IDs', async () => {
    await blocker.clearDynamicBlockRules();
    expect(storageGet).toHaveBeenCalledWith('activeRuleIds');
    expect(updateDynamicRules).toHaveBeenCalledWith({ removeRuleIds: [10000, 10001] });
    expect(storageRemove).toHaveBeenCalledWith('activeRuleIds');
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

  beforeEach(() => {
    updateEnabledRulesets = jest.fn().mockResolvedValue();
    updateDynamicRules = jest.fn().mockResolvedValue();
    storageGet = jest.fn().mockResolvedValue({ activeRuleIds: [10000] });
    storageRemove = jest.fn().mockResolvedValue();
    globalThis.chrome = {
      declarativeNetRequest: { updateEnabledRulesets, updateDynamicRules },
      storage: { local: { get: storageGet, remove: storageRemove } }
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
    expect(updateDynamicRules).toHaveBeenCalledWith({ removeRuleIds: [10000] });
    expect(storageRemove).toHaveBeenCalledWith('activeRuleIds');
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

  beforeEach(() => {
    storageGet = jest.fn((key) => {
      if (key === 'goal') return Promise.resolve({ goal: 'Stay focused' });
      if (key === 'blockedSites') return Promise.resolve({ blockedSites: ['blocked.com'] });
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
    const tab = { id: 1, url: 'https://blocked.com/page' };
    await blocker.lockOutTab(tab, 1000);
    expect(storageSet).toHaveBeenCalledWith(expect.objectContaining({
      [`origUrl_${tab.id}`]: tab.url,
      lockoutUntil: expect.any(Number),
      goal: 'Stay focused'
    }));
    expect(tabsUpdate).toHaveBeenCalledWith(tab.id, {
      url: expect.stringContaining('pages/lockout.html')
    });
    expect(alarmsCreate).toHaveBeenCalledWith('unlock', { when: expect.any(Number) });
  });

  test('does not redirect or store when already on lockout page', async () => {
    const lockoutUrl = runtimeGetURL('pages/lockout.html');
    const tab = { id: 1, url: `${lockoutUrl}?tabId=1` };
    await blocker.lockOutTab(tab, 1000);
    expect(tabsUpdate).not.toHaveBeenCalled();
    expect(storageSet).not.toHaveBeenCalled();
  });
});
