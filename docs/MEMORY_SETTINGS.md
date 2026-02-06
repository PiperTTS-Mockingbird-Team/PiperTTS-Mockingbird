# Quick Memory Settings Reference

## 🚀 Quick Start

Set these environment variables before starting the server:

### Windows (PowerShell)
```powershell
$env:PIPER_MAX_PROCESSES = "3"
$env:PIPER_CHUNK_SIZE = "5000"
python src/piper_server.py
```

### Linux/macOS
```bash
export PIPER_MAX_PROCESSES=3
export PIPER_CHUNK_SIZE=5000
python src/piper_server.py
```

## 📊 Presets

### Low Memory (< 4GB RAM)
```bash
PIPER_MAX_PROCESSES=1
PIPER_CHUNK_SIZE=3000
PIPER_PROCESS_IDLE_TIMEOUT=60
```
Expected usage: ~150-200MB

### Balanced (4-8GB RAM) - **DEFAULT**
```bash
PIPER_MAX_PROCESSES=3
PIPER_CHUNK_SIZE=5000
PIPER_PROCESS_IDLE_TIMEOUT=120
```
Expected usage: ~300-450MB

### High Performance (> 16GB RAM)
```bash
PIPER_MAX_PROCESSES=10
PIPER_CHUNK_SIZE=10000
PIPER_PROCESS_IDLE_TIMEOUT=300
```
Expected usage: ~800MB-1.5GB

## 🔧 Settings Explained

| Variable | Default | What It Does |
|----------|---------|--------------|
| `PIPER_MAX_PROCESSES` | 3 | Max concurrent voice processes |
| `PIPER_CHUNK_SIZE` | 5000 | Characters per chunk (for long texts) |
| `PIPER_MAX_TEXT_LENGTH` | 100000 | Absolute max characters (safety limit) |
| `PIPER_PROCESS_IDLE_TIMEOUT` | 120 | Seconds before cleanup |

## 📈 Check Current Settings

Visit: `http://localhost:8786/health`

Look for the `memory_settings` section:
```json
{
  "ok": true,
  "memory_settings": {
    "max_processes": 3,
    "max_text_length": 100000,
    "idle_timeout_seconds": 120,
    "active_processes": 1
  }
}
```

## 🎯 Common Scenarios

**Q: Server uses too much memory**
```bash
# Reduce processes and chunk size
export PIPER_MAX_PROCESSES=1
export PIPER_CHUNK_SIZE=3000
export PIPER_PROCESS_IDLE_TIMEOUT=60
```

**Q: Long texts processing slowly**
```bash
# Increase chunk size for faster processing
export PIPER_CHUNK_SIZE=10000
```

**Q: Getting "text too long" errors**
```bash
# You hit the 100K safety limit - split your text
# Or increase (use carefully, may cause memory issues):
export PIPER_MAX_TEXT_LENGTH=200000
```

**Q: Slow when switching voices**
```bash
# Increase timeout to keep processes alive longer
export PIPER_PROCESS_IDLE_TIMEOUT=300
```

**Q: Running in Docker**
Add to `docker-compose.yml`:
```yaml
environment:
  - PIPER_MAX_PROCESSES=2
  - PIPER_CHUNK_SIZE=5000
```

## 📝 Full Documentation

See [MEMORY_OPTIMIZATION.md](MEMORY_OPTIMIZATION.md) for complete details.
