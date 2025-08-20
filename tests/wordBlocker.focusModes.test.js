import { jest } from '@jest/globals';

jest.mock('../src/background/blocker.js', () => ({
  shouldBlockUrl: jest.fn().mockResolvedValue(false),
  lockOutTab: jest.fn().mockResolvedValue(),
  enableBlockRules: jest.fn(),
  disableBlockRules: jest.fn(),
}));

function createChromeMocks(store) {
  const getLocal = jest.fn((keys) => {
    if (Array.isArray(keys)) {
      const res = {};
      for (const k of keys) res[k] = store[k];
      return Promise.resolve(res);
    }
    return Promise.resolve({ [keys]: store[keys] });
  });
  const setLocal = jest.fn((obj) => {
    Object.assign(store, obj);
    return Promise.resolve();
  });
  const query = jest.fn().mockResolvedValue([{ id: 1, url: 'https://chat.openai.com/' }]);
  const sendMessage = jest.fn();
  const tabsGet = jest.fn().mockResolvedValue({});
  const onActivated = { addListener: jest.fn() };
  return {
    storage: { local: { get: getLocal, set: setLocal }, onChanged: { addListener: jest.fn() }, sync: { set: jest.fn(), get: jest.fn() } },
    tabs: { query, sendMessage, update: jest.fn(), create: jest.fn(), get: tabsGet, onActivated },
    alarms: { create: jest.fn(), onAlarm: { addListener: jest.fn() }, clear: jest.fn() },
    runtime: { onInstalled: { addListener: jest.fn() }, onStartup: { addListener: jest.fn() }, onMessage: { addListener: jest.fn() }, getURL: jest.fn((p) => p) },
    notifications: { create: jest.fn(), onClicked: { addListener: jest.fn() } },
    action: { setBadgeBackgroundColor: jest.fn(), setBadgeText: jest.fn() },
    declarativeNetRequest: { onRuleMatchedDebug: { addListener: jest.fn() }, getDynamicRules: jest.fn(), updateDynamicRules: jest.fn(), updateEnabledRulesets: jest.fn() },
    scripting: { executeScript: jest.fn() },
    webNavigation: { onCommitted: { addListener: jest.fn() } },
  };
}

describe('word blocker focus modes', () => {
  let store;
  let chromeMocks;
  let onBannedCheckAlarm;

  function seedStorage({ focusMode, cyclePhase, blockedWords }) {
    if (focusMode !== undefined) store.focusMode = focusMode;
    if (cyclePhase !== undefined) store.cyclePhase = cyclePhase;
    if (blockedWords !== undefined) store.blockedWords = blockedWords;
  }

  function mockSnippet(text) {
    chromeMocks.tabs.query.mockResolvedValue([{ id: 1, url: 'https://chat.openai.com/' }]);
    chromeMocks.tabs.sendMessage.mockResolvedValue({ snippet: text, fullSnippet: text });
  }

  async function triggerBannedCheck() {
    await onBannedCheckAlarm({ name: 'bannedCheck' });
  }

  beforeEach(async () => {
    jest.resetModules();
    jest.useFakeTimers();
    store = { score: 5, blockThreshold: 4, focusMode: 'off' };
    chromeMocks = createChromeMocks(store);
    global.chrome = chromeMocks;
    const mod = await import('../src/background/background.js');
    onBannedCheckAlarm = mod.__test__.onBannedCheckAlarm;
  });

  afterEach(() => {
    jest.useRealTimers();
    delete global.chrome;
  });

  test('Focus off → blocked word present ⇒ no action', async () => {
    seedStorage({ focusMode: 'off', blockedWords: ['bad'] });
    mockSnippet('this is a long snippet containing bad word somewhere in text to trigger');
    chromeMocks.storage.local.set.mockClear();
    await triggerBannedCheck();
    expect(chromeMocks.storage.local.set).not.toHaveBeenCalled();
  });

  test('All-day on → blocked word + long snippet ⇒ action (score/lockout)', async () => {
    seedStorage({ focusMode: 'onAllDay', blockedWords: ['bad'] });
    mockSnippet('this is a long snippet containing bad word somewhere in text to trigger');
    chromeMocks.storage.local.set.mockClear();
    await triggerBannedCheck();
    expect(store.score).toBe(4);
    expect(store.lockoutReason).toMatch(/bad/);
  });

  test('Cycle relax ⇒ no action', async () => {
    seedStorage({ focusMode: 'cycle', cyclePhase: 'relax', blockedWords: ['bad'] });
    mockSnippet('this is a long snippet containing bad word somewhere in text to trigger');
    chromeMocks.storage.local.set.mockClear();
    await triggerBannedCheck();
    expect(chromeMocks.storage.local.set).not.toHaveBeenCalled();
  });

  test('Cycle focus + blocked word ⇒ action', async () => {
    seedStorage({ focusMode: 'cycle', cyclePhase: 'focus', blockedWords: ['bad'] });
    mockSnippet('this is a long snippet containing bad word somewhere in text to trigger');
    chromeMocks.storage.local.set.mockClear();
    await triggerBannedCheck();
    expect(store.score).toBe(4);
  });

  test('Short snippet (<30 chars) ⇒ no action', async () => {
    seedStorage({ focusMode: 'onAllDay', blockedWords: ['bad'] });
    mockSnippet('bad word here');
    chromeMocks.storage.local.set.mockClear();
    await triggerBannedCheck();
    expect(chromeMocks.storage.local.set).not.toHaveBeenCalled();
  });

  test('No blocked words ⇒ no action', async () => {
    seedStorage({ focusMode: 'onAllDay', blockedWords: [] });
    mockSnippet('this is a long snippet with nothing banned in it so should do nothing');
    chromeMocks.storage.local.set.mockClear();
    await triggerBannedCheck();
    expect(chromeMocks.storage.local.set).not.toHaveBeenCalled();
  });
});

