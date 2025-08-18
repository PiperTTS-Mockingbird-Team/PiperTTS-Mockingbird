import { fetchGPTJudgment } from '../src/utils/gpt-api.js';

beforeEach(() => {
  global.chrome = {
    storage: {
      local: { get: jest.fn() },
      sync: { get: jest.fn() }
    }
  };
  global.fetch = jest.fn();
});

afterEach(() => {
  jest.resetAllMocks();
  delete global.chrome;
  delete global.fetch;
});

describe('fetchGPTJudgment', () => {
  test('returns No with missingKey when no provider keys', async () => {
    chrome.storage.local.get.mockResolvedValue({});
    chrome.storage.sync.get.mockResolvedValue({
      providers: [
        { name: 'openai', order: 1 },
        { name: 'gemini', order: 2 }
      ]
    });

    const result = await fetchGPTJudgment('snippet');

    expect(result).toEqual({ judgment: 'No', missingKey: true });
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('parses OpenAI provider response', async () => {
    chrome.storage.local.get.mockResolvedValue({ goal: 'Goal' });
    chrome.storage.sync.get.mockResolvedValue({
      providers: [{ name: 'openai', key: 'abc', order: 1 }]
    });
    global.fetch.mockResolvedValue({
      json: async () => ({
        choices: [{ message: { content: '  Yes  ' } }]
      })
    });

    const result = await fetchGPTJudgment('test');

    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(result).toEqual({ judgment: 'Yes' });
  });

  test('providers are tried in ascending order', async () => {
    chrome.storage.local.get.mockResolvedValue({});
    chrome.storage.sync.get.mockResolvedValue({
      providers: [
        { name: 'openai', key: 'openai-key', order: 2 },
        { name: 'gemini', key: 'gemini-key', order: 1 }
      ]
    });
    global.fetch
      .mockResolvedValueOnce({ json: async () => ({}) })
      .mockResolvedValueOnce({
        json: async () => ({
          choices: [{ message: { content: 'No' } }]
        })
      });

    const result = await fetchGPTJudgment('hi');

    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(global.fetch.mock.calls[0][0]).toContain('generativelanguage.googleapis.com');
    expect(global.fetch.mock.calls[1][0]).toContain('api.openai.com');
    expect(result).toEqual({ judgment: 'No' });
  });
  test('continues to next provider if earlier ones fail', async () => {
    chrome.storage.local.get.mockResolvedValue({});
    chrome.storage.sync.get.mockResolvedValue({
      providers: [
        { name: 'gemini', key: 'gemini-key', order: 1 },
        { name: 'openai', key: 'openai-key', order: 2 }
      ]
    });
    global.fetch
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce({
        json: async () => ({
          choices: [{ message: { content: 'Yes' } }]
        })
      });

    const result = await fetchGPTJudgment('hi');

    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(global.fetch.mock.calls[0][0]).toContain('generativelanguage.googleapis.com');
    expect(global.fetch.mock.calls[1][0]).toContain('api.openai.com');
    expect(result).toEqual({ judgment: 'Yes' });
  });

  test('returns null judgment when all providers fail', async () => {
    chrome.storage.local.get.mockResolvedValue({});
    chrome.storage.sync.get.mockResolvedValue({
      providers: [
        { name: 'openai', key: 'openai-key', order: 1 },
        { name: 'gemini', key: 'gemini-key', order: 2 }
      ]
    });
    global.fetch.mockRejectedValue(new Error('fail'));

    const result = await fetchGPTJudgment('snippet');

    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(result).toEqual({ judgment: null, error: 'All providers failed' });
  });
});
