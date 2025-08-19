import fs from 'fs';
import path from 'path';

describe('clearAllDNRules', () => {
  let clearAllDNRules;
  let getActive;
  let updateDynamicRules;
  let log;

  beforeEach(() => {
    // Extract clearAllDNRules from source file
    const src = fs.readFileSync(path.resolve(__dirname, '../src/background/background.js'), 'utf8');
    const start = src.indexOf('async function clearAllDNRules');
    let brace = 0; let end = start;
    for (; end < src.length; end++) {
      const ch = src[end];
      if (ch === '{') brace++;
      else if (ch === '}') {
        brace--;
        if (brace === 0) { end++; break; }
      }
    }
    const fnStr = src.slice(start, end);
    log = jest.fn();
    clearAllDNRules = eval('(' + fnStr + ')');

    getActive = jest.fn().mockResolvedValue([10000, 10001]);
    updateDynamicRules = jest.fn().mockResolvedValue();
    globalThis.RuleIds = { getActive, updateDynamicRules };
  });

  afterEach(() => {
    delete globalThis.RuleIds;
  });

  test('removes active rule IDs', async () => {
    await clearAllDNRules();
    expect(getActive).toHaveBeenCalled();
    expect(updateDynamicRules).toHaveBeenCalledWith({ removeRuleIds: [10000, 10001] });
  });

  test('does nothing when no active IDs', async () => {
    getActive.mockResolvedValue([]);
    await clearAllDNRules();
    expect(updateDynamicRules).not.toHaveBeenCalled();
  });
});
