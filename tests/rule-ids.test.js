describe('rule-ids', () => {
  let storage;

  beforeEach(() => {
    storage = {};
    global.chrome = {
      storage: {
        local: {
          get: jest.fn(async (key) => {
            if (Array.isArray(key)) {
              const res = {};
              for (const k of key) res[k] = storage[k];
              return res;
            }
            if (typeof key === 'object') {
              const res = {};
              for (const k in key) res[k] = storage[k] ?? key[k];
              return res;
            }
            return { [key]: storage[key] };
          }),
          set: jest.fn(async (obj) => { Object.assign(storage, obj); }),
          remove: jest.fn(async (key) => {
            if (Array.isArray(key)) {
              for (const k of key) delete storage[k];
            } else {
              delete storage[key];
            }
          })
        }
      }
    };
  });

  afterEach(() => {
    delete global.chrome;
    jest.resetModules();
  });

  test('allocates within ranges and persists', async () => {
    const mod = await import('../src/background/rule-ids.js');
    await mod.init();
    const a = await mod.allocate('lockout');
    expect(a).toEqual({ id: 10001, dnrIndex: 1 });
    const b = await mod.allocate('word-blocker');
    expect(b).toEqual({ id: 20001, dnrIndex: 1 });
    let snap = await mod.snapshot();
    expect(snap.inUse[10001]).toEqual({ tag: 'lockout', dnrIndex: 1 });
    expect(snap.next.lockout).toBe(10002);
    // simulate module reload
    const saved = { ...storage };
    jest.resetModules();
    storage = saved;
    const mod2 = await import('../src/background/rule-ids.js');
    global.chrome.storage.local.get.mockImplementation(async (key) => {
      if (Array.isArray(key)) {
        const res = {};
        for (const k of key) res[k] = storage[k];
        return res;
      }
      if (typeof key === 'object') {
        const res = {};
        for (const k in key) res[k] = storage[k] ?? key[k];
        return res;
      }
      return { [key]: storage[key] };
    });
    await mod2.init();
    snap = await mod2.snapshot();
    expect(snap.next.lockout).toBe(10002);
    expect(snap.inUse[10001]).toEqual({ tag: 'lockout', dnrIndex: 1 });
  });

  test('release frees ids', async () => {
    const mod = await import('../src/background/rule-ids.js');
    await mod.init();
    const { id } = await mod.allocate('debug');
    let snap = await mod.snapshot();
    expect(snap.inUse[id]).toBeDefined();
    await mod.release(id);
    snap = await mod.snapshot();
    expect(snap.inUse[id]).toBeUndefined();
  });
});
