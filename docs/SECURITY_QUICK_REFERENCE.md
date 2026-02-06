# Security Hardening - Quick Reference Card

## ✅ What You Can Keep Open

**CORS is now restricted to localhost only** - this is the sweet spot for developers:

### ✅ Allowed Origins (Automatic)
- `http://localhost:3000` - React Create App
- `http://localhost:5173` - Vite
- `http://localhost:8080` - Vue CLI / Common servers
- `http://localhost:8000` - Django / FastAPI dev
- `http://127.0.0.1:*` - Same as above

### ❌ Blocked Origins (Protected)
- Any remote website (`https://evil-site.com`)
- Your server exposed to the internet without reverse proxy
- Cross-site requests from non-localhost domains

---

## 🔐 API Key Authentication

### Default Setup (Zero Config - Recommended) ✅
```bash
# No setup needed - just run the server!
python src/piper_server.py

# No API key required for local use
```

✅ Perfect for:
- Personal use on a private machine
- Standard development workflow
- Home Assistant local integration

**How it works:**
- Authentication is skipped when no `PIPER_API_KEY` is set.
- Still protected by CORS (localhost-only) and 127.0.0.1 binding.
- Only apps on your machine can reach your server.

### With API Key (Optional - For Extra Security)
```bash
# 1. Set environment variable
[System.Environment]::SetEnvironmentVariable("PIPER_API_KEY", "my-secret-key", "User")

# 2. Start server
python src/piper_server.py

# 3. Connect with X-API-Key header
curl -H "X-API-Key: my-secret-key" http://localhost:5002/api/tts ...
```

✅ Use when:
- Running on a shared local network.
- Using a reverse proxy to access from other devices.
- You want an extra layer of defense-in-depth.

---

## 🛡️ What's Protected Now

| Attack | Protected | How |
|--------|-----------|-----|
| **Malicious Website Tab** | ✅ | CORS localhost-only |
| **Path Traversal** | ✅ | Input validation |
| **Command Injection** | ✅ | Safe PowerShell params |
| **Info Disclosure** | ✅ | Relative paths only |
| **CSRF from External Sites** | ✅ | CORS restriction |
| **Unauthorized Access** | ⚠️ | Optional (API key) |

---

## 📝 For Developers Building Apps

### JavaScript/TypeScript
```javascript
// Works automatically from localhost apps
const response = await fetch('http://localhost:5000/api/voices');
const voices = await response.json();

// With API key (if enabled)
const response = await fetch('http://localhost:5000/api/voices', {
  headers: { 'X-API-Key': 'your-key-here' }
});
```

### Python
```python
import requests

# No API key
response = requests.get('http://localhost:5000/api/voices')

# With API key
headers = {'X-API-Key': 'your-key-here'}
response = requests.get('http://localhost:5000/api/voices', headers=headers)
```

### PowerShell
```powershell
# No API key
Invoke-RestMethod http://localhost:5000/api/voices

# With API key
Invoke-RestMethod http://localhost:5000/api/voices -Headers @{"X-API-Key"="your-key"}
```

---

## 🚀 Zero-Config Security Summary

**The Good News**: You don't need to do anything! The server is now secure by default for local development:

1. ✅ **CORS**: Restricted to localhost automatically
2. ✅ **Input Validation**: All dangerous inputs blocked
3. ✅ **Command Safety**: PowerShell injection fixed
4. ✅ **Privacy**: System paths not exposed
5. ⚠️ **API Key**: Optional (off by default)

**The Result**: Developers can connect from local apps while malicious websites are blocked - all without any configuration!

---

## 📖 Need More Info?

- **Full Details**: [SECURITY_HARDENING.md](SECURITY_HARDENING.md)
- **API Key Setup**: [../.env.example](../.env.example)
- **Main README**: [../README.md](../README.md)

---

**Last Updated**: February 4, 2026
