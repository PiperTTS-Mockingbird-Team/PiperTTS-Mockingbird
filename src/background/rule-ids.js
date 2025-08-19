const LOCK_KEY = 'ruleIds_lock';
const IDS_KEY = 'activeRuleIds';

export const RANGES = {
  lockout: { start: 10_000, end: 19_999 },
  wordBlocker: { start: 20_000, end: 29_999 },
  debug: { start: 30_000, end: 39_999 }
};

export const START_ID = RANGES.lockout.start;

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

  static async allocate(count = 1, range = 'lockout') {
    return await this.withLock(async () => {
      const { [IDS_KEY]: active = [] } = await chrome.storage.local.get(IDS_KEY);
      const { start, end } = RANGES[range] || RANGES.lockout;
      const used = new Set(active.filter(id => id >= start && id <= end));
      const ids = [];
      for (let id = start; id <= end && ids.length < count; id++) {
        if (!used.has(id)) ids.push(id);
      }
      if (ids.length < count) {
        throw new Error(`Insufficient rule IDs in ${range} range`);
      }
      const updated = [...active, ...ids].sort((a, b) => a - b);
      await chrome.storage.local.set({ [IDS_KEY]: updated });
      return ids;
    });
  }

  static async release(ids) {
    await this.withLock(async () => {
      const { [IDS_KEY]: active = [] } = await chrome.storage.local.get(IDS_KEY);
      const remaining = active.filter(id => !ids.includes(id)).sort((a, b) => a - b);
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
        const unique = Array.from(new Set(ids)).sort((a, b) => a - b);
        await chrome.storage.local.set({ [IDS_KEY]: unique });
      } else {
        await chrome.storage.local.remove(IDS_KEY);
      }
    });
  }

  static async reconcile() {
    const rules = await chrome.declarativeNetRequest.getDynamicRules();
    const ids = rules.map(r => r.id).filter(id => id >= START_ID);
    await this.update(ids);
  }

  static async updateDynamicRules(options) {
    await chrome.declarativeNetRequest.updateDynamicRules(options);
    const { removeRuleIds = [], addRules = [] } = options;
    if (removeRuleIds.length) {
      const added = new Set(addRules.map(r => r.id));
      const toRelease = removeRuleIds.filter(id => !added.has(id));
      if (toRelease.length) {
        await this.release(toRelease);
      }
    }
  }
}
