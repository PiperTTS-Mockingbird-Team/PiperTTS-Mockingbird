// blocklist.js

const box = document.getElementById("siteBox");
const saveBtn = document.getElementById("saveBtn");
const backBtn = document.getElementById("backBtn");

function saveBlocklist() {
  const cleaned = box.value
    .split("\n")
    .map(line => line.trim())
    .filter(line => line.length > 0);
  chrome.storage.local.set({ blockedSites: cleaned });
}

chrome.storage.local.get("blockedSites", ({ blockedSites = [] }) => {
  box.value = blockedSites.join("\n");
});

saveBtn.onclick = () => {
  saveBlocklist();
  alert("✅ Blocklist updated.");
};

window.addEventListener("beforeunload", saveBlocklist);

backBtn.onclick = () => {
  window.location.href = chrome.runtime.getURL("pages/options.html");
};
