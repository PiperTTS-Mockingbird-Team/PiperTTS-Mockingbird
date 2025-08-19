import { createRuleIdAllocator } from '../src/background/blocker-ids.js';

describe('Rule ID allocator', () => {
  test('deterministic allocation', () => {
    const alloc = createRuleIdAllocator();
    expect(alloc.allocate('a.com')).toBe(10000);
    expect(alloc.allocate('a.com')).toBe(10000);
    expect(alloc.allocate('b.com')).toBe(10001);
  });

  test('reuse after release', () => {
    const alloc = createRuleIdAllocator();
    const idA = alloc.allocate('a.com');
    alloc.allocate('b.com');
    alloc.release('a.com');
    const idC = alloc.allocate('c.com');
    expect(idC).toBe(idA);
  });

  test('snapshot shape', () => {
    const alloc = createRuleIdAllocator();
    alloc.allocate('a.com');
    expect(alloc.snapshot()).toEqual({ next: 10001, index: { 'a.com': 10000 } });
  });
});
