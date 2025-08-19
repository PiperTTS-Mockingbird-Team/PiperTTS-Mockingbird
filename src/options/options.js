
/* options.js – cleaned & lock-aware */
import { clamp } from '../utils/utils.js';
const $ = (id) => document.getElementById(id);
const KEYS = [
  "charLimit","gptScanInterval","hoursPerDay","scanInterval","blockDuration","blockThreshold","userNotes",
  "blockedSites","blockedWords","bannedCheckInterval","insertOnRedirect","redirectTemplate",
  "blockLimit","blockWindowMinutes","lockoutCustomText",
  "useAccountabilityIntervention","blockTimeMultiplier","debug","resetFocusOnRestart"
];

let providers = [];
function renderProviders(list){
  providers = list.sort((a,b)=>a.order-b.order);
  const wrap = $("providerList");
  if (!wrap) return;
  wrap.innerHTML = "";
  providers.forEach((p, idx) => {
    const row = document.createElement("div");
    row.className = "field provider-row";
    row.dataset.provider = p.name;
    row.dataset.index = idx;
    row.innerHTML = `
      <label class="label">${p.name.charAt(0).toUpperCase()+p.name.slice(1)} API key</label>
      <input type="text" value="${p.key || ""}" autocomplete="off" spellcheck="false" />
      <div class="actions"><button class="up">↑</button><button class="down">↓</button></div>
    `;
    wrap.appendChild(row);
  });
}

/** Lock-aware toggle for the Save button */
async function updateSaveBtnLock() {
  const now = Date.now();
  const { lockoutUntil = 0, manualUILockUntil = 0, extremeLocked = false } =
    await chrome.storage.local.get(["lockoutUntil", "manualUILockUntil", "extremeLocked"]);
  const lockedByTimer = now < lockoutUntil || now < manualUILockUntil;
  const isLocked = lockedByTimer || !!extremeLocked;
  const btn = $("saveBtn");
  if (!btn) return;
  btn.disabled = isLocked;
  btn.title = isLocked
    ? "Settings are locked during focus/lockout. Use the password control or wait until the timer ends."
    : "";
}

// Keep button state in sync with storage changes
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes.lockoutUntil || changes.manualUILockUntil || changes.extremeLocked) {
    updateSaveBtnLock();
  }
});

