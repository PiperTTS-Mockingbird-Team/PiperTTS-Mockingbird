import * as core from '../src/utils/primer-core.js';

beforeEach(() => { document.body.innerHTML = ''; });

describe('waitForComposer', () => {
  test('finds textarea[placeholder] via mutation', async () => {
    setTimeout(() => {
      const ta = document.createElement('textarea');
      ta.setAttribute('placeholder','Message');
      document.body.appendChild(ta);
    }, 10);
    const el = await core.waitForComposer({ timeout: 100 });
    expect(el.tagName).toBe('TEXTAREA');
  });

  test('falls back to [data-testid="composer"]', async () => {
    setTimeout(() => {
      const div = document.createElement('div');
      div.setAttribute('data-testid','composer');
      document.body.appendChild(div);
    }, 10);
    const el = await core.waitForComposer({ timeout: 100 });
    expect(el.getAttribute('data-testid')).toBe('composer');
  });

  test('finds contenteditable inside container', async () => {
    setTimeout(() => {
      const main = document.createElement('main');
      const div = document.createElement('div');
      div.setAttribute('contenteditable','true');
      main.appendChild(div);
      document.body.appendChild(main);
    }, 10);
    const el = await core.waitForComposer({ timeout: 100 });
    expect(el.getAttribute('contenteditable')).toBe('true');
  });
});

describe('typeAndSend', () => {
  test('ignores placeholder text', async () => {
    const el = document.createElement('div');
    el.setAttribute('contenteditable','true');
    el.setAttribute('data-placeholder','Say something');
    el.textContent = 'Say something';
    document.body.appendChild(el);
    global.chrome = { storage: { local: { remove: jest.fn() } } };
    await core.typeAndSend(el, 'hello');
    expect(el.textContent).toBe('hello');
    delete global.chrome;
  });
});
