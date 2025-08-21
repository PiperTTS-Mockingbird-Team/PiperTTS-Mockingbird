import { RuleIds } from '../src/background/rule-ids.js';
import { clearNow } from '../src/lockout/lockout.js';

describe('clearNow', () => {
  beforeEach(() => {
    window.toast = jest.fn();
    RuleIds.getActive = jest.fn().mockResolvedValue([1]);
    RuleIds.updateDynamicRules = jest
      .fn()
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce();
    RuleIds.setActive = jest.fn().mockResolvedValue();
  });

  afterEach(() => {
    delete window.toast;
  });

  test('retries updateDynamicRules before succeeding', async () => {
    await clearNow();
    expect(RuleIds.updateDynamicRules).toHaveBeenCalledTimes(2);
    expect(RuleIds.setActive).toHaveBeenCalledWith('lockout', []);
    expect(window.toast).toHaveBeenLastCalledWith('Cleared lockout rules.');
  }, 10000);
});

