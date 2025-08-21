let handlePrimerMessage;

describe('primer handshake', () => {
  beforeEach(async () => {
    global.chrome = {
      storage: {
        local: {
          get: jest.fn(async () => ({ primers: { 1: { primedMessage: 'hi', expiresAt: Date.now() + 1000 }, 2: { primedMessage: 'other', expiresAt: Date.now() + 1000 } } })),
          set: jest.fn(async () => {})
        },
        onChanged: { addListener: jest.fn() }
      },
      tabs: { sendMessage: jest.fn(), update: jest.fn(), query: jest.fn(), get: jest.fn(), onActivated: { addListener: jest.fn() } },
      alarms: { create: jest.fn(), onAlarm: { addListener: jest.fn() }, clear: jest.fn() },
      runtime: { onInstalled: { addListener: jest.fn() }, onStartup: { addListener: jest.fn() }, onMessage: { addListener: jest.fn() }, getURL: jest.fn() },
      notifications: { create: jest.fn(), onClicked: { addListener: jest.fn() } },
      action: { setBadgeBackgroundColor: jest.fn(), setBadgeText: jest.fn() },
      declarativeNetRequest: { onRuleMatchedDebug: { addListener: jest.fn() }, getDynamicRules: jest.fn(), updateDynamicRules: jest.fn(), updateEnabledRulesets: jest.fn() },
      scripting: { executeScript: jest.fn() },
      webNavigation: { onCommitted: { addListener: jest.fn() } }
    };
    const mod = await import('../src/background/background.js');
    handlePrimerMessage = mod.__test__.handlePrimerMessage;
  });

  afterEach(() => { delete global.chrome; jest.resetModules(); });

  test('READY → PAYLOAD → DONE', async () => {
    await handlePrimerMessage({ type: 'PRIMER_READY', tabId: 1, host: 'chatgpt.com' }, { tab: { id: 1 } });
    expect(chrome.tabs.sendMessage).toHaveBeenCalledWith(1, { type: 'PRIMER_PAYLOAD', primedMessage: 'hi' });
    await handlePrimerMessage({ type: 'PRIMER_DONE', tabId: 1 }, { tab: { id: 1 } });
    expect(chrome.storage.local.set).toHaveBeenCalledWith({ primers: { 2: { primedMessage: 'other', expiresAt: expect.any(Number) } } });
  });

  test('tab isolation', async () => {
    await handlePrimerMessage({ type: 'PRIMER_DONE', tabId: 2 }, { tab: { id: 2 } });
    const calls = chrome.storage.local.set.mock.calls;
    const setArg = calls[calls.length - 1][0];
    expect(setArg.primers).toEqual({ 1: { primedMessage: 'hi', expiresAt: expect.any(Number) } });
  });
});
