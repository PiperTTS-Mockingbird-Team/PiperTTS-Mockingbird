# Security Hardening Summary

## What Changed (February 4, 2026)

Your Piper TTS server now has **invisible, automatic security** that protects against common attacks while remaining completely plug-and-play for developers.

---

## 🔒 Security Features Added

### 1. **Optional API Key Authentication** (Lines 110-130 in piper_server.py)
- **What it does**: Allows you to lock down the server with a custom password.
- **How it works**: Set the `PIPER_API_KEY` environment variable. If set, the server rejects any request missing the `X-API-Key` header.
- **Impact**: Left empty by default for a "zero-config" experience on your own machine.
- **Protection**: If you ever expose the server to a network, this prevents unauthorized use.

### 2. **Restricted CORS Origins** (Lines 149-169 in piper_server.py)
- **What it does**: Only allows connections from localhost development ports
- **How it works**: Blocks cross-origin requests from non-local websites
- **Impact**: Developers can still connect from local apps (React, Vite, Next.js, etc.)
- **Protection**: Stops "malicious tab" attacks where evil websites control your server

### 3. **Input Validation on All Voice Endpoints** (11 endpoints updated)
- **What it does**: Sanitizes voice names to prevent path traversal and injection
- **How it works**: Validates all voice/dojo parameters against strict regex pattern
- **Impact**: Invisible to legitimate users; rejects malicious input
- **Protection**: Prevents attackers from deleting arbitrary files or executing commands

### 4. **PowerShell Command Injection Fixed** (training_manager.py)
- **What it does**: Uses safe parameter passing instead of string interpolation
- **How it works**: PowerShell `-File` with argument list instead of `-Command` with inline strings
- **Impact**: No functionality change; commands work exactly the same
- **Protection**: Prevents code execution via crafted voice names

### 5. **Privacy-First Path Reporting** (Line 589 in training_manager.py)
- **What it does**: Returns relative paths instead of absolute system paths
- **How it works**: `training/tts_dojo/voice_dojo` instead of `/home/user/projects/piper_tts_server/training/...`
- **Impact**: API responses don't leak your username or directory structure
- **Protection**: Prevents information disclosure for reconnaissance attacks

---

## 🎯 Attack Vectors Blocked

| Attack Type | Before | After |
|------------|--------|-------|
| **Cross-Site Request Forgery (CSRF)** | ❌ Any website could control server | ✅ Only localhost apps allowed |
| **Path Traversal** | ❌ Could delete system files | ✅ Strict validation blocks `../` patterns |
| **Command Injection** | ❌ PowerShell code execution possible | ✅ Safe parameter passing prevents injection |
| **Information Disclosure** | ❌ Full system paths exposed | ✅ Relative paths only |
| **Unauthorized Access** | ⚠️ No authentication | ✅ Optional API key (when enabled) |

---

## 📋 For Developers: How to Connect

### Default Mode (No API Key)
```javascript
// Just connect normally - works out of the box
fetch('http://localhost:5000/api/voices')
  .then(r => r.json())
  .then(data => console.log(data));
```

### With API Key Enabled
```javascript
// Option 1: Header
fetch('http://localhost:5000/api/voices', {
  headers: { 'X-API-Key': 'your-key-here' }
});

// Option 2: URL parameter
fetch('http://localhost:5000/api/voices?api_key=your-key-here');
```

### Allowed Origins
The following localhost ports work automatically:
- `http://localhost:3000` (React default)
- `http://localhost:5173` (Vite default)
- `http://localhost:8080` (Common dev server)
- Plus `127.0.0.1` equivalents

---

## ⚙️ How to Enable API Key (Optional)

**By default, the server is in "Zero-Config" mode with no API key required for local use.**

This provides the most seamless experience for local developers and Home Assistant users. The server is still protected from external internet attacks by binding to `127.0.0.1` and restricting CORS origins.

### To Enable an API Key:

1. Set the environment variable: `PIPER_API_KEY=your-custom-key`
2. Update any connecting extensions or apps to send this key in the `X-API-Key` header.
3. Restart the server.

**Why use an API key?**
- Adds an extra layer of defense-in-depth.
- Required if you plan to use a reverse proxy to expose the server to your local network.

**Generate a custom random key:**
```powershell
# PowerShell
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
```

---

## ✅ What Stayed the Same

- **Zero configuration required** - Works immediately without setup
- **No passwords for casual use** - API key is optional
- **Same API endpoints** - No breaking changes
- **Same functionality** - Everything works exactly as before
- **Developer-friendly** - Local apps connect seamlessly

---

## 🧪 Testing Your Setup

```powershell
# Test basic connection (should work)
Invoke-RestMethod http://localhost:5000/api/voices

# Test with API key (if enabled)
Invoke-RestMethod -Uri http://localhost:5000/api/voices -Headers @{"X-API-Key"="your-key"}

# Test CORS (should work from localhost:3000)
# Open your React/Vite app and make API calls

# Test validation (should reject)
Invoke-RestMethod http://localhost:5000/api/training/status?voice="../../../etc/passwd"
# Response: 400 Bad Request - Invalid voice name
```

---

## 📚 Related Files

- [piper_server.py](../src/piper_server.py) - API key & CORS middleware
- [training_manager.py](../src/training_manager.py) - Command injection fixes
- [common_utils.py](../src/common_utils.py) - Input validation logic
- [.env.example](../.env.example) - API key configuration template

---

## 🔐 Security Posture

**Before**: Vulnerable to cross-site attacks, command injection, path traversal
**After**: Hardened against common web attacks while maintaining ease of use

**Threat Model**: Designed for local development use where:
- You control the machine
- Developers connect from localhost
- Malicious websites might try to abuse the API
- Users might accidentally input dangerous characters

**Not Designed For**:
- Public internet exposure (use reverse proxy with proper auth)
- Multi-tenant environments (no user isolation)
- High-security production deployments (consider additional hardening)

---

**Last Updated**: February 4, 2026  
**Applies to**: PiperTTS Mockingbird v1.0.0+
