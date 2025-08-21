// api-error.js
import { logger } from '../utils/logger.js';

const log = logger('options');

document.addEventListener("DOMContentLoaded", () => {
  const details = document.getElementById("errorDetails");

  chrome.storage.local.get("lastApiError", ({ lastApiError }) => {
    const message = lastApiError || "No additional error details available.";
    if (details) details.textContent = message;
    if (lastApiError) log("API error:", lastApiError);
  });

  const btn = document.getElementById("openSettingsBtn");
  if (btn) {
    btn.addEventListener("click", () => {
      chrome.runtime.openOptionsPage();
    });
  }
});
