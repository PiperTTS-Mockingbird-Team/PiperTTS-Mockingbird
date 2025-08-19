import '../src/options/api-error.js';

describe('api-error page', () => {
  let openOptionsPage;

  beforeEach(() => {
    document.body.innerHTML = `
      <p id="errorDetails"></p>
      <button id="openSettingsBtn"></button>
    `;

    openOptionsPage = jest.fn();

    global.chrome = {
      storage: {
        local: {
          get: jest.fn((key, cb) => cb({ lastApiError: 'Something went wrong' }))
        }
      },
      runtime: { openOptionsPage }
    };
  });

  afterEach(() => {
    delete global.chrome;
  });

  test('displays stored error details', () => {
    document.dispatchEvent(new Event('DOMContentLoaded'));
    expect(document.getElementById('errorDetails').textContent)
      .toBe('Something went wrong');
  });

  test('falls back when no error is stored', () => {
    chrome.storage.local.get.mockImplementation((key, cb) => cb({}));
    document.dispatchEvent(new Event('DOMContentLoaded'));
    expect(document.getElementById('errorDetails').textContent)
      .toBe('No additional error details available.');
  });

  test('opens settings when button clicked', () => {
    document.dispatchEvent(new Event('DOMContentLoaded'));
    document.getElementById('openSettingsBtn').click();
    expect(openOptionsPage).toHaveBeenCalled();
  });
});

