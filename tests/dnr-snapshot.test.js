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
    delete globalThis.RuleIds;
    delete globalThis.RULE_ID_RANGES;
  });

  test('returns dynamic rules and active IDs within configured ranges', async () => {
    const dynamicRules = [{ id: 1 }];
    const getDynamicRules = jest.fn().mockResolvedValue(dynamicRules);
    const getActive = jest.fn((feature) => {
      const [min] = RULE_ID_RANGES[feature];
      return Promise.resolve([min]);
    });
    globalThis.chrome = { declarativeNetRequest: { getDynamicRules } };
    globalThis.RuleIds = { getActive };
    globalThis.RULE_ID_RANGES = {
      lockout: [10000,19999],
      wordBlocker: [20000,29999],
      debug: [30000,39999]
    };

    const response = await new Promise(resolve => {
      listener({ type: 'DNR_SNAPSHOT' }, {}, resolve);
    });

    expect(getDynamicRules).toHaveBeenCalled();
    expect(getActive).toHaveBeenCalledTimes(Object.keys(RULE_ID_RANGES).length);

    const features = Object.keys(RULE_ID_RANGES);
    expect(Object.keys(response.snapshot).sort()).toEqual(features.sort());
    features.forEach(f => {
      const [min, max] = RULE_ID_RANGES[f];
      response.snapshot[f].forEach(id => {
        expect(id).toBeGreaterThanOrEqual(min);
        expect(id).toBeLessThanOrEqual(max);
      });
    });
    expect(response.dynamicRules).toEqual(dynamicRules);
  });

  test('handles features with no active IDs', async () => {
    const getDynamicRules = jest.fn().mockResolvedValue([{ id: 1 }]);
    const getActive = jest.fn(() => Promise.resolve([]));
    globalThis.chrome = { declarativeNetRequest: { getDynamicRules } };
    globalThis.RuleIds = { getActive };
    globalThis.RULE_ID_RANGES = {
      lockout: [10000,19999],
      wordBlocker: [20000,29999],
      debug: [30000,39999]
    };

    const response = await new Promise(resolve => {
      listener({ type: 'DNR_SNAPSHOT' }, {}, resolve);
    });

    expect(getDynamicRules).toHaveBeenCalled();
    expect(getActive).toHaveBeenCalledTimes(Object.keys(RULE_ID_RANGES).length);

    const features = Object.keys(RULE_ID_RANGES);
    expect(Object.keys(response.snapshot).sort()).toEqual(features.sort());
    features.forEach(f => {
      expect(response.snapshot[f]).toEqual([]);
    });
  });
});
