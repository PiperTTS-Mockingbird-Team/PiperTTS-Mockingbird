let DEBUG = {};

function setDebug(val) {
  if (typeof val === 'boolean') {
    DEBUG = { all: !!val };
    console.log(`[grape] debug ${val ? 'enabled' : 'disabled'}`);
  } else if (val && typeof val === 'object') {
    DEBUG = { ...val };
  } else {
    DEBUG = {};
  }
}

if (typeof process !== 'undefined' && process.env && process.env.DEBUG) {
  setDebug(process.env.DEBUG !== '0' && process.env.DEBUG !== 'false');
}

if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
  try {
    chrome.storage.local.get('debug').then(({ debug }) => {
      if (typeof debug !== 'undefined') setDebug(debug);
    });
  } catch (e) {
    // ignore
  }
  try {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area === 'local' && Object.prototype.hasOwnProperty.call(changes, 'debug')) {
        setDebug(changes.debug.newValue);
      }
    });
  } catch (e) {
    // ignore
  }
}

export function isDebug(category) {
  if (category) return !!(DEBUG[category] || DEBUG.all);
  return Object.values(DEBUG).some(Boolean);
}

export function logger(category = 'general') {
  return (...args) => {
    if (DEBUG[category] || DEBUG.all) console.log('[grape]', ...args);
  };
}
