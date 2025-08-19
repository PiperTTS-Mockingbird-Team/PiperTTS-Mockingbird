import fs from 'fs';
import path from 'path';

describe('DNR_SNAPSHOT message', () => {
  let listener;
  let log, setBadge;

  beforeEach(() => {
    const src = fs.readFileSync(path.resolve(__dirname, '../src/background/background.js'), 'utf8');
    const idx = src.indexOf('chrome.runtime.onMessage.addListener');
    const start = src.indexOf('(', idx);
    let depth = 0;
    let end = start;
    for (; end < src.length; end++) {
      const ch = src[end];
      if (ch === '(') depth++;
      else if (ch === ')') {
        depth--;
        if (depth === 0) break;
      }
    }
    const fnStr = src.slice(start + 1, end);
    log = jest.fn();
    setBadge = jest.fn();
    listener = eval(fnStr);
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('returns dynamic rules and snapshot', async () => {
    const getDynamicRules = jest.fn().mockResolvedValue([{ id: 1 }]);
    const snapshot = jest.fn().mockResolvedValue({ ruleIds: [1] });
    globalThis.chrome = { declarativeNetRequest: { getDynamicRules, RuleIds: { snapshot } } };

    const response = await new Promise(resolve => {
      listener({ type: 'DNR_SNAPSHOT' }, {}, resolve);
    });

    expect(getDynamicRules).toHaveBeenCalled();
    expect(snapshot).toHaveBeenCalled();
    expect(response).toEqual({ dynamicRules: [{ id: 1 }], snapshot: { ruleIds: [1] } });
  });

  test('falls back when snapshot API is missing', async () => {
    const getDynamicRules = jest.fn().mockResolvedValue([{ id: 1 }]);
    globalThis.chrome = { declarativeNetRequest: { getDynamicRules } };

    const response = await new Promise(resolve => {
      listener({ type: 'DNR_SNAPSHOT' }, {}, resolve);
    });

    expect(getDynamicRules).toHaveBeenCalled();
    expect(response).toEqual({ dynamicRules: [{ id: 1 }], snapshot: { ruleIds: [1] } });
  });
});
