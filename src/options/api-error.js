// api-error.js
document.addEventListener("DOMContentLoaded", () => {
  const details = document.getElementById("errorDetails");

  chrome.storage.local.get("lastApiError", ({ lastApiError }) => {
    const message = lastApiError || "No additional error details available.";
    if (details) details.textContent = message;
    if (lastApiError) console.log("API error:", lastApiError);
  });

  const btn = document.getElementById("openSettingsBtn");
  if (btn) {
    btn.addEventListener("click", () => {
      chrome.runtime.openOptionsPage();
    });
  }
});
