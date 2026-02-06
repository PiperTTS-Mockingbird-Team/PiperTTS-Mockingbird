# Piper Server Performance Guide

Quick reference for developers working with the optimized Piper TTS Server.

## Key Performance Features

### 1. Config Caching
Model configurations are cached for 5 minutes with automatic invalidation on file changes.

**Usage**: Just use the model normally - caching is automatic.

**Clear cache manually**:
```python
_MODEL_CONFIG_CACHE.clear()
```

### 2. Streaming WAV Processing
Large audio concatenations use streaming to reduce memory.

**Automatic**: No code changes needed, works transparently.

**Memory savings**: ~60-80% for long texts (>10 chunks).

### 3. Smart Text Chunking
Text is intelligently split at paragraph and sentence boundaries.

**Control chunk size**:
```bash
export PIPER_CHUNK_SIZE=5000  # Default
export PIPER_CHUNK_SIZE=10000 # Fewer, larger chunks
export PIPER_CHUNK_SIZE=3000  # More, smaller chunks (better for low memory)
```

**Algorithm priority**:
1. Paragraphs (double newlines)
2. Sentences (. ! ? punctuation)
3. Hard split if needed

### 4. Process Management
Processes are gracefully terminated with proper cleanup.

**Idle timeout**:
```bash
export PIPER_PROCESS_IDLE_TIMEOUT=120  # Default: 2 minutes
```

**Max concurrent**:
```bash
export PIPER_MAX_PROCESSES=3  # Default
```

## Performance Tips

### For Maximum Speed
```bash
export PIPER_MAX_PROCESSES=10        # Allow more concurrent voices
export PIPER_PROCESS_IDLE_TIMEOUT=600 # Keep processes alive longer
export PIPER_CHUNK_SIZE=10000         # Larger chunks
```

### For Minimum Memory
```bash
export PIPER_MAX_PROCESSES=1         # Single process only
export PIPER_PROCESS_IDLE_TIMEOUT=30 # Aggressive cleanup
export PIPER_CHUNK_SIZE=3000          # Smaller chunks
```

### Balanced (Recommended)
```bash
export PIPER_MAX_PROCESSES=3         # Default
export PIPER_PROCESS_IDLE_TIMEOUT=120 # Default
export PIPER_CHUNK_SIZE=5000          # Default
```

## Monitoring

### Check Cache Status
```python
# In Python REPL or debug code:
from piper_server import _MODEL_CONFIG_CACHE
print(f"Cached configs: {len(_MODEL_CONFIG_CACHE)}")
```

### Monitor Memory
```powershell
# Windows PowerShell
while($true) {
    Get-Process python | Select Name, @{N='MB';E={[int]($_.WS/1MB)}}
    Start-Sleep 1
}
```

```bash
# Linux/macOS
watch -n 1 'ps aux | grep python'
```

### View Process Count
```python
from piper_server import manager
print(f"Active processes: {len(manager.processes)}")
```

## API Usage

No API changes - all optimizations are transparent!

### Standard Request
```javascript
fetch('/api/tts', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    text: "Your text here",
    voice_model: "en_US-amy-medium.onnx"
  })
})
```

### Long Text (Automatic Chunking)
```javascript
// Server automatically chunks texts > CHUNK_SIZE
fetch('/api/tts', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    text: veryLongText,  // Up to 100,000 chars
    voice_model: "en_US-amy-medium.onnx"
  })
})
```

## Troubleshooting

### "Process limit reached"
**Cause**: Too many concurrent voice models active.
**Solution**: Increase `PIPER_MAX_PROCESSES` or wait for idle cleanup.

### Slow first request, fast subsequent
**Expected**: First request starts process + loads model (~500-1000ms).
**Subsequent requests**: Reuse warm process (~200-500ms).
**Optimization**: Use `/api/warmup` to pre-load voices.

### High memory usage
**Check**: How many processes are active?
**Solution**: Lower `PIPER_PROCESS_IDLE_TIMEOUT` for faster cleanup.

### Audio quality issues with long texts
**Cause**: Text chunking at awkward boundaries.
**Solution**: Add paragraph breaks in your input text for better chunking.

## Code Examples

### Pre-warm a Voice
```python
import requests

# Start a voice process before first real use
requests.post('http://localhost:5050/api/warmup', json={
    'voice_model': 'en_US-amy-medium.onnx'
})
```

### Check Server Health
```python
import requests

health = requests.get('http://localhost:5050/health').json()
if not health['ok']:
    print(f"Server issue: {health.get('error', 'Unknown')}")
```

### Batch Processing
```python
texts = ["Text 1", "Text 2", "Text 3"]
voice = "en_US-amy-medium.onnx"

for i, text in enumerate(texts):
    response = requests.post('http://localhost:5050/api/tts', 
        json={'text': text, 'voice_model': voice})
    
    with open(f'output_{i}.wav', 'wb') as f:
        f.write(response.content)
```

## Best Practices

1. **Reuse voices**: Multiple requests to the same voice reuse the process
2. **Add paragraph breaks**: Helps chunking algorithm work better
3. **Monitor memory**: Set alerts if usage exceeds thresholds
4. **Graceful shutdown**: Use SIGTERM, not SIGKILL for proper cleanup
5. **Update configs**: Server detects config file changes automatically

## Performance Metrics

Track these metrics to monitor server health:

- **Request latency**: Should be <1s for cached voices
- **Memory usage**: Should stabilize after initial requests
- **Process count**: Should decrease during idle periods
- **Error rate**: Should be <0.1% under normal load

---

**Last Updated**: February 2, 2026
**Version**: 1.2
