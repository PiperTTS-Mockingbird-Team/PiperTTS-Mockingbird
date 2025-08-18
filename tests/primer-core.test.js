const FakeInputEvent = class extends Event { constructor(type, params){ super(type, params); this.data = params?.data; this.inputType = params?.inputType; } };
if (typeof globalThis.InputEvent === "undefined") globalThis.InputEvent = FakeInputEvent;

import { getComposer, insertText, sendMessage } from '../src/utils/primer-core.js';

describe('getComposer', () => {
  test('finds contenteditable textarea', () => {
    document.body.innerHTML = '<div id="prompt-textarea" contenteditable="true"></div>';
    const el = getComposer();
    expect(el).not.toBeNull();
    expect(el.id).toBe('prompt-textarea');
  });
});

describe('insertText', () => {
  test('inserts into contenteditable', () => {
    document.body.innerHTML = '<div id="prompt-textarea" contenteditable="true"></div>';
    const el = document.getElementById('prompt-textarea');
    insertText(el, 'hello');
    expect(el.textContent).toBe('hello');
  });

  test('inserts into textarea', () => {
    document.body.innerHTML = '<textarea id="prompt-textarea"></textarea>';
    const el = document.getElementById('prompt-textarea');
    insertText(el, 'hello');
    expect(el.value).toBe('hello');
  });
});

describe('sendMessage', () => {
   test('clicks available send button', async () => {
    jest.useFakeTimers();
    document.body.innerHTML = `
      <form>
        <textarea id="prompt-textarea"></textarea>
        <button type="submit" id="sendBtn">Send</button>
      </form>
    `;
    const el = document.getElementById('prompt-textarea');
    const btn = document.getElementById('sendBtn');
    let clicked = false;
    btn.addEventListener('click', () => { clicked = true; });

    const promise = sendMessage(el);
    jest.advanceTimersByTime(200);
    await promise;
    jest.useRealTimers();
    expect(clicked).toBe(true);
  });
});
