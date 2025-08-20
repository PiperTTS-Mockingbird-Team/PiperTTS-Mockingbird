const LOCK_KEY = 'ruleIds_lock';

export const RULE_ID_RANGES = {
  lockout: [10_000, 19_999],
  wordBlocker: [20_000, 29_999],
  debug: [30_000, 39_999]
};

export const START_ID = RULE_ID_RANGES.lockout[0];

export function featureForId(id) {
  for (const [feature, [start, end]] of Object.entries(RULE_ID_RANGES)) {
    if (id >= start && id <= end) return feature;
  }
  return null;
}

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

  static async getActive(feature) {
    const key = `activeRuleIds:${feature}`;
    const { [key]: ids = [] } = await chrome.storage.local.get(key);
    return ids;
  }
  static async allocate(feature, count = 1) {
    return this.withLock(async () => {
      const activeKey = `activeRuleIds:${feature}`;
      const freeKey = `freeRuleIds:${feature}`;
      const { [activeKey]: active = [], [freeKey]: free = [] } =
        await chrome.storage.local.get([activeKey, freeKey]);
      const [start, end] = RULE_ID_RANGES[feature] || RULE_ID_RANGES.lockout;
      const ids = [];
      while (free.length && ids.length < count) ids.push(free.pop());
      const used = new Set([...active, ...ids]);
      for (let id = start; id <= end && ids.length < count; id++) {
        if (!used.has(id)) ids.push(id);
      }
      if (ids.length < count) {
        throw new Error(`Insufficient rule IDs in ${feature} range`);
      }
      const updatedActive = [...active, ...ids].sort((a, b) => a - b);
      await chrome.storage.local.set({
        [activeKey]: updatedActive,
        [freeKey]: free
      });
      return ids;
    });
  }
  static async _releaseNoLock(feature, ids) {
    const activeKey = `activeRuleIds:${feature}`;
    const freeKey = `freeRuleIds:${feature}`;
    const { [activeKey]: active = [], [freeKey]: free = [] } =
      await chrome.storage.local.get([activeKey, freeKey]);
    const remaining = active.filter(id => !ids.includes(id));
    const updatedFree = [...free, ...ids];
    const toSet = { [freeKey]: updatedFree };
    if (remaining.length) {
      toSet[activeKey] = remaining;
      await chrome.storage.local.set(toSet);
    } else {
      await chrome.storage.local.set(toSet);
      await chrome.storage.local.remove(activeKey);
    }
  }

  static async release(feature, ids) {
    await this.withLock(async () => {
      await this._releaseNoLock(feature, ids);
    });
  }

  static async setActive(feature, ids) {
    await this.withLock(async () => {
      const activeKey = `activeRuleIds:${feature}`;
      const freeKey = `freeRuleIds:${feature}`;
      const { [freeKey]: free = [] } = await chrome.storage.local.get(freeKey);
      const filteredFree = free.filter(id => !ids.includes(id));
      const toSet = { [freeKey]: filteredFree };
      if (ids && ids.length) {
        const unique = Array.from(new Set(ids)).sort((a, b) => a - b);
        toSet[activeKey] = unique;
        await chrome.storage.local.set(toSet);
      } else {
        await chrome.storage.local.set(toSet);
        await chrome.storage.local.remove(activeKey);
      }
    });
  }
  static async updateDynamicRules(options) {
    await this.withLock(async () => {
      await chrome.declarativeNetRequest.updateDynamicRules(options);
      const { removeRuleIds = [], addRules = [] } = options;
      if (removeRuleIds.length) {
        const added = new Set(addRules.map(r => r.id));
        const byFeature = {};
        for (const id of removeRuleIds) {
          if (added.has(id)) continue;
          const feature = featureForId(id);
          if (feature) {
            byFeature[feature] ??= [];
            byFeature[feature].push(id);
          }
        }
        for (const [feature, ids] of Object.entries(byFeature)) {
          await this._releaseNoLock(feature, ids);
        }
      }
    });
  }
}
