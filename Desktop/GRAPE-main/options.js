
/* options.js – cleaned & lock-aware */
import { clamp } from './src/utils.js';
const $ = (id) => document.getElementById(id);
const KEYS = [
  "charLimit","scanInterval","apiKey","blockDuration","blockThreshold","userNotes",
  "blockedWords","bannedCheckInterval","insertOnRedirect","redirectTemplate",
  "blockLimit","blockWindowMinutes","lockoutCustomText",
  "useAccountabilityIntervention","blockTimeMultiplier","debug"
];

function maskKey(k){
  if (!k) return "";
  if (k.length <= 8) return "••••" + k.slice(-2);
  return k.slice(0,4) + "••••" + k.slice(-4);
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
  const stored = await chrome.storage.local.get([...KEYS, "lastApiError"]);

  // Show any API error
  const statusEl = $("apiStatus");
  if (stored.lastApiError && statusEl) {
    statusEl.textContent = stored.lastApiError;
    statusEl.style.color = "red";
    chrome.storage.local.remove("lastApiError");
  }

  // Populate inputs (guard each id in case the section is not present)
  if ($("charLimit")) $("charLimit").value = stored.charLimit ?? 1000;
  if ($("scanInterval")) $("scanInterval").value = stored.scanInterval ?? 2.1;
  if ($("blockDuration")) $("blockDuration").value = stored.blockDuration ?? 0.3;
  if ($("blockThreshold")) $("blockThreshold").value = stored.blockThreshold ?? 4;
  if ($("userNotes")) $("userNotes").value = stored.userNotes ?? "";
  if ($("blockedWords")) $("blockedWords").value = (stored.blockedWords || []).join("\n");
  if ($("bannedCheckInterval")) $("bannedCheckInterval").value = stored.bannedCheckInterval ?? 30;

  // API key masking
  if ($("apiKey") && stored.apiKey) {
    $("apiKey").value = maskKey(stored.apiKey);
    $("apiKey").dataset.full = stored.apiKey;
  }

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
  ["charLimit","scanInterval"].forEach(id => { if ($(id)) $(id).addEventListener("input", updateCost); });
  updateCost();

  // Save handler
  if ($("saveBtn")) $("saveBtn").addEventListener("click", async () => {
    // Hard guard while locked
    if ($("saveBtn").disabled) {
      alert("Settings are locked right now. Use the 🔐 Password control or wait until the timer ends.");
      return;
    }

    const data = {};
    if ($("charLimit")) data.charLimit = clamp($("charLimit").value, 100, 4000);
    if ($("scanInterval")) data.scanInterval = clamp($("scanInterval").value, 0.1, 60);
    if ($("blockDuration")) data.blockDuration = clamp($("blockDuration").value, 0.1, 720);
    if ($("blockThreshold")) data.blockThreshold = clamp($("blockThreshold").value, -5, 10);
    if ($("userNotes")) data.userNotes = $("userNotes").value;
    if ($("blockedWords")) data.blockedWords = $("blockedWords").value.split("\n").map(w => w.trim()).filter(Boolean);
    if ($("bannedCheckInterval")) data.bannedCheckInterval = clamp($("bannedCheckInterval").value, 1, 300);

    // API key (keep masked field UX)
    if ($("apiKey")) data.apiKey = $("apiKey").dataset.full ?? "";

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
  const charLimit = parseFloat(($("charLimit")?.value ?? 1000));
  const scanInterval = parseFloat(($("scanInterval")?.value ?? 2));
  if (!Number.isFinite(charLimit) || !Number.isFinite(scanInterval)) return;
  const perHour = 3600 / Math.max(0.1, scanInterval);
  const tokensPerScan = charLimit * 1.33; // rough prompt+response multiplier
  const tokensPerHour = perHour * tokensPerScan;
  const dollarsPerHour = tokensPerHour / 1_000_000 * 5; // ballpark at $5/1M tokens
  const pretty = dollarsPerHour > 0 ? `${Math.max(1, Math.round(1/dollarsPerHour))} hours` : "very long time";
  if ($("costDollar")) $("costDollar").textContent = `≈ $1 every ${pretty}`;
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
