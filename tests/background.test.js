import fs from 'fs';
import path from 'path';

describe('clearAllDNRules', () => {
  let clearAllDNRules;
  let snapshot;
  let updateDynamicRules;
  let log;

  beforeEach(() => {
    // Extract clearAllDNRules from source file
    const src = fs.readFileSync(path.resolve(__dirname, '../src/background/background.js'), 'utf8');
    const start = src.indexOf('function clearAllDNRules');
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

    snapshot = jest.fn().mockResolvedValue({ ruleIds: [10000, 10001] });
    updateDynamicRules = jest.fn();
    globalThis.chrome = {
      declarativeNetRequest: { RuleIds: { snapshot }, updateDynamicRules }
    };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('removes only rule IDs from snapshot', async () => {
    await clearAllDNRules();
    expect(snapshot).toHaveBeenCalled();
    expect(updateDynamicRules).toHaveBeenCalledWith(
      { removeRuleIds: [10000, 10001], addRules: [] },
      expect.any(Function)
    );
  });

  test('does nothing when snapshot returns empty', async () => {
    snapshot.mockResolvedValue({ ruleIds: [] });
    await clearAllDNRules();
    expect(updateDynamicRules).not.toHaveBeenCalled();
  });
});
