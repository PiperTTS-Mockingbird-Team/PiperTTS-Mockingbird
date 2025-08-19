import fs from 'fs';
import path from 'path';

describe('static rules.json', () => {
  afterEach(() => {
    delete globalThis.chrome;
  });

  test('each rule has a urlFilter and passes validation', () => {
    const rulesPath = path.resolve(__dirname, '../rules.json');
    const rules = JSON.parse(fs.readFileSync(rulesPath, 'utf8'));

    globalThis.chrome = {
      declarativeNetRequest: {
        validateRules: ({ rules }) => {
          const ids = new Set();
          const ruleErrors = [];
          rules.forEach((rule, index) => {
            if (ids.has(rule.id)) ruleErrors.push({ index, error: 'Duplicate ID' });
            ids.add(rule.id);
            if (!rule.condition || !rule.condition.urlFilter) {
              ruleErrors.push({ index, error: 'Missing urlFilter' });
            }
          });
          return { ruleErrors };
        }
      }
    };

    const result = chrome.declarativeNetRequest.validateRules({ rules });
    expect(result.ruleErrors).toHaveLength(0);
    rules.forEach(rule => {
      expect(rule.condition.urlFilter).toBeDefined();
    });
  });
});

