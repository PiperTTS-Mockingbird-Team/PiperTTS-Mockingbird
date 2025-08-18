export function clamp(val, min = 0.1, max = 720) {
  const num = parseFloat(val);
  if (!Number.isFinite(num)) return min;
  return Math.min(max, Math.max(min, num));
}

export function formatTime(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const mins = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return `${mins}m ${secs}s`;
}
