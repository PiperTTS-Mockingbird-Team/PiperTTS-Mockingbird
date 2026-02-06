# Future Plans

## New Engine Support

- **Add Kokoro-82M Support**: One day I might add Kokoro-82M to this UI. It offers significantly higher vocal quality and more natural prosody.
  - **Why not now?**: I chose Piper as the primary engine because it is the fastest local TTS available and can run on almost any hardware—even "potatoes" like a Raspberry Pi 4.

## Maximum Future-Proofing (Optional)

- **Create offline backup archive** for guaranteed 10+ year stability:
  - Export Docker image: `docker save domesticatedviking/textymcspeechy-piper > docker_image.tar`
  - Archive the entire `.venv/` folder (all Python packages)
  - Archive `src/piper/` folder (Piper binaries)
  - Bundle all trained `.onnx` voice models
  - This backup guarantees the project works identically even if external dependencies disappear
