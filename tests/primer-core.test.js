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

  test('finds data-testid prompt textarea', () => {
    document.body.innerHTML = '<div data-testid="prompt-textarea" contenteditable="true"></div>';
    const el = core.getComposer();
    expect(el).not.toBeNull();
    expect(el.getAttribute('data-testid')).toBe('prompt-textarea');
  });

  test('finds role textbox', () => {
    document.body.innerHTML = '<div contenteditable="true" role="textbox"></div>';
    const el = core.getComposer();
    expect(el).not.toBeNull();
    expect(el.getAttribute('role')).toBe('textbox');
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

  test('dispatches Enter key events when contenteditable and no button', async () => {
    jest.useFakeTimers();
    document.body.innerHTML = '<div id="prompt-textarea" contenteditable="true"></div>';
    const el = document.getElementById('prompt-textarea');
    Object.defineProperty(el, 'isContentEditable', { value: true });
    const events = [];
    ['keydown','keypress','keyup'].forEach(type =>
      el.addEventListener(type, e => events.push([type, e.key]))
    );

    const promise = core.sendMessage(el);
    jest.advanceTimersByTime(2100);
    await promise;
    jest.useRealTimers();
    expect(events).toEqual([
      ['keydown','Enter'],
      ['keypress','Enter'],
      ['keyup','Enter'],
    ]);
  });

  test('calls form.requestSubmit when no send button for textarea', async () => {
    jest.useFakeTimers();
    document.body.innerHTML = '<form id="theForm"><textarea id="prompt-textarea"></textarea></form>';
    const el = document.getElementById('prompt-textarea');
    const form = document.getElementById('theForm');
    form.requestSubmit = jest.fn();

    const promise = core.sendMessage(el);
    jest.advanceTimersByTime(2000);
    await promise;
    jest.useRealTimers();
    expect(form.requestSubmit).toHaveBeenCalled();
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

  test('sends primed message and clears storage when priming valid', async () => {
    jest.useFakeTimers();

    const url = new URL('https://example.com/chat?fresh=123');
    const originalLocation = window.location;
    delete window.location;
    window.location = url;

    const ranKey = `primer_ran:${url.pathname}:123`;
    const sessionStore = {};
    const sessionSet = jest.fn((k, v) => { sessionStore[k] = v; });
    const originalSession = window.sessionStorage;
    Object.defineProperty(window, 'sessionStorage', {
      value: {
        getItem: (k) => sessionStore[k] || null,
        setItem: sessionSet,
      },
      configurable: true,
    });

    const removeMock = jest.fn(async () => {});
    const setMock = jest.fn(async () => {});
    global.chrome = {
      storage: {
        local: {
          get: jest.fn(async () => ({
            primedMessage: 'hello',
            redirectPriming: true,
            primeExpiresAt: Date.now() + 1000,
            goal: null,
            primingGraceUntil: null,
            lastPrimedMessage: null,
          })),
          set: setMock,
          remove: removeMock,
        },
      },
    };

    document.body.innerHTML = '<textarea id="prompt-textarea"></textarea>';
    const fakeEl = document.getElementById('prompt-textarea');

    const typeAndSendSpy = jest.fn().mockResolvedValue(true);
    core.__setTypeAndSend(typeAndSendSpy);

    const intervalSpy = jest
      .spyOn(global, 'setInterval')
      .mockImplementation((fn) => { fn(); return 1; });
    const clearSpy = jest.spyOn(global, 'clearInterval').mockImplementation(() => {});

    await core.runPrimerOnce();
    await Promise.resolve();

    expect(typeAndSendSpy).toHaveBeenCalledWith(fakeEl, 'hello', 'hello');
    expect(sessionSet).toHaveBeenCalledWith(ranKey, '1');
    expect(removeMock).toHaveBeenCalledWith(['primedMessage','redirectPriming','primeExpiresAt']);

    intervalSpy.mockRestore();
    clearSpy.mockRestore();
    core.__setTypeAndSend(core._typeAndSend);
    Object.defineProperty(window, 'sessionStorage', { value: originalSession });
    window.location = originalLocation;
    jest.useRealTimers();
  });

  test('cleans up and sets guard after timeout', async () => {
    jest.useFakeTimers();

    const url = new URL('https://example.com/chat?fresh=999');
    const originalLocation = window.location;
    delete window.location;
    window.location = url;

    const ranKey = `primer_ran:${url.pathname}:999`;
    const sessionStore = {};
    const sessionSet = jest.fn((k, v) => { sessionStore[k] = v; });
    const originalSession = window.sessionStorage;
    Object.defineProperty(window, 'sessionStorage', {
      value: {
        getItem: (k) => sessionStore[k] || null,
        setItem: sessionSet,
      },
      configurable: true,
    });

    const removeMock = jest.fn(async () => {});
    const setMock = jest.fn(async () => {});
    global.chrome = {
      storage: {
        local: {
          get: jest.fn(async () => ({
            primedMessage: 'hello',
            redirectPriming: true,
            primeExpiresAt: Date.now() + 1000,
            goal: null,
            primingGraceUntil: null,
            lastPrimedMessage: null,
          })),
          set: setMock,
          remove: removeMock,
        },
      },
    };

    document.body.innerHTML = '';

    await core.runPrimerOnce();
    jest.advanceTimersByTime(60000);
    await Promise.resolve();
    await Promise.resolve();

    expect(sessionSet).toHaveBeenCalledWith(ranKey, '1');
    expect(removeMock).toHaveBeenCalledWith(['primedMessage', 'primeExpiresAt']);
    expect(setMock).toHaveBeenCalledWith({ redirectPriming: false });

    expect(sessionStore[ranKey]).toBe('1');

    Object.defineProperty(window, 'sessionStorage', { value: originalSession });
    window.location = originalLocation;
    jest.useRealTimers();
  });

  test('replaces {hero} with random hero', async () => {
    jest.useFakeTimers();

    const url = new URL('https://example.com/chat?fresh=abc');
    const originalLocation = window.location;
    delete window.location;
    window.location = url;

    const ranKey = `primer_ran:${url.pathname}:abc`;
    const sessionSet = jest.fn();
    const originalSession = window.sessionStorage;
    Object.defineProperty(window, 'sessionStorage', {
      value: { getItem: () => null, setItem: sessionSet },
      configurable: true,
    });

    const heroes = ['Socrates', 'Plato'];
    global.chrome = {
      storage: {
        local: {
          get: jest.fn(async () => ({
            primedMessage: 'Hello {hero}',
            redirectPriming: true,
            primeExpiresAt: Date.now() + 1000,
            goal: '',
            primingGraceUntil: null,
            lastPrimedMessage: null,
            heroes,
          })),
          set: jest.fn(async () => {}),
          remove: jest.fn(async () => {}),
        },
      },
    };

    document.body.innerHTML = '<textarea id="prompt-textarea"></textarea>';
    const fakeEl = document.getElementById('prompt-textarea');

    const typeAndSendSpy = jest.fn().mockResolvedValue(true);
    core.__setTypeAndSend(typeAndSendSpy);

    const origRand = Math.random;
    Math.random = () => 0; // pick first hero

    const intervalSpy = jest
      .spyOn(global, 'setInterval')
      .mockImplementation((fn) => { fn(); return 1; });
    const clearSpy = jest.spyOn(global, 'clearInterval').mockImplementation(() => {});

    await core.runPrimerOnce();
    await Promise.resolve();

    expect(typeAndSendSpy).toHaveBeenCalledWith(fakeEl, 'Hello Socrates', 'Hello Socrates');

    Math.random = origRand;
    intervalSpy.mockRestore();
    clearSpy.mockRestore();
    core.__setTypeAndSend(core._typeAndSend);
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
