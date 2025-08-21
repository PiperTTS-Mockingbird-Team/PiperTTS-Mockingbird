import { parseBlockedSites } from '../src/options/blocked-sites.js';

describe('parseBlockedSites', () => {
  beforeEach(() => {
    globalThis.chrome = {
      runtime: {
        getURL: (path = '') => `chrome-extension://ext-id/${path}`
      }
    };
    globalThis.fetch = jest.fn().mockResolvedValue({
      json: async () => [
        { condition: { urlFilter: '||chat.openai.com^' } },
        { condition: { urlFilter: '||chatgpt.com^' } }
      ]
    });
  });

  afterEach(() => {
    delete globalThis.chrome;
    delete globalThis.fetch;
  });

  test('filters invalid URLs and deduplicates hostnames', async () => {
    const text = 'https://good.com\nfoo bar.com\ngood.com';
    const result = await parseBlockedSites(text);
    expect(result).toEqual(['good.com']);
  });

  test('excludes extension and lockout hosts', async () => {
    const text = 'chrome-extension://ext-id/pages/lockout.html\next-id\nother.com';
    const result = await parseBlockedSites(text);
    expect(result).toEqual(['other.com']);
  });

  test('excludes domains present in rules.json', async () => {
    const text = 'chat.openai.com\nexample.com';
    const result = await parseBlockedSites(text);
    expect(result).toEqual(['example.com']);
  });
});
