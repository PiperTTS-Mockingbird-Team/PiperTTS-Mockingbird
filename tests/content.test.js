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

  test('returns snippet from markdown prose elements', () => {
    mockData.charLimit = 5;
    document.body.innerHTML = `
      <div class="markdown prose">Hello</div>
      <div class="markdown prose">World</div>
    `;
    const sendResponse = jest.fn();
    listener({ action: 'getSnippet' }, null, sendResponse);
    expect(sendResponse).toHaveBeenCalledWith({ snippet: 'World' });
  });

  test('truncates combined markdown text to charLimit', () => {
    mockData.charLimit = 10;
    document.body.innerHTML = `
      <div class="markdown prose">Lorem ipsum</div>
      <div class="markdown prose">dolor</div>
    `;
    const sendResponse = jest.fn();
    listener({ action: 'getSnippet' }, null, sendResponse);
    const expected = 'Lorem ipsum dolor'.slice(-mockData.charLimit);
    const snippet = sendResponse.mock.calls[0][0].snippet;
    expect(snippet.length).toBeLessThanOrEqual(mockData.charLimit);
    expect(snippet).toBe(expected);
  });

  test('returns focus off message', () => {
    mockData.focusMode = 'off';
    const sendResponse = jest.fn();
    listener({ action: 'getSnippet' }, null, sendResponse);
    expect(sendResponse).toHaveBeenCalledWith({ snippet: '[Focus mode is off]' });
  });

  test('returns relax phase message when in relax phase', () => {
    mockData.focusMode = 'cycle';
    mockData.focusPhaseMode = 'cycle';
    mockData.focusPhaseStart = 0;
    mockData.G = 5;
    jest.spyOn(Date, 'now').mockReturnValue(0);
    const sendResponse = jest.fn();
    listener({ action: 'getSnippet' }, null, sendResponse);
    expect(sendResponse).toHaveBeenCalledWith({ snippet: '[In relax phase]' });
  });

  test('retries and returns no content found when no markdown prose elements exist', () => {
    const timeoutSpy = jest.spyOn(global, 'setTimeout');
    const sendResponse = jest.fn();
    listener({ action: 'getSnippet' }, null, sendResponse);
    expect(sendResponse).not.toHaveBeenCalled();
    for (let i = 0; i < 4; i++) {
      jest.advanceTimersByTime(400);
    }
    expect(sendResponse).toHaveBeenCalledWith({ snippet: '[No content found]' });
    expect(timeoutSpy).toHaveBeenCalledTimes(4);
  });
});