// === Init ===
document.addEventListener("DOMContentLoaded", async () => {
  const stored = await chrome.storage.local.get([...KEYS, "lastApiError", "apiKey"]);
  const sync = await chrome.storage.sync.get("providers");
  let providerData = sync.providers;
  if (!providerData) {
    providerData = [
      { name: "openai", key: stored.apiKey || "", order: 0 },
      { name: "gemini", key: "", order: 1 }
    ];
    await chrome.storage.sync.set({ providers: providerData });
  }
  renderProviders(providerData);

  // Show any API error
  const statusEl = $("apiStatus");
  if (stored.lastApiError && statusEl) {
    statusEl.textContent = stored.lastApiError;
    statusEl.style.color = "red";
    chrome.storage.local.remove("lastApiError");
  }

  // Populate inputs (guard each id in case the section is not present)
  if ($("charLimit")) $("charLimit").value = stored.charLimit ?? 1000;
  if ($("gptScanInterval")) {
    const val = stored.gptScanInterval ?? stored.scanInterval ?? 0;
    $("gptScanInterval").value = val;
  }
  if ($("hoursPerDay")) $("hoursPerDay").value = stored.hoursPerDay ?? 1;
  if ($("blockDuration")) $("blockDuration").value = stored.blockDuration ?? 0.3;
  if ($("blockThreshold")) $("blockThreshold").value = stored.blockThreshold ?? 4;
  if ($("resetFocusOnRestart")) $("resetFocusOnRestart").checked = stored.resetFocusOnRestart ?? true;
  if ($("userNotes")) $("userNotes").value = stored.userNotes ?? "";
  if ($("blockedSites")) $("blockedSites").value = (stored.blockedSites || []).join("\n");
  if ($("blockedWords")) $("blockedWords").value = (stored.blockedWords || []).join("\n");
  if ($("bannedCheckInterval")) $("bannedCheckInterval").value = stored.bannedCheckInterval ?? 30;

  // Optional priming settings
  const insertCB = $("insertOnRedirect");
  const tmplTA   = $("redirectTemplate");
  if (insertCB) insertCB.checked = stored.insertOnRedirect ?? true;
  if (tmplTA)   tmplTA.value     = stored.redirectTemplate ?? "My current goal is: {goal}";

  // Escalation settings
  if ($("blockLimit")) $("blockLimit").value = stored.blockLimit ?? 3;
  if ($("blockWindowMinutes")) $("blockWindowMinutes").value = stored.blockWindowMinutes ?? 10;
  if ($("useAccountabilityIntervention")) $("useAccountabilityIntervention").checked = stored.useAccountabilityIntervention ?? true;
  if ($("blockTimeMultiplier")) $("blockTimeMultiplier").value = stored.blockTimeMultiplier ?? 2;
  if ($("debug")) $("debug").checked = stored.debug ?? false;

  // Custom lockout page message from Settings
  if ($("lockoutCustomText")) $("lockoutCustomText").value = stored.lockoutCustomText ?? "";

  // Live cost calc hooks
  ["charLimit","gptScanInterval","hoursPerDay"].forEach(id => { if ($(id)) $(id).addEventListener("input", updateCost); });
  updateCost();

  if ($("providerList")) {
    $("providerList").addEventListener("click", (e) => {
      const btn = e.target;
      if (!btn.classList.contains('up') && !btn.classList.contains('down')) return;
      const row = btn.closest('.provider-row');
      const idx = parseInt(row.dataset.index);
      const newIdx = idx + (btn.classList.contains('up') ? -1 : 1);
      if (newIdx < 0 || newIdx >= providers.length) return;
      const [moved] = providers.splice(idx, 1);
      providers.splice(newIdx, 0, moved);
      providers.forEach((p,i)=>p.order=i);
      renderProviders(providers);
    });
  }

  // Save handler
  if ($("saveBtn")) $("saveBtn").addEventListener("click", async () => {
    // Hard guard while locked
    if ($("saveBtn").disabled) {
      alert("Settings are locked right now. Use the 🔐 Password control or wait until the timer ends.");
      return;
    }

    const data = {};
    if ($("charLimit")) data.charLimit = clamp($("charLimit").value, 100, 4000);
    if ($("gptScanInterval")) data.gptScanInterval = clamp($("gptScanInterval").value, 0, 60);
    if ($("hoursPerDay")) data.hoursPerDay = clamp($("hoursPerDay").value, 0, 24);
    if ($("blockDuration")) data.blockDuration = clamp($("blockDuration").value, 0.1, 720);
    if ($("blockThreshold")) data.blockThreshold = clamp($("blockThreshold").value, -5, 10);
    if ($("resetFocusOnRestart")) data.resetFocusOnRestart = $("resetFocusOnRestart").checked;
    if ($("userNotes")) data.userNotes = $("userNotes").value;
    if ($("blockedSites")) data.blockedSites = $("blockedSites").value.split("\n").map(s => s.trim()).filter(Boolean);
    if ($("blockedWords")) data.blockedWords = $("blockedWords").value.split("\n").map(w => w.trim()).filter(Boolean);
    if ($("bannedCheckInterval")) data.bannedCheckInterval = clamp($("bannedCheckInterval").value, 1, 300);

    // Priming settings
    if (insertCB) data.insertOnRedirect = insertCB.checked;
    if (tmplTA)   data.redirectTemplate = tmplTA.value;

    // Escalation settings
    if ($("blockLimit")) data.blockLimit = clamp($("blockLimit").value, 1, 20);
    if ($("blockWindowMinutes")) data.blockWindowMinutes = clamp($("blockWindowMinutes").value, 1, 120);
    if ($("useAccountabilityIntervention")) data.useAccountabilityIntervention = $("useAccountabilityIntervention").checked;
    if ($("blockTimeMultiplier")) data.blockTimeMultiplier = clamp($("blockTimeMultiplier").value, 1, 10);
    if ($("debug")) data.debug = $("debug").checked;

    // Custom lockout message
    if ($("lockoutCustomText")) data.lockoutCustomText = $("lockoutCustomText").value.trim();

    const providerRows = [...document.querySelectorAll('#providerList .provider-row')];
    const providersToSave = providerRows.map((row, idx) => ({
      name: row.dataset.provider,
      key: row.querySelector('input').value.trim(),
      order: idx
    }));
    await chrome.storage.sync.set({ providers: providersToSave });

    const hasKey = providersToSave.some(p => p.key);
    if ((data.gptScanInterval ?? 0) > 0 && !hasKey) {
      const statusEl = $("apiStatus");
      if (statusEl) {
        statusEl.textContent = "API key required for GPT scans to work.";
        statusEl.style.color = "red";
      }
      data.gptScanInterval = 0;
      if ($("gptScanInterval")) $("gptScanInterval").value = 0;
    }

    data.scanInterval = data.gptScanInterval; // legacy mirror
    await chrome.storage.local.set(data);
    if ($("saveBtn")) {
      $("saveBtn").textContent = "✅ Saved!";
      setTimeout(() => ($("saveBtn").textContent = "💾 Save settings"), 1500);
    }
    updateCost();
    try { chrome.runtime.sendMessage({ action: "settingsUpdated" }); } catch {}
  });

  updateSaveBtnLock();
});

// Simple cost estimate display
function updateCost(){
  const charLimit = parseFloat($("charLimit")?.value ?? 1000);
  const scanInterval = parseFloat($("gptScanInterval")?.value ?? 2);
  const hoursPerDay = parseFloat($("hoursPerDay")?.value ?? 1);
  if (!Number.isFinite(charLimit) || !Number.isFinite(scanInterval) || !Number.isFinite(hoursPerDay)) return;
  if (scanInterval <= 0 || hoursPerDay <= 0) {
    if ($("costHour")) $("costHour").textContent = "$0.0000 / hour";
    if ($("costDollar")) $("costDollar").textContent = `≈ $0 at ${hoursPerDay} h/day`;
    return;
  }
  const perHour = 3600 / scanInterval;
  const tokensPerScan = charLimit * 1.33; // rough prompt+response multiplier
  const tokensPerHour = perHour * tokensPerScan;
  const dollarsPerHour = tokensPerHour / 1_000_000 * 5; // ballpark at $5/1M tokens
  if ($("costHour")) $("costHour").textContent = `$${dollarsPerHour.toFixed(4)} / hour`;
  const dollarsPerDay = dollarsPerHour * hoursPerDay;
  const daysPerDollar = dollarsPerDay > 0 ? 1 / dollarsPerDay : Infinity;
  const pretty = daysPerDollar === Infinity ? "∞" : Math.max(1, Math.round(daysPerDollar));
  if ($("costDollar")) $("costDollar").textContent = `≈ $1 every ${pretty} day${pretty === 1 ? "" : "s"} at ${hoursPerDay} h/day`;
}

// Show API errors sent from background/content scripts, if any
chrome.runtime.onMessage.addListener((request) => {
  if (request.action === "showApiError") {
    const statusEl = $("apiStatus");
    if (statusEl) {
      statusEl.textContent = request.message || "❌ API Error";
      statusEl.style.color = "red";
    }
    console.error("⚠️ " + (request.message || "Unknown API error"));
  }
});
