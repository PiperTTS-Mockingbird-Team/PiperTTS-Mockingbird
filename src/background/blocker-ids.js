export function createRuleIdAllocator(start = 10000) {
  let next = start;
  const free = [];
  const index = new Map(); // host -> id

  return {
    allocate(host) {
      if (index.has(host)) return index.get(host);
      const id = free.length ? free.shift() : next++;
      index.set(host, id);
      return id;
    },
    release(host) {
      if (!index.has(host)) return;
      const id = index.get(host);
      index.delete(host);
      free.push(id);
    },
    snapshot() {
      return { next, index: Object.fromEntries(index) };
    }
  };
}
