import { badgeColor, setBadge } from '../src/background/badge.js';

describe('badgeColor', () => {
  test('returns correct colors for score ranges', () => {
    expect(badgeColor(NaN)).toBe('#9E9E9E');
    expect(badgeColor(8)).toBe('#4CAF50');
    expect(badgeColor(6)).toBe('#FFEB3B');
    expect(badgeColor(1)).toBe('#FF9800');
    expect(badgeColor(-1)).toBe('#F44336');
  });
});

describe('setBadge', () => {
  let setBadgeBackgroundColor;
  let setBadgeText;

  beforeEach(() => {
    setBadgeBackgroundColor = jest.fn();
    setBadgeText = jest.fn();
    globalThis.chrome = { action: { setBadgeBackgroundColor, setBadgeText } };
    jest.spyOn(Date, 'now').mockReturnValue(0);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('shows focus mode score and color', async () => {
    const storage = {
      get: jest.fn((key) => {
        if (key === 'score') return Promise.resolve({ score: 6 });
        return Promise.resolve({ lockoutUntil: 0, focusMode: 'onAllDay', manualUILockUntil: 0 });
      })
    };

    await setBadge(null, storage);

    expect(setBadgeBackgroundColor).toHaveBeenCalledWith({ color: '#FFEB3B' });
    expect(setBadgeText).toHaveBeenCalledWith({ text: '🧠6' });
  });

  test('defaults score to 5 and shows unknown focus mode', async () => {
    const storage = {
      get: jest.fn((key) => {
        if (key === 'score') return Promise.resolve({});
        return Promise.resolve({ lockoutUntil: 0, focusMode: 'mystery', manualUILockUntil: 0 });
      })
    };

    await setBadge(null, storage);

    expect(setBadgeBackgroundColor).toHaveBeenCalledWith({ color: '#FFEB3B' });
    expect(setBadgeText).toHaveBeenCalledWith({ text: '❓5' });
  });

  test('indicates lockout with red badge', async () => {
    const storage = {
      get: jest.fn((key) => {
        if (key === 'score') return Promise.resolve({ score: 6 });
        return Promise.resolve({ lockoutUntil: 1000, focusMode: 'onAllDay', manualUILockUntil: 0 });
      })
    };

    await setBadge(null, storage);

    expect(setBadgeBackgroundColor).toHaveBeenCalledWith({ color: '#F44336' });
    expect(setBadgeText).toHaveBeenCalledWith({ text: '⛔6' });
  });

  test('underlines score when manually locked', async () => {
    const storage = {
      get: jest.fn((key) => {
        if (key === 'score') return Promise.resolve({ score: 6 });
        return Promise.resolve({ lockoutUntil: 0, focusMode: 'off', manualUILockUntil: 1000 });
      })
    };

    await setBadge(null, storage);

    const underline = (s) => [...s].map(ch => ch + '\u0332').join('');
    expect(setBadgeBackgroundColor).toHaveBeenCalledWith({ color: '#FFEB3B' });
    expect(setBadgeText).toHaveBeenCalledWith({ text: '🚫' + underline('6') });
  });

  test('shows timer mode emoji', async () => {
    const storage = {
      get: jest.fn((key) => {
        if (key === 'score') return Promise.resolve({ score: 6 });
        return Promise.resolve({ lockoutUntil: 0, focusMode: 'timer', manualUILockUntil: 0 });
      })
    };

    await setBadge(null, storage);

    expect(setBadgeBackgroundColor).toHaveBeenCalledWith({ color: '#FFEB3B' });
    expect(setBadgeText).toHaveBeenCalledWith({ text: '🕒6' });
  });

  test('shows cycle mode emoji', async () => {
    const storage = {
      get: jest.fn((key) => {
        if (key === 'score') return Promise.resolve({ score: 6 });
        return Promise.resolve({ lockoutUntil: 0, focusMode: 'cycle', manualUILockUntil: 0 });
      })
    };

    await setBadge(null, storage);

    expect(setBadgeBackgroundColor).toHaveBeenCalledWith({ color: '#FFEB3B' });
    expect(setBadgeText).toHaveBeenCalledWith({ text: '☕6' });
  });

  test('shows cycleFocus mode emoji', async () => {
    const storage = {
      get: jest.fn((key) => {
        if (key === 'score') return Promise.resolve({ score: 6 });
        return Promise.resolve({ lockoutUntil: 0, focusMode: 'cycleFocus', manualUILockUntil: 0 });
      })
    };

    await setBadge(null, storage);

    expect(setBadgeBackgroundColor).toHaveBeenCalledWith({ color: '#FFEB3B' });
    expect(setBadgeText).toHaveBeenCalledWith({ text: '💼6' });
  });

  test('clamps very low scores to -5', async () => {
    const storage = {
      get: jest.fn((key) => {
        if (key === 'score') return Promise.resolve({ score: -10 });
        return Promise.resolve({ lockoutUntil: 0, focusMode: 'onAllDay', manualUILockUntil: 0 });
      })
    };

    await setBadge(null, storage);

    expect(setBadgeBackgroundColor).toHaveBeenCalledWith({ color: '#F44336' });
    expect(setBadgeText).toHaveBeenCalledWith({ text: '🧠-5' });
  });
});

