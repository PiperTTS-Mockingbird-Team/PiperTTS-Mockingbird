const FakeInputEvent = class extends Event { constructor(type, params){ super(type, params); this.data = params?.data; this.inputType = params?.inputType; } };
if (typeof globalThis.InputEvent === "undefined") globalThis.InputEvent = FakeInputEvent;

import * as core from '../src/utils/primer-core.js';

describe('getComposer', () => {
  test('finds contenteditable textarea', () => {
    document.body.innerHTML = '<div id="prompt-textarea" contenteditable="true"></div>';
    const el = core.getComposer();
    expect(el).not.toBeNull();
    expect(el.id).toBe('prompt-textarea');
  });
});

describe('insertText', () => {
  test('inserts into contenteditable', () => {
    document.body.innerHTML = '<div id="prompt-textarea" contenteditable="true"></div>';
    const el = document.getElementById('prompt-textarea');
    core.insertText(el, 'hello');
    expect(el.textContent).toBe('hello');
  });

  test('inserts into textarea', () => {
    document.body.innerHTML = '<textarea id="prompt-textarea"></textarea>';
    const el = document.getElementById('prompt-textarea');
    core.insertText(el, 'hello');
    expect(el.value).toBe('hello');
  });
});

describe('sendMessage', () => {
   test('clicks available send button', async () => {
    jest.useFakeTimers();
    document.body.innerHTML = `
        <textarea id="prompt-textarea"></textarea>
        <button id="sendBtn" data-testid="send-button">Send</button>
    `;
    const el = document.getElementById('prompt-textarea');
    const btn = document.getElementById('sendBtn');
    let clicked = false;
    btn.addEventListener('click', () => { clicked = true; });

    const promise = core.sendMessage(el);
    jest.advanceTimersByTime(200);
    await promise;
    jest.useRealTimers();
    expect(clicked).toBe(true);
  });
});

describe('typeAndSend', () => {
  test('skips insertion if user typed a different message', async () => {
    const el = document.createElement('textarea');
    el.value = 'user text';
    document.body.appendChild(el);

    const insertSpy = jest.spyOn(core, 'insertText');
    const sendSpy = jest.spyOn(core, 'sendMessage').mockResolvedValue(true);
    global.chrome = { storage: { local: { remove: jest.fn(async () => {}) } } };

    const result = await core.typeAndSend(el, 'primed', 'primed');

    expect(result).toBe(true);
    expect(insertSpy).not.toHaveBeenCalled();
    expect(sendSpy).not.toHaveBeenCalled();
    expect(global.chrome.storage.local.remove).toHaveBeenCalledWith(['primedMessage','redirectPriming','primeExpiresAt']);
  });
});

describe('runPrimerOnce', () => {
  test('exits when already ran for same path and fresh flag', async () => {
    jest.useFakeTimers();

    const url = new URL('https://example.com/foo?fresh=abc');
    const originalLocation = window.location;
    delete window.location;
    window.location = url;

    const ranKey = `primer_ran:${url.pathname}:abc`;
    const sessionGet = jest.fn((key) => (key === ranKey ? '1' : null));
    const sessionSet = jest.fn();
    const originalSession = window.sessionStorage;
    Object.defineProperty(window, 'sessionStorage', {
      value: { getItem: sessionGet, setItem: sessionSet },
      configurable: true,
    });

    global.chrome = { storage: { local: { get: jest.fn(), set: jest.fn(), remove: jest.fn() } } };
    const composerSpy = jest.spyOn(core, 'getComposer');

    await core.runPrimerOnce();

    expect(global.chrome.storage.local.get).not.toHaveBeenCalled();
    expect(global.chrome.storage.local.set).not.toHaveBeenCalled();
    expect(global.chrome.storage.local.remove).not.toHaveBeenCalled();
    expect(composerSpy).not.toHaveBeenCalled();

    composerSpy.mockRestore();
    Object.defineProperty(window, 'sessionStorage', { value: originalSession });
    window.location = originalLocation;
    jest.useRealTimers();
  });

  test('removes expired priming data', async () => {
    jest.useFakeTimers();
    const now = new Date('2024-01-01T00:00:00Z');
    jest.setSystemTime(now);

    const url = new URL('https://example.com/chat?fresh=123');
    const originalLocation = window.location;
    delete window.location;
    window.location = url;

    const sessionGet = jest.fn(() => null);
    const sessionSet = jest.fn();
    const originalSession = window.sessionStorage;
    Object.defineProperty(window, 'sessionStorage', {
      value: { getItem: sessionGet, setItem: sessionSet },
      configurable: true,
    });

    const removeMock = jest.fn(async () => {});
    global.chrome = {
      storage: {
        local: {
          get: jest.fn(async () => ({
            primedMessage: 'msg',
            redirectPriming: true,
            primeExpiresAt: Date.now() - 1000,
            goal: 'g',
            primingGraceUntil: null,
            lastPrimedMessage: null,
          })),
          set: jest.fn(),
          remove: removeMock,
        },
      },
    };

    const composerSpy = jest.spyOn(core, 'getComposer');

    await core.runPrimerOnce();

    expect(removeMock).toHaveBeenCalledWith(['primedMessage','redirectPriming','primeExpiresAt']);
    expect(composerSpy).not.toHaveBeenCalled();
    expect(sessionSet).not.toHaveBeenCalled();

    composerSpy.mockRestore();
    Object.defineProperty(window, 'sessionStorage', { value: originalSession });
    window.location = originalLocation;
    jest.useRealTimers();
  });
});
