import { isChatGPT, getNonChatGPTReferrer } from '../src/lockout/redirector.js';

describe('redirector utilities', () => {
  afterEach(() => {
    Object.defineProperty(document, 'referrer', { value: '', configurable: true });
  });

  test('isChatGPT detects ChatGPT URLs', () => {
    expect(isChatGPT('https://chatgpt.com/foo')).toBe(true);
    expect(isChatGPT('https://example.com')).toBe(false);
  });

  test('getNonChatGPTReferrer returns referrer only when not ChatGPT', () => {
    Object.defineProperty(document, 'referrer', {
      value: 'https://example.com/path',
      configurable: true,
    });
    expect(getNonChatGPTReferrer()).toBe('https://example.com/path');

    Object.defineProperty(document, 'referrer', {
      value: 'https://chatgpt.com/bar',
      configurable: true,
    });
    expect(getNonChatGPTReferrer()).toBeNull();
  });
});
