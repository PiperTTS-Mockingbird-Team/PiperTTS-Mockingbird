const LOCK_KEY = 'ruleIds_lock';
const IDS_KEY = 'activeRuleIds';
const START_ID = 10_000;

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export class RuleIds {
  static async withLock(fn, retries = 5, delay = 10) {
    for (let attempt = 0; attempt < retries; attempt++) {
      const { [LOCK_KEY]: locked } = await chrome.storage.local.get(LOCK_KEY);
      if (!locked) {
        await chrome.storage.local.set({ [LOCK_KEY]: true });
        try {
          return await fn();
        } finally {
          await chrome.storage.local.remove(LOCK_KEY);
        }
      }
      await sleep(delay);
      delay = Math.min(delay * 2, 1000);
    }
    throw new Error('Failed to acquire RuleIds lock');
  }

  static async getActive() {
    const { [IDS_KEY]: ids = [] } = await chrome.storage.local.get(IDS_KEY);
    return ids;
  }

  static async allocate(count = 1) {
    return await this.withLock(async () => {
      const { [IDS_KEY]: active = [] } = await chrome.storage.local.get(IDS_KEY);
      let next = START_ID;
      if (active.length) next = Math.max(...active) + 1;
      const ids = [];
      for (let i = 0; i < count; i++) ids.push(next + i);
      await chrome.storage.local.set({ [IDS_KEY]: active.concat(ids) });
      return ids;
    });
  }

  static async release(ids) {
    await this.withLock(async () => {
      const { [IDS_KEY]: active = [] } = await chrome.storage.local.get(IDS_KEY);
      const remaining = active.filter(id => !ids.includes(id));
      if (remaining.length) {
        await chrome.storage.local.set({ [IDS_KEY]: remaining });
      } else {
        await chrome.storage.local.remove(IDS_KEY);
      }
    });
  }

  static async update(ids) {
    await this.withLock(async () => {
      if (ids && ids.length) {
        await chrome.storage.local.set({ [IDS_KEY]: ids });
      } else {
        await chrome.storage.local.remove(IDS_KEY);
      }
    });
  }
}
