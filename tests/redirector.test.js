import { jest } from '@jest/globals';

let getRedirectTarget;
let storageGet;

describe('getRedirectTarget', () => {
  beforeEach(async () => {
    storageGet = jest.fn().mockResolvedValue({});
    globalThis.chrome = { storage: { local: { get: storageGet } } };
    ({ getRedirectTarget } = await import('../src/lockout/redirector.js'));
  });

  afterEach(() => {
    delete globalThis.chrome;
    jest.resetModules();
  });

  test('normalizes encoded ChatGPT URLs', async () => {
    const orig = encodeURIComponent('https://chat.openai.com/chat/123');
    const result = await getRedirectTarget(orig);
    expect(result).toMatch(/^https:\/\/chatgpt\.com\/\?fresh=\d+$/);
    expect(storageGet).toHaveBeenCalledTimes(1);
    expect(storageGet).toHaveBeenCalledWith('debug');
  });

  test('falls back to storage and normalizes ChatGPT URLs', async () => {
    storageGet.mockImplementation(async (key) => ({ [key]: 'https://chat.openai.com/chat/abc' }));
    const result = await getRedirectTarget('', 7);
    expect(storageGet).toHaveBeenCalledWith('debug');
    expect(storageGet).toHaveBeenCalledWith('origUrl_7');
    expect(storageGet).toHaveBeenCalledTimes(2);
    expect(result).toMatch(/^https:\/\/chatgpt\.com\/\?fresh=\d+$/);
  });

  test('returns non-ChatGPT URLs unchanged', async () => {
    const url = 'https://example.com/page';
    const result = await getRedirectTarget(encodeURIComponent(url));
    expect(result).toBe(url);
    expect(storageGet).toHaveBeenCalledTimes(1);
    expect(storageGet).toHaveBeenCalledWith('debug');
  });

  test('handles invalid encodings safely', async () => {
    const bad = '%E0%A4%A';
    const result = await getRedirectTarget(bad);
    expect(result).toBe(bad);
    expect(storageGet).toHaveBeenCalledTimes(1);
    expect(storageGet).toHaveBeenCalledWith('debug');
  });
});
