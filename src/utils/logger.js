let DEBUG = false;

function setDebug(val){
  DEBUG = !!val;
}

if (typeof process !== 'undefined' && process.env && process.env.DEBUG) {
  setDebug(process.env.DEBUG !== '0' && process.env.DEBUG !== 'false');
}

if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
  try {
    chrome.storage.local.get('debug').then(({debug}) => {
      if (typeof debug === 'boolean') setDebug(debug);
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

export function isDebug(){
  return DEBUG;
}

export function log(...args){
  if (DEBUG) console.log('[grape]', ...args);
}
