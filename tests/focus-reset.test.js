import { resetFocusModeOnStartup } from '../src/background/reset-focus-mode.js';

function createStorage(store) {
  return {
    get: jest.fn((keys) => {
      if (Array.isArray(keys)) {
        const res = {};
        keys.forEach(k => { res[k] = store[k]; });
        return Promise.resolve(res);
      }
      return Promise.resolve({ [keys]: store[keys] });
    }),
    set: jest.fn((obj) => {
      Object.assign(store, obj);
      return Promise.resolve();
    })
  };
}

describe('resetFocusModeOnStartup', () => {
  afterEach(() => {
    delete global.chrome;
  });

  test('defaults to onAllDay when flag is absent', async () => {
    const store = { focusMode: 'off', score: 6, lockoutUntil: 0, manualUILockUntil: 0 };
    const storage = createStorage(store);
    const action = { setBadgeBackgroundColor: jest.fn(), setBadgeText: jest.fn() };
    global.chrome = { storage: { local: storage }, action };

    await resetFocusModeOnStartup();

    expect(storage.set).toHaveBeenCalledWith({ focusMode: 'onAllDay' });
    expect(store.focusMode).toBe('onAllDay');
    expect(action.setBadgeText).toHaveBeenCalledWith({ text: '🧠6' });
  });

  test('preserves focusMode when resetFocusOnRestart is false', async () => {
    const store = { resetFocusOnRestart: false, focusMode: 'cycle', score: 4, lockoutUntil: 0, manualUILockUntil: 0 };
    const storage = createStorage(store);
    const action = { setBadgeBackgroundColor: jest.fn(), setBadgeText: jest.fn() };
    global.chrome = { storage: { local: storage }, action };

    await resetFocusModeOnStartup();

    expect(storage.set).not.toHaveBeenCalled();
    expect(store.focusMode).toBe('cycle');
    expect(action.setBadgeText).toHaveBeenCalledWith({ text: '☕4' });
  });
});
