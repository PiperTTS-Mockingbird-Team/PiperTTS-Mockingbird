import { createRuleIdAllocator } from '../src/background/blocker-ids.js';
import { START_ID } from '../src/background/ruleIds.js';

describe('Rule ID allocator', () => {
  test('deterministic allocation', () => {
    const alloc = createRuleIdAllocator();
    expect(alloc.allocate('a.com')).toBe(START_ID);
    expect(alloc.allocate('a.com')).toBe(START_ID);
    expect(alloc.allocate('b.com')).toBe(START_ID + 1);
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
    expect(alloc.snapshot()).toEqual({ next: START_ID + 1, index: { 'a.com': START_ID } });
  });
});
