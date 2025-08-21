import { RuleIds, RULE_ID_RANGES } from '../src/background/rule-ids.js';
import { applyDynamicRules } from '../src/background/dynamic-rule-manager.js';

const store = {};

globalThis.chrome = {
  storage: {
    local: {
      async get(key) {
        if (Array.isArray(key)) {
          const res = {};
          for (const k of key) res[k] = store[k];
          return res;
        }
        if (typeof key === 'string') {
          return { [key]: store[key] };
        }
        return {};
      },
      async set(obj) {
        Object.assign(store, obj);
      },
      async remove(key) {
        if (Array.isArray(key)) {
          for (const k of key) delete store[k];
        } else {
          delete store[key];
        }
      }
    },
    onChanged: { addListener() {} }
  },
  declarativeNetRequest: {
    async updateDynamicRules() {}
  }
};

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

async function main() {
  const [wordId] = await RuleIds.allocate('wordBlocker', 1);
  await applyDynamicRules(['a.com', 'b.com']);
  const lockoutIds = await RuleIds.getActive('lockout');
  const wordIds = await RuleIds.getActive('wordBlocker');

  const [lockStart, lockEnd] = RULE_ID_RANGES.lockout;
  const [wordStart, wordEnd] = RULE_ID_RANGES.wordBlocker;

  assert(wordIds.length === 1, 'expected one wordBlocker rule id');
  assert(wordIds[0] >= wordStart && wordIds[0] <= wordEnd,
    `wordBlocker id ${wordIds[0]} out of range ${wordStart}-${wordEnd}`);
  assert(wordId === wordIds[0], 'allocated id mismatch');

  assert(lockoutIds.length === 2, 'expected two lockout rule ids');
  for (const id of lockoutIds) {
    assert(id >= lockStart && id <= lockEnd,
      `lockout id ${id} out of range ${lockStart}-${lockEnd}`);
  }

  console.log('smoke-dnr: success');
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});

