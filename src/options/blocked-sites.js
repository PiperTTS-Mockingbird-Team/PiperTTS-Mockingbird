export async function parseBlockedSites(text) {
  const lines = String(text || '')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);

  // Gather excluded hosts: extension itself, lockout page, and static rule domains
  const extensionHost = (() => {
    try {
      return new URL(chrome.runtime.getURL('*')).hostname;
    } catch {
      return '';
    }
  })();
  const lockoutHost = (() => {
    try {
      return new URL(chrome.runtime.getURL('pages/lockout.html')).hostname;
    } catch {
      return '';
    }
  })();

  const excluded = new Set([extensionHost, lockoutHost].filter(Boolean));

  try {
    const res = await fetch(chrome.runtime.getURL('rules.json'));
    const rules = await res.json();
    (rules || []).forEach((rule) => {
      const filter = rule?.condition?.urlFilter;
      if (typeof filter !== 'string') return;
      const match = filter.match(/^\|\|([^\^/]+)\^/);
      if (match) excluded.add(match[1]);
    });
  } catch {
    // ignore fetch errors
  }

  const hosts = [];
  for (const line of lines) {
    let url;
    try {
      url = new URL(line);
    } catch {
      try {
        url = new URL(`https://${line}`);
      } catch {
        continue;
      }
    }
    const host = url.hostname;
    if (!excluded.has(host)) {
      hosts.push(host);
    }
  }
  return [...new Set(hosts)];
}
