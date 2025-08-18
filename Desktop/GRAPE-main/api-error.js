// api-error.js
document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("openSettingsBtn");
  if (btn) {
    btn.addEventListener("click", () => {
      chrome.runtime.openOptionsPage();
    });
  }
});
