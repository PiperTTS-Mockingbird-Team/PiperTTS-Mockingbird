import { jest } from '@jest/globals';
import { RULE_ID_RANGES } from '../src/background/rule-ids.js';

var mockLog;
jest.mock('../src/utils/logger.js', () => {
  mockLog = jest.fn();
  return { logger: jest.fn(() => mockLog), isDebug: () => false };
});
jest.mock('../src/background/dynamic-rule-manager.js', () => ({
  manageDynamicRules: jest.fn().mockResolvedValue(0),
  getBlockedSites: jest.fn()
}));

function createChromeMocks(store) {
  let dynamicRules = [];
  const get = jest.fn((keys) => {
    if (Array.isArray(keys)) {
      const res = {};
      for (const k of keys) res[k] = store[k];
      return Promise.resolve(res);
    }
    return Promise.resolve({ [keys]: store[keys] });
  });
  const set = jest.fn((obj) => { Object.assign(store, obj); return Promise.resolve(); });
  const remove = jest.fn((keys) => {
    if (Array.isArray(keys)) keys.forEach(k => delete store[k]);
    else delete store[keys];
    return Promise.resolve();
  });
  const updateDynamicRules = jest.fn(async ({ addRules = [], removeRuleIds = [] }) => {
    dynamicRules = dynamicRules.filter(r => !removeRuleIds.includes(r.id));
    dynamicRules.push(...addRules);
  });
  const getDynamicRules = jest.fn(async () => dynamicRules);
  const runtime = {
    onInstalled: { addListener: jest.fn() },
    onStartup: { addListener: jest.fn() },
    onMessage: { addListener: jest.fn() },
    getURL: jest.fn(p => p)
  };
  return {
    getDynamicRulesArray: () => dynamicRules,
    setDynamicRulesArray: (rules) => { dynamicRules = rules; },
    chrome: {
      storage: { local: { get, set, remove }, onChanged: { addListener: jest.fn() }, sync: { get: jest.fn(), set: jest.fn() } },
      runtime,
      tabs: { query: jest.fn(), sendMessage: jest.fn(), update: jest.fn(), create: jest.fn(), get: jest.fn(), onActivated: { addListener: jest.fn() } },
      alarms: { create: jest.fn(), onAlarm: { addListener: jest.fn() }, clear: jest.fn() },
      notifications: { create: jest.fn(), onClicked: { addListener: jest.fn() } },
      action: { setBadgeBackgroundColor: jest.fn(), setBadgeText: jest.fn() },
      declarativeNetRequest: { updateDynamicRules, getDynamicRules },
      scripting: { executeScript: jest.fn() },
      webNavigation: { onCommitted: { addListener: jest.fn() } }
    }
  };
}

describe('startup migration of dynamic rule IDs', () => {
  let store;
  let chromeMocks;
  let startupCallbacks;

  beforeEach(async () => {
    jest.resetModules();
    store = {
      lockoutHostIndex: { 'good.com': 10001, 'bad.com': 500 },
      lockoutUntil: 0
    };
    chromeMocks = createChromeMocks(store);
    const { chrome, setDynamicRulesArray, getDynamicRulesArray } = chromeMocks;
    global.chrome = chrome;
    setDynamicRulesArray([
      {
        id: 10001,
        priority: 1,
        action: { type: 'redirect', redirect: { extensionPath: '/pages/lockout.html' } },
        condition: { urlFilter: '||good.com^', resourceTypes: ['main_frame'] }
      },
      {
        id: 500,
        priority: 1,
        action: { type: 'redirect', redirect: { extensionPath: '/pages/lockout.html' } },
        condition: { urlFilter: '||bad.com^', resourceTypes: ['main_frame'] }
      },
      {
        id: 20000,
        priority: 1,
        action: { type: 'redirect', redirect: { extensionPath: '/pages/other.html' } },
        condition: { urlFilter: '||wb.com^', resourceTypes: ['main_frame'] }
      }
    ]);

    await import('../src/background/background.js');
    startupCallbacks = chrome.runtime.onStartup.addListener.mock.calls.map(([cb]) => cb);
    // expose for tests
    chromeMocks.getDynamicRulesArray = getDynamicRulesArray;
  });

  afterEach(() => {
    delete global.chrome;
  });

  test('reassigns out-of-range lockout ids without affecting others', async () => {
    for (const cb of startupCallbacks) {
      await cb();
    }
    const rules = chromeMocks.getDynamicRulesArray();
    const good = rules.find(r => r.condition.urlFilter.includes('good.com'));
    const migrated = rules.find(r => r.condition.urlFilter.includes('bad.com'));
    const wb = rules.find(r => r.condition.urlFilter.includes('wb.com'));

    expect(good.id).toBe(10001);
    expect(migrated.id).toBeGreaterThanOrEqual(RULE_ID_RANGES.lockout[0]);
    expect(migrated.id).toBeLessThanOrEqual(RULE_ID_RANGES.lockout[1]);
    expect(migrated.id).not.toBe(500);
    expect(wb.id).toBe(20000);

    expect(store.lockoutHostIndex).toEqual({
      'good.com': 10001,
      'bad.com': migrated.id
    });
  });
});
