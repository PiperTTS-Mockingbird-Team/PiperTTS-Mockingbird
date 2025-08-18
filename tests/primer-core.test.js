const FakeInputEvent = class extends Event { constructor(type, params){ super(type, params); this.data = params?.data; this.inputType = params?.inputType; } };
if (typeof globalThis.InputEvent === "undefined") globalThis.InputEvent = FakeInputEvent;

import * as core from '../src/utils/primer-core.js';

describe('getComposer', () => {
  test('finds contenteditable textarea', () => {
    document.body.innerHTML = '<div id="prompt-textarea" contenteditable="true"></div>';
    const el = core.getComposer();
    expect(el).not.toBeNull();
    expect(el.id).toBe('prompt-textarea');
  });
});

describe('insertText', () => {
  test('inserts into contenteditable', () => {
    document.body.innerHTML = '<div id="prompt-textarea" contenteditable="true"></div>';
    const el = document.getElementById('prompt-textarea');
    core.insertText(el, 'hello');
    expect(el.textContent).toBe('hello');
  });

  test('inserts into textarea', () => {
    document.body.innerHTML = '<textarea id="prompt-textarea"></textarea>';
    const el = document.getElementById('prompt-textarea');
    core.insertText(el, 'hello');
    expect(el.value).toBe('hello');
  });
});

describe('sendMessage', () => {
   test('clicks available send button', async () => {
    jest.useFakeTimers();
    document.body.innerHTML = `
        <textarea id="prompt-textarea"></textarea>
        <button id="sendBtn" data-testid="send-button">Send</button>
    `;
    const el = document.getElementById('prompt-textarea');
    const btn = document.getElementById('sendBtn');
    let clicked = false;
    btn.addEventListener('click', () => { clicked = true; });

    const promise = core.sendMessage(el);
    jest.advanceTimersByTime(200);
    await promise;
    jest.useRealTimers();
    expect(clicked).toBe(true);
  });
});

describe('typeAndSend', () => {
  test('skips insertion if user typed a different message', async () => {
    const el = document.createElement('textarea');
    el.value = 'user text';
    document.body.appendChild(el);

    const insertSpy = jest.spyOn(core, 'insertText');
    const sendSpy = jest.spyOn(core, 'sendMessage').mockResolvedValue(true);
    global.chrome = { storage: { local: { remove: jest.fn(async () => {}) } } };

    const result = await core.typeAndSend(el, 'primed', 'primed');

    expect(result).toBe(true);
    expect(insertSpy).not.toHaveBeenCalled();
    expect(sendSpy).not.toHaveBeenCalled();
    expect(global.chrome.storage.local.remove).toHaveBeenCalledWith(['primedMessage','redirectPriming','primeExpiresAt']);
  });
});
