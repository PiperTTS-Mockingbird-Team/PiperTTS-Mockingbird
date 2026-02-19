# Potato-Local-AI

A local search and AI assistant pipeline using DuckDuckGo, image search, and Ollama.

## Features
- DuckDuckGo Search Integration
- Image Search Capability
- Local AI processing via Ollama
- GUI Application interface ([gui_app.py](gui_app.py))

## Hardware Compatibility (Potato-Friendly!)
This project is designed to run efficiently even on "potato" computers. It is specifically optimized for:
- **Low RAM:** Works with as little as 8GB RAM.
- **Integrated Graphics:** No dedicated GPU required; runs well on integrated graphics cards.
- **Model Recommendation:** Optimized to work flawlessly with the **qwen3:1.7b** model via Ollama. 

By optimizing for **qwen3:1.7b**, you are targeting a model that only uses about 1.4GB of RAM but has the reasoning power of older 3B models. This leaves enough breathing room for your browser, the OS, and your Python scripts to run simultaneously without freezing your computer.

It handles web searches, image searches, and general AI chat comfortably on these lower-spec machines.

## Project Structure
- `ddgsearch.py`: Integration with DuckDuckGo.
- `image_search.py`: Core image search logic.
- `gui_app.py`: Desktop application interface.
- `test_*.py`: Various test scripts for components and performance.

## Prerequisites
- Python 3.x
- Ollama (running locally)

## Installation & Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/mindcraft0/Potato-Local-AI.git
   ```
2. Setup a virtual environment and install dependencies (see [requirements.txt](requirements.txt) if generated).
3. Ensure Ollama is running on your machine.
