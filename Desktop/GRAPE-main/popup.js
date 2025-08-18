import { clamp, formatTime } from './src/utils.js';

document.addEventListener("DOMContentLoaded", async () => {
  // 🔒 Check and apply extreme lock ASAP
  const { extremeLocked = false } = await chrome.storage.local.get("extremeLocked");
  if (extremeLocked) {
    lockPopupUIExtreme(true);
  }

  const input = document.getElementById("goal");
  const status = document.getElementById("status");
  const saveFocusButton = document.getElementById("saveFocusButton");
  const allNumberInputs = Array.from(document.querySelectorAll('input[type="number"]'));
  const lockContainers = document.querySelectorAll('.lock-container');


  let focusTimerInterval;
  let statusInterval;
  let currentFocusMode = null;
  let showFocusActive = false;
  let pendingFocusMode = null;

  function lockUI() {
    if (currentFocusMode === "off") return;

    let blocker = document.getElementById("uiBlocker");
    if (!blocker) {
      blocker = document.createElement("div");
      blocker.id = "uiBlocker";
      blocker.style.position = "absolute";
      blocker.style.top = 0;
      blocker.style.left = 0;
      blocker.style.width = "100%";

      // ✅ Shrink height to allow room for emergency controls
      blocker.style.height = "calc(100% - 90px)";

      blocker.style.zIndex = 999;
      blocker.style.background = "rgba(255,255,255,0.4)";
      blocker.style.pointerEvents = "auto";

      document.body.appendChild(blocker);
    }
  }



  // Removes the translucent overlay added by lockUI()
  function unlockUI() {
    const blocker = document.getElementById("uiBlocker");
    if (blocker) blocker.remove();
  }

  /*
  * Sets a live-updating interval to:
  *   Handle UI locking/unlocking focus time
  *   Show motivational stats like "Willpower points"
  *   Optionally inlcude focus phase countdowns (via focusDisplay())
  */
  function updateStatusLive(manualUILockUntil, autoLockUntil, score, focusDisplay = "") {
    const countdownEl = document.getElementById("lockCountdown");
    if (statusInterval) clearInterval(statusInterval);

    statusInterval = setInterval(() => {
      const now = Date.now();
      const lockRemaining = manualUILockUntil - now;
      const autoRemaining = autoLockUntil - now;

      let statusLines = [];

      if (currentFocusMode === "off") {
        unlockUI();
        statusLines.push("Focus mode is off.");
        statusLines.push(`Willpower: ${Math.max(-5, score ?? 5)} points`);
        status.textContent = statusLines.join("\n");
        return;
      }

      if (autoRemaining > 0) {
        statusLines.push(`⛔ Blocked for ${formatTime(autoRemaining)}`);
      }

      if (lockRemaining > 0) {
        statusLines.push(`🔒 Locked for ${formatTime(lockRemaining)}`);
        if (countdownEl) countdownEl.textContent = `Remaining: ${formatTime(lockRemaining)}`;
      } else {
        if (countdownEl) countdownEl.textContent = "";
      }

      let isRelax = false;




 

      if (typeof focusDisplay === "function") {
        const result = focusDisplay();
        if (result?.display) statusLines.push(result.display);
        isRelax = result?.isRelax;
      }

      if (showFocusActive && !isRelax) {
        statusLines.push("🧠 Focus Mode: Always On");
      }

      // Only lock if not relaxing
      if (autoRemaining <= 0 && lockRemaining <= 0 && !isRelax) {
        unlockUI();
      } else if (!isRelax) {
        lockUI();
      }


      statusLines.push(`Willpower: ${Math.max(-5, score ?? 5)} points`);
      status.textContent = statusLines.join("\n");
    }, 1000);
  }

  /*
  * Manages timing for:
  *  timer: one-shot focus period
  *  cycle: alternating relax/focus periods
  *  Sets a timer and stores info in chrome.storage.local
  * 
  * Returns a closure function that displays the remaining time or focus/relax status for use in updateStatusLive.
  */
  function startFocusTimer(mode, startTime = Date.now()) {
    if (focusTimerInterval) clearInterval(focusTimerInterval);

    const relaxMin = clamp(document.getElementById("G").value);
    const focusMin = clamp(document.getElementById("H").value);
    const timerMin = clamp(document.getElementById("D").value);

    let phase = "focus";
    let endTime = startTime;

    if (mode === "timer") {
      endTime += timerMin * 60 * 1000;
    } else if (mode === "cycle") {
      endTime += relaxMin * 60 * 1000;
      phase = "relax";
    }

    chrome.storage.local.set({ focusPhaseStart: startTime, focusPhaseMode: mode });

    focusTimerInterval = setInterval(async () => {
      const now = Date.now();
      const remaining = endTime - now;
if (remaining <= 0) {
if (mode === "cycle" && phase === "relax") {
  // ☕ Relax just ended → switch to mini-focus phase
  phase = "focus";
  endTime = now + focusMin * 60 * 1000;
  
  // ✅ Tell background we're now in "cycleFocus"
  await chrome.storage.local.set({ focusMode: "cycleFocus" });

  return;
}


if (mode === "cycle" && phase === "focus") {
  // 💼 Focus just ended → transition to always-on
  clearInterval(focusTimerInterval);
  await chrome.storage.local.set({
    focusMode: "onAllDay",
    focusPhaseStart: null,
    focusPhaseMode: null
  });
  currentFocusMode = "onAllDay";
  showFocusActive = true;
  return;
}


  // For timer mode only — safe to update state here
  clearInterval(focusTimerInterval);
  chrome.storage.local.remove(["focusPhaseStart", "focusPhaseMode"]);
  await chrome.storage.local.set({
    focusMode: "off",
    manualUILockUntil: 0,
    lockoutUntil: 0
  });
  currentFocusMode = "off";
  pendingFocusMode = "off";
  showFocusActive = false;
  unlockUI();
  status.textContent = "🚫 Focus mode is off.";
}



    }, 1000);

    return () => {
      const now = Date.now();
      const remaining = Math.max(0, endTime - now);
      if (remaining <= 0) return { display: "", isRelax: false };

      if (mode === "timer") {
        return { display: `🕒 Focus Mode: Timer — ends in ${formatTime(remaining)}`, isRelax: false };
      }
    
      if (phase === "relax") {
        return { display: `☕ Relax Mode — ends in ${formatTime(remaining)}`, isRelax: true };
      }
    
      return { display: `💼 Focus ends in ${formatTime(remaining)}`, isRelax: false };
    };

  }

  /*
  * Runs on DOM load:
  *  Loads saved settings from storage
  *  Starts any active timers
  *  Restores the correct focus mode
  *  Locks/unlocks UI as needed
  */

// ✅ Ensure a password exists before enabling a lock.
// Returns true if a password is already set OR was just set by the user.
// Returns false if user canceled.
async function ensurePasswordForLock() {
  const { extremePassword = null } = await chrome.storage.local.get("extremePassword");
  if (extremePassword) return true; // already set → no prompt

  // First-time setup: ask user to set one
  const pw = await openPasswordModal("lock");
  if (!pw) return false; // canceled
  await chrome.storage.local.set({ extremePassword: pw });
  return true;
}

// 🔐 EXTREME LOCK FEATURE
function lockPopupUIExtreme(lock) {
  const all = document.querySelectorAll("input, select, button, textarea");
  all.forEach(el => {
    if (
      el.id === "extremeLockButton" ||
      el.closest("#passwordModal") // ✅ Don't lock modal inputs/buttons
    ) return;
    el.disabled = lock;
  });
  document.body.style.opacity = lock ? "0.5" : "1";
}


const modal = document.getElementById("passwordModal");
const pwInput = document.getElementById("pwInput");
const pwInputConfirm = document.getElementById("pwInputConfirm");
const pwTitle = document.getElementById("pwModalTitle");
const pwSubmit = document.getElementById("pwSubmit");
const pwCancel = document.getElementById("pwCancel");

let pwMode = "lock"; // "lock" or "unlock"
let resolvePw;
let isConfirmingDelete = false;

function openPasswordModal(mode) {
  pwMode = mode;
  pwInput.value = "";
  pwInputConfirm.value = "";
  pwInputConfirm.style.display = mode === "lock" ? "block" : "none";
  pwTitle.textContent = mode === "lock" ? "🔐 Set Password" : "🔓 Enter Password";
  document.getElementById("pwInitialButtons").style.display = "block";
  document.getElementById("pwPostUnlockButtons").style.display = "none";
  pwInput.disabled = false;
  pwSubmit.style.display = "inline-block";
  pwCancel.style.display = "inline-block";
  modal.style.display = "flex";
  return new Promise(res => (resolvePw = res));
}

function closePasswordModal() {
  modal.style.display = "none";
  resolvePw(null);
}

pwSubmit.addEventListener("click", async () => {
  const pw = pwInput.value;

  if (pwMode === "lock") {
    const confirmPw = pwInputConfirm.value;
    if (pw !== confirmPw) return alert("Passwords do not match.");
    modal.style.display = "none";
    resolvePw(pw);
  } else {
    // Unlock flow
    const { extremePassword } = await chrome.storage.local.get("extremePassword");

    if (pw === extremePassword) {
      if (isConfirmingDelete) {
        // ✅ Delete confirmed password
        await chrome.storage.local.remove(["extremeLocked", "extremePassword"]);
        lockPopupUIExtreme(false);
        modal.style.display = "none";
        isConfirmingDelete = false;
        return;
      }

      // ✅ Just unlocking normally
      pwInput.disabled = true;
      pwSubmit.style.display = "none";
      pwCancel.style.display = "none";
      document.getElementById("pwInitialButtons").style.display = "none";
      document.getElementById("pwPostUnlockButtons").style.display = "block";
    } else if (pw) {
      alert("Incorrect password.");
    }
  }
});



pwCancel.addEventListener("click", () => {
  closePasswordModal();
});



document.getElementById("extremeLockButton").addEventListener("click", async () => {
  // If no password exists, set one and lock immediately.
  const { extremePassword = null, extremeLocked = false } = await chrome.storage.local.get(["extremePassword","extremeLocked"]);

  if (!extremePassword) {
    const pw = await openPasswordModal("lock");
    if (!pw) return;
    await chrome.storage.local.set({ extremePassword: pw, extremeLocked: true });
    lockPopupUIExtreme(true);
    return;
  }

  // Password exists:
  if (!extremeLocked) {
    // ✅ Quick-enable permanent UI lock with NO prompt
    await chrome.storage.local.set({ extremeLocked: true });
    lockPopupUIExtreme(true);
    return;
  }

  // 🔒 Already locked → show unlock/manage modal
  const pw = await openPasswordModal("unlock");
  if (pw === null) return;
  const { extremePassword: stored } = await chrome.storage.local.get("extremePassword");
  if (pw !== stored) {
    alert("Incorrect password.");
    return;
  }
  // On success the modal reveals post-unlock buttons
});



document.getElementById("pwContinue").addEventListener("click", async () => {
  lockPopupUIExtreme(false);                // Temporarily unlock the popup UI
  modal.style.display = "none";             // Hide the modal
  resolvePw(pwInput.value);                 // Resolve the password prompt
});



document.getElementById("pwDelete").addEventListener("click", async () => {
  const { extremePassword = null } = await chrome.storage.local.get("extremePassword");
  if (!extremePassword) {
    return alert("No password is set.");
  }

  // Flag that the user is about to confirm deletion
  isConfirmingDelete = true;

  // Show the unlock modal again
  openPasswordModal("unlock");
});



// 👇 Add this below the existing pwContinue and pwDelete handlers
document.getElementById("pwResetLock").addEventListener("click", async () => {
  await chrome.storage.local.set({
    lockoutUntil: 0,
    manualUILockUntil: 0,
    extremeLocked: false
  });

  lockPopupUIExtreme(false);
  modal.style.display = "none";
  resolvePw(pwInput.value);
});

// 👇 NEW: Toggle the permanent/password UI-lock
document.getElementById("pwTogglePermanent").addEventListener("click", async () => {
  const { extremeLocked = false } = await chrome.storage.local.get("extremeLocked");
  await chrome.storage.local.set({ extremeLocked: !extremeLocked });
  lockPopupUIExtreme(!extremeLocked);
  modal.style.display = "none";
  resolvePw(pwInput.value);
});


// 👇 NEW: Cancel the password prompt
document.getElementById("pwCancelPost").addEventListener("click", () => {
  // Hide the modal
  modal.style.display = "none";
  // Resolve the openPasswordModal() promise with `null`
  // so your code knows the user cancelled.
  resolvePw(null);
});


  async function initializePopup() {
    const storage = await chrome.storage.local.get([
      "goal", "manualUILockUntil", "autoLockUntil", "score",
      "focusMode", "lockOnAllDay", "lockTimer", "lockCycle",
      "D", "G", "H", "J",
      "focusPhaseStart", "focusPhaseMode"
    ]);

    input.value = storage.goal || "MCAT";

    const now = Date.now();
    const lockUntil = storage.manualUILockUntil ?? 0;
    const autoUntil = storage.autoLockUntil ?? 0;
    const isAnyLocked = (lockUntil > now || autoUntil > now);

    if (isAnyLocked) {
      lockUI();
    } else {
      unlockUI();
    }

    allNumberInputs.forEach(num => {
      const storedVal = storage[num.id];
      if (storedVal !== undefined) num.value = clamp(storedVal);
    });

    let focus = storage.focusMode;
    if (!focus) {
      focus = "onAllDay"; // 👈 default to Always On
      await chrome.storage.local.set({ focusMode: "onAllDay" });
    }
    pendingFocusMode = focus;
    currentFocusMode = focus;

    const radio = document.querySelector(`input[name="focusMode"][value="${focus}"]`);
    if (radio) {
      radio.checked = true;
      updateLockVisibility(); // 👈 ensure correct section shows
    }
    showFocusActive = (focus === "onAllDay");


    if (focus === "off") {
      unlockUI();
      status.textContent = "🚫 Focus Off — No monitoring active.";
     
      // ── Show install date & streak even when off ──
        const { extensionInstallDate } = await chrome.storage.local.get("extensionInstallDate");
        const banner = document.getElementById("installBanner");
        const installDate = new Date(extensionInstallDate);
        const diffDays = Math.floor((Date.now() - installDate) / (1000 * 60 * 60 * 24));
        const emoji = diffDays === 0
          ? "🧊"
          : diffDays >= 7
            ? "🔥"
            : "🍇";
        banner.textContent = `📅 Installed on ${installDate.toLocaleDateString()} | Streak: ${diffDays} ${emoji}`;


      return;
    }

    let focusDisplay = "";
    if ((storage.focusPhaseMode === "timer" || storage.focusPhaseMode === "cycle") && storage.focusPhaseStart) {
      focusDisplay = startFocusTimer(storage.focusPhaseMode, storage.focusPhaseStart);
    }

    if (lockUntil > Date.now()) {
      input.disabled = true; // Lock goal
    } else {
      input.disabled = false; // unlock goal
    }

    updateStatusLive(lockUntil, autoUntil, storage.score ?? 5, focusDisplay);
    updateLockVisibility();
    validateAndSave();

    const { extremeLocked = false } = await chrome.storage.local.get("extremeLocked");
    if (extremeLocked) lockPopupUIExtreme(true);

    const { extensionInstallDate } = await chrome.storage.local.get("extensionInstallDate");
    const banner = document.getElementById("installBanner");

    if (extensionInstallDate) {
      const installDate = new Date(extensionInstallDate);
      const now = new Date();
      const diffDays = Math.floor(
  (now.setHours(0,0,0,0) - installDate.setHours(0,0,0,0)) / (1000 * 60 * 60 * 24)
);

      const emoji = diffDays === 0
        ? "🧊"
        : diffDays >= 7
          ? "🔥"
          : "🍇";

      banner.textContent = `📅 Installed on ${installDate.toLocaleDateString()} | Streak: ${diffDays} ${emoji}`;
    } else {
      const now = new Date();
      const installDate = now;
      const diffDays = 0;
      const emoji = "🧊";

      banner.textContent = `📅 Installed on ${installDate.toLocaleDateString()} | Streak: ${diffDays} ${emoji}`;

      // ✅ Save it so we don’t show "unknown" again
      await chrome.storage.local.set({ extensionInstallDate: Date.now() });
    }



  }

  // Toggles visibility of lock configuration sections based on selected focusMode.
  function updateLockVisibility() {
    const selected = document.querySelector('input[name="focusMode"]:checked')?.value;
    lockContainers.forEach(container => {
      container.style.display = container.dataset.mode === selected ? "block" : "none";
    });
  }

  // Validates and clamps number inputs (D, G, H, J), stores them in chrome.storage.local
  // Enforces J <= H rule
  function validateAndSave() {
    const values = {};
    allNumberInputs.forEach(num => {
      const id = num.id;
      const raw = parseFloat(num.value);
      const v = isNaN(raw) ? 0.1 : clamp(raw);
      num.value = v;
      values[id] = v;
    });

    if (values.J > values.H) {
      values.J = values.H;
      document.getElementById("J").value = values.H;
    }

    chrome.storage.local.set(values);
  }

  input.addEventListener("input", () => {
    chrome.storage.local.set({ goal: input.value });
  });

  document.querySelectorAll('input[name="focusMode"]').forEach(r => {
    r.addEventListener("change", () => {
      pendingFocusMode = document.querySelector('input[name="focusMode"]:checked')?.value;
      updateLockVisibility();
    });
  });


  const lockMap = {
    lockOnAllDay: "iconOnAllDay",
    lockTimer: "iconTimer",
    lockCycle: "iconCycle"
  };

  for (const [checkboxId, iconId] of Object.entries(lockMap)) {
    const checkbox = document.getElementById(checkboxId);
    const icon = document.getElementById(iconId);
    if (!checkbox || !icon) continue;

    checkbox.checked = false;
    icon.textContent = "🔓";

    checkbox.addEventListener("change", () => {
      icon.textContent = checkbox.checked ? "🔒" : "🔓";
    });
  }

  saveFocusButton.addEventListener("click", async () => {
    // 🚧 Prevent weakening an active lock without password
  {
    const now = Date.now();
    const { extremeLocked = false, manualUILockUntil = 0 } = await chrome.storage.local.get(["extremeLocked", "manualUILockUntil"]);
    const hasUILock = manualUILockUntil > now;
    const isTryingToEnableAnyLock =
      (document.getElementById("lockOnAllDay")?.checked) ||
      (document.getElementById("lockTimer")?.checked) ||
      (document.getElementById("lockCycle")?.checked);

    if ((extremeLocked || hasUILock) && !isTryingToEnableAnyLock) {
      alert("Settings are locked. Use the 🔐 Password button to unlock before changing focus settings.");
      return;
    }
  }
const mode = pendingFocusMode || currentFocusMode;
  currentFocusMode = mode;
  showFocusActive = (mode === "onAllDay");

  let manualUILockUntil = 0;

  if (mode === "onAllDay" && document.getElementById("lockOnAllDay").checked) {
      const ok_lock = await ensurePasswordForLock();
  if (!ok_lock) return;
manualUILockUntil = Date.now() + 12 * 60 * 60 * 1000;
    await chrome.storage.local.set({ lockOnAllDay: true, manualUILockUntil, focusMode: mode });
    document.getElementById("iconOnAllDay").textContent = "🔒";
} else if (mode === "timer" && document.getElementById("lockTimer").checked) {
    const ok_lock = await ensurePasswordForLock();
  if (!ok_lock) return;
manualUILockUntil = Date.now() + clamp(document.getElementById("D").value) * 60 * 1000;
  await chrome.storage.local.set({ lockTimer: true, manualUILockUntil, focusMode: mode });
  document.getElementById("iconTimer").textContent = "🔒";

  // Immediately block the UI
  lockUI();

  // Immediately update badge to 🔒🕒score
  //chrome.storage.local.get(["score"]).then(({ score = 5 }) => {
    //chrome.action.setBadgeBackgroundColor({ color: "#9E9E9E" });
   // chrome.action.setBadgeText({ text: `🔒🕒${score}` });
 // });
}
else if (mode === "cycle" && document.getElementById("lockCycle").checked) {
    const ok_lock = await ensurePasswordForLock();
  if (!ok_lock) return;
const G = clamp(document.getElementById("G").value);
  const H = clamp(document.getElementById("H").value);
  manualUILockUntil = Date.now() + (G + H) * 60 * 1000;

  await chrome.storage.local.set({
    lockCycle: true,
    manualUILockUntil,
    focusMode: mode
  });

  document.getElementById("iconCycle").textContent = "🔒";
  lockUI(); // ✅ This line makes the lock immediately take effect

  // ✅ Set badge to ☕ immediately since we're entering relax mode now
  const { score = 5 } = await chrome.storage.local.get("score");
  chrome.runtime.sendMessage({
    action: "refreshBadge",
    payload: {
      score,
      focusMode: "cycle",
      lockoutUntil: 0,
      manualUILockUntil: manualUILockUntil
    }
  });
}
 else if (mode === "off") {
  await chrome.storage.local.set({
    focusMode: "off",
    lockoutUntil: 0,
    manualUILockUntil: 0,
    autoLockUntil: 0,
    focusPhaseStart: null,
    focusPhaseMode: null
  });
  chrome.alarms.clear("poll");
  unlockUI();
  status.textContent = "🚫 Focus Off — No monitoring active.";

  // ← NEW: immediately update the badge to 🚫score
  //chrome.storage.local.get(["score"]).then(({ score = 5 }) => {
   // chrome.action.setBadgeText({ text: `🚫${score}` });
  //});
}
 else {
    // ✅ ADD THIS: Save non-locked mode
    await chrome.storage.local.set({
      focusMode: mode,
      manualUILockUntil: 0
    });
  }

  validateAndSave();

  let focusDisplay = "";

  if (mode === "timer" || mode === "cycle") {
    focusDisplay = startFocusTimer(mode);
  } else {
    chrome.storage.local.remove(["focusPhaseStart", "focusPhaseMode"]);
    focusDisplay = ""; // ensure stale closure is not passed to updateStatusLive
  }
    const { autoLockUntil = 0, score = 5 } = await chrome.storage.local.get(["autoLockUntil", "score"]);
    updateStatusLive(manualUILockUntil ?? 0, autoLockUntil, score, focusDisplay);
  });


  allNumberInputs.forEach(num => {
    // Allow free typing
    num.addEventListener("change", validateAndSave);
  });

  document.getElementById("openSettings").addEventListener("click", () => {
    chrome.runtime.openOptionsPage();
  });

  document.getElementById("openUserGuide").addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("guide.html") });
  });

  initializePopup();
});
