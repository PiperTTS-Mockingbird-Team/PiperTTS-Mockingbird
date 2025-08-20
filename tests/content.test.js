import { jest } from '@jest/globals';

// jsdom lacks innerText; provide a simple polyfill.
Object.defineProperty(HTMLElement.prototype, 'innerText', {
  configurable: true,
  get() { return this.textContent; },
  set(value) { this.textContent = value; }
});

let listener;
let mockData;

describe('getSnippet', () => {
  beforeEach(async () => {
    jest.useFakeTimers();
    mockData = {
      charLimit: 1000,
      focusMode: 'onAllDay',
      focusPhaseMode: null,
      focusPhaseStart: 0,
      G: 5
    };

    global.chrome = {
      runtime: {
        onMessage: {
          addListener: jest.fn(fn => {
            listener = fn;
          })
        },
        sendMessage: jest.fn()
      },
      storage: {
        local: {
          get: jest.fn((keys, cb) => {
            const result = (() => {
              if (typeof keys === 'string') {
                return { [keys]: mockData[keys] };
              }
              if (Array.isArray(keys)) {
                return keys.reduce((acc, k) => ({ ...acc, [k]: mockData[k] }), {});
              }
              return { ...keys, ...mockData };
            })();
            if (typeof cb === 'function') {
              cb(result);
            } else {
              return Promise.resolve(result);
            }
          })
        },
        onChanged: { addListener: jest.fn() }
      }
    };

    await import('../src/content/content.js');
    document.body.innerHTML = '';
  });

  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
    jest.restoreAllMocks();
    document.body.innerHTML = '';
    delete global.chrome;
    jest.resetModules();
  });

  test('returns normalized snippet from markdown/prose elements', () => {
    mockData.charLimit = 1000;
    document.body.innerHTML = `
      <div class="markdown prose">Hello</div>
      <div class="markdown prose">World</div>
    `;
    const sendResponse = jest.fn();
    listener({ action: 'getSnippet', type: 'context' }, null, sendResponse);
    expect(sendResponse).toHaveBeenCalledWith({ snippet: 'hello world' });
  });

  test('truncates context to charLimit but at least 120 chars', () => {
    mockData.charLimit = 150;
    const longText = 'a'.repeat(200);
    document.body.innerHTML = `<div class="markdown">${longText}</div>`;
    const sendResponse = jest.fn();
    listener({ action: 'getSnippet', type: 'context' }, null, sendResponse);
    const snippet = sendResponse.mock.calls[0][0].snippet;
    expect(snippet.length).toBe(150);
  });

  test('returns focus off message', () => {
    mockData.focusMode = 'off';
    const sendResponse = jest.fn();
    listener({ action: 'getSnippet', type: 'status' }, null, sendResponse);
    expect(sendResponse).toHaveBeenCalledWith({ snippet: '[Focus mode is off]' });
  });

  test('returns relax phase message when in relax phase', () => {
    mockData.focusMode = 'cycle';
    mockData.focusPhaseMode = 'cycle';
    mockData.focusPhaseStart = 0;
    mockData.G = 5;
    jest.spyOn(Date, 'now').mockReturnValue(0);
    const sendResponse = jest.fn();
    listener({ action: 'getSnippet', type: 'status' }, null, sendResponse);
    expect(sendResponse).toHaveBeenCalledWith({ snippet: '[In relax phase]' });
  });

  test('retries and returns empty string when no content exists', () => {
    const timeoutSpy = jest.spyOn(global, 'setTimeout');
    const sendResponse = jest.fn();
    listener({ action: 'getSnippet', type: 'context' }, null, sendResponse);
    expect(sendResponse).not.toHaveBeenCalled();
    for (let i = 0; i < 4; i++) {
      jest.advanceTimersByTime(400);
    }
    expect(sendResponse).toHaveBeenCalledWith({ snippet: '' });
    expect(timeoutSpy).toHaveBeenCalledTimes(4);
  });

  test('normalizes text content', () => {
    document.body.innerHTML = `<div class="markdown">He\u200bLLo   WORLD</div>`;
    const sendResponse = jest.fn();
    listener({ action: 'getSnippet', type: 'context' }, null, sendResponse);
    expect(sendResponse).toHaveBeenCalledWith({ snippet: 'hello world' });
  });

  test('handles settingsUpdated and refresh badge interval', async () => {
    listener({ action: 'settingsUpdated' });
    expect(chrome.storage.local.get).toHaveBeenCalledWith(
      ['charLimit', 'gptScanInterval', 'scanInterval', 'blockDuration', 'blockThreshold'],
      expect.any(Function)
    );

    jest.advanceTimersByTime(2000);
    await Promise.resolve();

    expect(chrome.runtime.sendMessage).toHaveBeenCalledWith({
      action: 'refreshBadge',
      payload: expect.any(Object)
    });
  });
});

