const RANGES = {
  'lockout':   { start: 10001, end: 19999 },
  'word-blocker': { start: 20001, end: 29999 },
  'debug':     { start: 90001, end: 90999 }
};

const STORAGE_KEY = 'ruleIds';
const MUTEX_KEY   = 'ruleIdsMutex';

let next = {};
let inUse = {};

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function withMutex(fn) {
  const token = Math.random().toString(36).slice(2);
  while (true) {
    const { [MUTEX_KEY]: owner } = await chrome.storage.local.get(MUTEX_KEY);
    if (!owner) {
      await chrome.storage.local.set({ [MUTEX_KEY]: token });
      const verify = await chrome.storage.local.get(MUTEX_KEY);
      if (verify[MUTEX_KEY] === token) break;
    }
    await sleep(5);
  }
  try {
    return await fn();
  } finally {
    const verify = await chrome.storage.local.get(MUTEX_KEY);
    if (verify[MUTEX_KEY] === token) {
      await chrome.storage.local.remove(MUTEX_KEY);
    }
  }
}

async function load() {
  const stored = (await chrome.storage.local.get(STORAGE_KEY))[STORAGE_KEY];
  if (stored) {
    next = stored.next || {};
    inUse = stored.inUse || {};
  } else {
    next = {
      'lockout': RANGES['lockout'].start,
      'word-blocker': RANGES['word-blocker'].start,
      'debug': RANGES['debug'].start
    };
    inUse = {};
  }
}

async function save() {
  await chrome.storage.local.set({
    [STORAGE_KEY]: { next, inUse }
  });
}

export async function init() {
  return withMutex(async () => {
    await load();
    await save();
  });
}

export async function allocate(tag) {
  return withMutex(async () => {
    await load();
    const range = RANGES[tag];
    if (!range) throw new Error(`unknown tag: ${tag}`);
    const id = next[tag];
    if (id > range.end) throw new Error(`${tag} ids exhausted`);
    next[tag] = id + 1;
    const dnrIndex = id - range.start + 1;
    inUse[id] = { tag, dnrIndex };
    await save();
    return { id, dnrIndex };
  });
}

export async function release(ids) {
  const list = Array.isArray(ids) ? ids : [ids];
  return withMutex(async () => {
    await load();
    for (const id of list) {
      delete inUse[id];
    }
    await save();
  });
}

export async function snapshot() {
  return withMutex(async () => {
    await load();
    return {
      next: { ...next },
      inUse: { ...inUse }
    };
  });
}
