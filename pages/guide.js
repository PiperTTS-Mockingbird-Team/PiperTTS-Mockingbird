import { initOrbs } from "./orbs.js";

chrome.storage.local
  .get({ particlesOnGuide: true })
  .then(({ particlesOnGuide }) => {
    initOrbs({
      initialParticles: particlesOnGuide ? 6000 : 0,
      maxParticles: particlesOnGuide ? 12000 : 0,
    });
  });
