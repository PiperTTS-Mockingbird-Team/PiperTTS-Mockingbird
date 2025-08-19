# GRAPE | GPT-Regulated Autonomous Productivity Enforcer

A Chrome extension that gamifies and enforces on-topic use of ChatGPT (chat.openai.com or chatgpt.com), complete with willpower scoring, lockouts, and streak tracking—all powered by **your** own API keys.

---

## 📥 Installation

1. **Clone** or **download** this repo.
2. In Chrome, navigate to `chrome://extensions`.
3. Enable **Developer mode** (top right).
4. Click **Load unpacked**, select this repo’s folder.

> **Tip**: After installation you’ll automatically see the full user guide (`guide.html`).\
> **Don’t forget** to **pin** the GRAPE icon to your toolbar—this extension is designed for one-click access and real-time badge updates!

---

## 🚀 Quick Start

1. Click the GRAPE badge; add your API key under **AI Providers**.
2. Choose your **Focus Mode** (Always On, Timer, Cycle).
3. Set your **Goal**, **Durations**, and **Willpower Threshold**.
4. Hit **Save**, then head over to chat.openai.com or chatgpt.com to start tracking!

*For full details on every button, setting, and troubleshooting tips, see **`guide.html`** (opens automatically on install).*

---

## ✨ Key Features

- 🎮 **Willpower Scoring**: +1 on-topic, –1 distractions; clamped between –5 and 10.
- 🔒 **Lockouts**: Automatic “time-out” when you dip below threshold or hit banned words.
- ⏱ **Three Focus Modes**:
  - **Always On**: Continuous monitoring.
  - **Timer**: Fixed-length session (D minutes).
  - **Cycle**: Relax (G min) → Focus (H min) → then Always On.
- 🔥 **Streaks**: Day 0 ❄️, Days 1–6 🍇, Days 7+ 🔥 (tracked across reinstalls).
- 🔑 **Extreme Lock**: Password-protect settings so you can’t disable mid-session.
- 💾 **Local-First**: All data (scores, blocklists, settings) stays in your browser.
- 💰 **Cost Estimate**: Calculates API spend (e.g. “\$1/9 days”) and skips idle scans.
- 🌐 **Multiple AI Providers**: Use OpenAI, Gemini, or others with per-provider API keys.
- ✍️ **Redirect Priming & Custom Messages**: Auto-insert goal reminders and personalize the lockout page.
- 📊 **Accountability Intervention**: Longer locks if you trigger too many blocks in a short window.

---

## ⚙️ Settings Overview

- **Goal Input**: Your focus topic.
- **Mode Selector**: Always On / Timer / Cycle.
- **Durations**: D = focus minutes; G = relax minutes; H = focus minutes in cycle.
- **Threshold & Block Duration**: When and how long lockouts occur.
- **Blocked Sites & Words**: URLs/terms that instantly deduct willpower.
- **Scan Config**: Character limit (100–4000) & interval (0.1–60 min).
- **API Keys**: Add keys for providers like OpenAI or Gemini (only first/last chars shown).
- **User Notes**: Local memo field for reminders.
- **Redirect Priming**: Auto-paste a template message after redirect using your goal.
- **Lockout Message**: Optional text displayed on the lockout page.
- **Accountability Intervention**: Longer locks if you’re blocked repeatedly in a short time.

---

## 🛠️ Emergency & Troubleshooting

- **Emergency Unblock**: Button in the popup to clear dynamic rules.
- **Console Helper**: If unblock fails, open DevTools and run:
  ```js
  function clearNow() {
    const snap = chrome.declarativeNetRequest.RuleIds?.snapshot
      ? chrome.declarativeNetRequest.RuleIds.snapshot()
      : chrome.declarativeNetRequest.getDynamicRules().then(rules => ({ ruleIds: rules.map(r => r.id) }));
    snap.then(({ ruleIds = [] }) => {
      if (!ruleIds.length) return console.log("ℹ️ No rules to clear.");
      chrome.declarativeNetRequest.updateDynamicRules(
        { removeRuleIds: ruleIds, addRules: [] },
        () => console.log("✅ Cleared:", ruleIds)
      );
    });
  }
  clearNow();
  ```
- **Locked while on-topic?** Tweak scan length or threshold.
- **API issues?** Check your key and reload the ChatGPT tab (chat.openai.com or chatgpt.com).

---

## 📄 License & Contributing

MIT © Robert Remedios\
Contributions welcome! Please open an issue or pull request.

---

## 🧑‍💻 Developer Notes

Developers working with the Chrome declarativeNetRequest API can reference
the [DNR rule ID guide](docs/dnr-ids.md) for information on ID ranges,
allocator usage, migration steps, and common pitfalls.

---

> Built with 💜 and AI assistance (ChatGPT).

