import { clamp, formatTime } from '../src/utils.js';

describe('clamp', () => {
  test('clamps below min and above max', () => {
    expect(clamp(-5, 0, 10)).toBe(0);
    expect(clamp(15, 0, 10)).toBe(10);
  });

  test('parses strings and uses defaults', () => {
    expect(clamp('0')).toBe(0.1);
    expect(clamp('800')).toBe(720);
  });
});

describe('formatTime', () => {
  test('formats milliseconds into minutes and seconds', () => {
    expect(formatTime(65000)).toBe('1m 5s');
  });

  test('handles negative values as zero', () => {
    expect(formatTime(-5000)).toBe('0m 0s');
  });
});
