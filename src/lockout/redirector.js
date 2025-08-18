import { log } from '../utils/logger.js';

// redirector.js

// Check if the URL is a ChatGPT domain
export function isChatGPT(url) {
  return url.includes("chat.openai.com") || url.includes("chatgpt.com");
}

// Return referrer if it's not from a ChatGPT domain
export function getNonChatGPTReferrer() {
  const referrer = document.referrer || "";
  return isChatGPT(referrer) ? null : referrer;
}

// Decide where to redirect after lockout ends
export async function getRedirectTarget(orig, tabId) {
  log("🔍 getRedirectTarget() called with:", { orig, tabId });

  let original = "";

  // Try decoding the original URL safely
  try {
    original = decodeURIComponent(orig || "");
    log("✅ Decoded original URL:", original);
  } catch (err) {
    console.warn("⚠️ Failed to decode original URL:", orig);
    original = orig || "";
  }

  // Fallback: if no original and we have a tabId, check local storage
  if (!original && tabId) {
    const key = `origUrl_${tabId}`;
    const storage = await chrome.storage.local.get(key);
    original = storage[key] || "";
    log("📦 Fallback from chrome.storage.local:", original);
  }

  let target = original;

  // If it's a ChatGPT link, redirect to homepage instead of specific chat
  if (isChatGPT(original)) {
    target = `https://chat.openai.com/?fresh=${Date.now()}`;
    log("🔁 ChatGPT override → redirecting to homepage:", target);
  }

  // Log final result
  if (!target) {
    console.warn("⚠️ No valid redirect target found");
  } else {
    log("🚀 Final redirect target:", target);
  }

  return target || null;
}
