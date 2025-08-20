import { initOrbs } from "./orbs.js";

chrome.storage.local
  .get({ particlesOnGuide: true })
  .then(({ particlesOnGuide }) => {
    if (particlesOnGuide) {
      initOrbs({ initialParticles: 6000 });
    }
  });
