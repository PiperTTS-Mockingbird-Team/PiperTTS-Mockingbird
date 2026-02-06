# TextyMcSpeechy - Windows Quick Start Guide

This folder has been updated with PowerShell scripts to make it compatible with Windows without requiring a dedicated Linux partition or manual WSL2 setup (though Docker Desktop will use WSL2 behind the scenes).

## Prerequisites

1.  **Docker Desktop**: [Download and Install](https://www.docker.com/products/docker-desktop/).
    *   Ensure "Use the WSL 2 based engine" is checked in Settings > General.
2.  **NVIDIA Drivers**: If you have an NVIDIA GPU, ensure your drivers are up to date.
3.  **PowerShell**: Use PowerShell 5.1 or 7 (standard on Windows).

## Getting Started

1.  **Run Setup**:
    Open PowerShell in this directory and run:
    ```powershell
    .\setup.ps1
    ```
    This will check your Docker installation and create the necessary configuration.

2.  **Create a Training Dojo**:
    A "Dojo" is a workspace for a specific voice.
    ```powershell
    .\new_dojo.ps1 MyVoice
    ```
    This creates `tts_dojo\MyVoice_dojo`.

3.  **Prepare Your Dataset**:
    Follow the original [quick_start_guide.md](quick_start_guide.md) to place your `.wav` files and `metadata.csv` (in LJSpeech format) into the `target_voice_dataset` folder inside your new Dojo.

4.  **Start Training**:
    ```powershell
    .\run_training.ps1
    ```
    Pick your Dojo from the list. This script will:
    *   Start the Docker container if it's not running.
    *   Open a bash shell inside the container and start the interactive training guide.

## Useful Commands

*   `.\run_container.ps1`: Just start the environment.
*   `.\stop_container.ps1`: Shut down the Docker environment.
*   `.\run_training.ps1`: Resume training or check status.

## Hardware Requirements for Training

### Minimum (CPU-only - slow)
- **CPU**: 6+ cores
- **RAM**: 16GB
- **Storage**: 10GB+ free (SSD recommended)
- **Training Time**: 12-24 hours per voice

### Recommended (GPU-accelerated)
- **CPU**: 6+ cores
- **RAM**: 16GB+ (32GB ideal)
- **GPU**: NVIDIA GPU with 8GB+ VRAM (GTX 1070 Ti or better)
- **Storage**: SSD with 20GB+ free
- **Training Time**: 2-4 hours per voice

### Optimal
- **CPU**: 8+ cores
- **RAM**: 32GB+
- **GPU**: NVIDIA GPU with 12GB+ VRAM (RTX 3060, RTX 3080, etc.)
- **Storage**: SSD with 50GB+ free
- **Training Time**: 1-3 hours per voice

**Note:** These specs are only for training custom voices. If you just want to use the TTS server with pre-trained voices, it runs on almost any hardware (2GB RAM is enough).

## Note on GPU Acceleration
If `setup.ps1` reports that GPU support is not functional, training will run on your CPU (which is much slower). Ensure you have the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) logic integrated via Docker Desktop (it usually works out of the box with modern Docker Desktop and WSL2).
