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
  const backdrop = document.createElement('div');
  backdrop.className = 'help-backdrop';

  const pop = document.createElement('div');
  pop.className = 'help-popover';
  pop.setAttribute('role', 'dialog');
  pop.setAttribute('aria-modal', 'true');
  pop.innerHTML = `
      <button class="close" aria-label="Close">✖</button>
      <h5>${title}</h5>
      <div>${html}</div>
    `;

  document.body.append(backdrop, pop);

  // position
  const r = btn.getBoundingClientRect();
  const pw = pop.offsetWidth || 360;
  let left = Math.min(window.innerWidth - pw - 12, r.right - pw);
  if (left < 12) left = 12;
  let top = r.bottom + 8;
  if (top + pop.offsetHeight > window.innerHeight - 12) {
    top = r.top - pop.offsetHeight - 8;
  }
  if (top < 12) top = 12;
  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;

  const close = pop.querySelector('.close');

  const closeAll = () => {
    pop.remove();
    backdrop.remove();
    btn.setAttribute('aria-expanded', 'false');
    btn.focus();
  };

  backdrop.addEventListener('click', closeAll);
  close.addEventListener('click', closeAll);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeAll(); }, { once: true });

  // focus trap
  const focusable = pop.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  pop.addEventListener('keydown', e => {
    if (e.key === 'Tab') {
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  });

  btn.setAttribute('aria-expanded', 'true');
  close.focus();
}

function openHelp(btn) {
  const id = btn.closest('.card-title')?.dataset.helpId;
  if (!id || !HELP_MAP[id]) return;
  document.querySelectorAll('.help-popover, .help-backdrop').forEach(n => n.remove());
  createPopover(btn, HELP_MAP[id]);
}

function attach() {
  document.querySelectorAll('.card-title .info-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      openHelp(btn);
    });
    btn.addEventListener('mouseenter', () => openHelp(btn));
    btn.addEventListener('focus', () => openHelp(btn));
  });
  document.addEventListener('click', () => {
    document.querySelectorAll('.help-popover, .help-backdrop').forEach(n => n.remove());
    document.querySelectorAll('.card-title .info-btn[aria-expanded="true"]').forEach(b => b.setAttribute('aria-expanded', 'false'));
  });
}

document.addEventListener('DOMContentLoaded', attach);

