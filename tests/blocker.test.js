import { applyDynamicBlockRules, clearDynamicBlockRules } from '../src/background/blocker.js';

describe('applyDynamicBlockRules', () => {
  let updateDynamicRules;
  let storageSet;

  beforeEach(() => {
    updateDynamicRules = jest.fn().mockResolvedValue();
    storageSet = jest.fn().mockResolvedValue();
    globalThis.chrome = {
      declarativeNetRequest: { updateDynamicRules },
      storage: { local: { set: storageSet } }
    };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('constructs rule IDs starting at 10000 and saves them', async () => {
    await applyDynamicBlockRules(['a.com', 'b.com']);
    const ids = [10000, 10001];
    expect(updateDynamicRules).toHaveBeenCalledWith({
      removeRuleIds: ids,
      addRules: expect.arrayContaining([
        expect.objectContaining({ id: 10000 }),
        expect.objectContaining({ id: 10001 })
      ])
    });
    expect(storageSet).toHaveBeenCalledWith({ activeRuleIds: ids });
  });
});

describe('clearDynamicBlockRules', () => {
  let updateDynamicRules;
  let storageGet;
  let storageRemove;

  beforeEach(() => {
    updateDynamicRules = jest.fn().mockResolvedValue();
    storageGet = jest.fn().mockResolvedValue({ activeRuleIds: [10000, 10001] });
    storageRemove = jest.fn().mockResolvedValue();
    globalThis.chrome = {
      declarativeNetRequest: { updateDynamicRules },
      storage: { local: { get: storageGet, remove: storageRemove } }
    };
  });

  afterEach(() => {
    delete globalThis.chrome;
  });

  test('removes stored rule IDs', async () => {
    await clearDynamicBlockRules();
    expect(storageGet).toHaveBeenCalledWith('activeRuleIds');
    expect(updateDynamicRules).toHaveBeenCalledWith({ removeRuleIds: [10000, 10001] });
    expect(storageRemove).toHaveBeenCalledWith('activeRuleIds');
  });
});
