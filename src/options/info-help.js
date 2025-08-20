const HELP_MAP = {
  SCANNING: {
    title: "Scanning",
    html: `
        <p><strong>Scan character limit</strong> is the max text sent to GPT per check.</p>
        <p><strong>Scan interval</strong> controls how often GRAPE checks your ChatGPT tab.</p>
        <p><em>Tip:</em> Lower intervals cost more; see Cost estimate below.</p>`
  },
  AI_PROVIDERS: {
    title: "AI Providers",
    html: `
        <p>Paste your API key(s). Use the ↑/↓ to set provider priority.</p>
        <p>Your keys are stored with chrome.storage.sync and never leave your device except to call the model you configure.</p>`
  },
  FOCUS_LOCKS: {
    title: "Focus & Lockouts",
    html: `
        <p><strong>Always On</strong>: scans continuously.</p>
        <p><strong>Timer</strong>: one-shot focus period.</p>
        <p><strong>Relax → Focus</strong>: cycles relax then mini-focus. Optional locks require a password.</p>`
  },
  BLOCKED_SITES: { title: "Blocked Sites", html: `<p>One domain per line (e.g., <code>youtube.com</code>).</p>` },
  COST: { title: "Cost estimate", html: `<p>Projected weekly/monthly costs based on your interval, limit, and hours/day.</p>` },
  BLOCKED_WORDS: {
    title: "Blocked Words",
    html: `
        <p>Enter words or phrases that should trigger a willpower deduction and skip GPT processing.</p>
        <p>Provide one entry per line.</p>`
  },
  NOTES: {
    title: "Notes",
    html: `<p>Keep personal notes or reminders related to your goals. Stored locally with your settings.</p>`
  },
  REDIRECT_PRIMING: {
    title: "Redirect Priming",
    html: `
        <p>Automatically paste a template message into ChatGPT after redirecting.</p>
        <p>Use <code>{goal}</code> in the template to insert your current goal.</p>`
  },
  LOCKOUT_MSG: {
    title: "Lockout page message",
    html: `<p>Optional message shown on the lockout page beneath your goal.</p>`
  },
  ACCOUNTABILITY: {
    title: "Accountability Intervention",
    html: `
        <p>Escalates lock duration when repeated blocks occur within a window.</p>
        <p>Configure thresholds and multiplier to fit your needs.</p>`
  },
  DEBUGGING: {
    title: "Debugging",
    html: `<p>Enable debug logging to troubleshoot issues. Logs appear in the extension's background console.</p>`
  }
};

function createPopover(btn, { title, html }) {
  const pop = document.createElement('div');
  pop.className = 'help-popover';
  pop.setAttribute('role', 'tooltip');
  pop.innerHTML = `
      <h5>${title}</h5>
      <div>${html}</div>
    `;

  document.body.append(pop);

  // position
  const r = btn.getBoundingClientRect();
  const pw = pop.offsetWidth || 360;
  let left = Math.min(window.innerWidth - pw - 12, r.right - pw) + window.scrollX;
  if (left < window.scrollX + 12) left = window.scrollX + 12;
  let top = r.bottom + 8 + window.scrollY;
  if (top + pop.offsetHeight > window.innerHeight - 12 + window.scrollY) {
    top = r.top - pop.offsetHeight - 8 + window.scrollY;
  }
  if (top < window.scrollY + 12) top = window.scrollY + 12;
  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;

  btn.setAttribute('aria-expanded', 'true');
  return pop;
}

function openHelp(btn) {
  const id = btn.closest('.card-title')?.dataset.helpId;
  if (!id || !HELP_MAP[id]) return;
  document.querySelectorAll('.help-popover').forEach(n => n.remove());
  if (btn._helpClose) btn.removeEventListener('mouseleave', btn._helpClose);
  const pop = createPopover(btn, HELP_MAP[id]);

  const maybeClose = e => {
    const related = e.relatedTarget;
    if (!btn.contains(related) && !pop.contains(related)) {
      pop.remove();
      btn.setAttribute('aria-expanded', 'false');
      btn.removeEventListener('mouseleave', maybeClose);
      pop.removeEventListener('mouseleave', maybeClose);
    }
  };

  btn._helpClose = maybeClose;
  btn.addEventListener('mouseleave', maybeClose);
  pop.addEventListener('mouseleave', maybeClose);
}

function attach() {
  document.querySelectorAll('.card-title .info-btn').forEach(btn => {
    btn.addEventListener('mouseenter', () => openHelp(btn));
    btn.addEventListener('focus', () => openHelp(btn));
    btn.addEventListener('blur', () => {
      document.querySelectorAll('.help-popover').forEach(n => n.remove());
      btn.setAttribute('aria-expanded', 'false');
    });
  });
}

document.addEventListener('DOMContentLoaded', attach);

