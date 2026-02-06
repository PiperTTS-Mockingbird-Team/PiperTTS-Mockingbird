# Mockingbird Testing Guide

## Quick Start Testing

### 1. Reload the Extension
1. Open Chrome → Extensions (`chrome://extensions/`)
2. Find Mockingbird
3. Click the **Reload** button (🔄)

### 2. Check Server Status
1. Make sure Piper server is running on `http://localhost:5002`
2. Open Mockingbird side panel
3. Look for: `✓ Server connected (X voices)`

---

## Feature Testing

### ✅ Audio Caching Test

**Test**: Read the same text twice

1. Open any webpage
2. Select some text and click "Read"
3. Wait for it to finish
4. Select the SAME text again and click "Read"
5. **Expected**: Second playback starts almost instantly

**Verify**:
- Open DevTools Console (F12)
- Look for: `[Cache] HIT: <text>`
- Should see message on second read

---

### ✅ Server Health Check Test

**Test**: Server online/offline detection

1. Make sure server is running
2. Check side panel → Should show: `✓ Server connected`
3. Stop the Piper server
4. Wait 10-15 seconds
5. **Expected**: Status changes to `✗ Server offline`
6. Try to read → Should show error notification
7. Restart server
8. **Expected**: Green notification: `✓ Server connection restored`

**Verify**:
- Status indicator changes color (green → red → green)
- Error notification appears when reading with server offline
- Success notification appears when server comes back

---

### ✅ Retry Logic Test

**Test**: Automatic recovery from transient failures

1. Start reading a long article
2. Quickly stop/start the Piper server during reading
3. **Expected**: Extension retries and continues reading
4. Check console for: `[Retry] Attempt X failed, retrying...`

**Verify**:
- No permanent failure
- Reading continues after retry
- Up to 3 retry attempts visible in console

---

### ✅ Sentence Batching Test

**Test**: Short sentences are combined

1. Find text with very short sentences like:
   ```
   Hello. Hi. Yes. Okay. Great. Thanks.
   ```
2. Click "Read entire page"
3. Open Console (F12)
4. Look for: `Split into X sentences, batched to Y`
5. **Expected**: Y should be less than X

**Example Output**:
```
Split into 12 sentences, batched to 5
```

**Verify**:
- Fewer API calls (check Network tab)
- Smoother audio playback
- Console shows batching happened

---

### ✅ Notification Types Test

**Test**: Different notification colors

1. **Error (Red)**:
   - Stop Piper server
   - Try to read text
   - Should see red notification: `⚠ Cannot reach Piper server`

2. **Success (Green)**:
   - Restart server (while extension is open)
   - Should see green notification: `✓ Server connection restored`

3. **Info (Purple)**:
   - Normal operation notifications
   - Should use purple gradient

**Verify**:
- Notifications appear in top-right corner
- Colors match type (red=error, green=success, purple=info)
- Auto-dismiss after 3-5 seconds

---

## Console Messages to Look For

### Cache System:
```
[Cache] Initialized
[Cache] STORED: <text preview>
[Cache] HIT: <text preview>
[Cache] Cleared X expired entries
```

### Health Checks:
```
[Health] Server check failed: <error>
[Mockingbird] Service worker loaded with audio cache
```

### Retry Logic:
```
[Retry] Attempt 1 failed, retrying in 1000ms...
[Retry] Attempt 2 failed, retrying in 2000ms...
```

### Batching:
```
Split into 15 sentences, batched to 8
```

---

## Performance Verification

### Check Cache Size:
1. Open DevTools (F12)
2. Application tab → IndexedDB
3. Expand `MockingbirdCache` → `audioCache`
4. View stored entries and timestamps

### Check Network Activity:
1. Open DevTools → Network tab
2. Filter by: `/api/tts`
3. Read same text twice
4. **Expected**: 
   - First read: 1 API call per sentence
   - Second read: 0 API calls (cache hit)

### Measure Speed:
1. **First read** of paragraph: Note time
2. **Second read** of same paragraph: Note time
3. **Expected**: 3-5x faster on second read

---

## Common Issues & Solutions

### Cache not working?
- **Check**: DevTools → Application → IndexedDB
- **Fix**: Clear cache and reload extension

### Status stuck on "Checking..."?
- **Check**: Is server running on correct port?
- **Fix**: Verify `http://localhost:5002/health` works in browser

### No notifications appearing?
- **Check**: Content script loaded? (Console should show `[Mockingbird] Content script loaded`)
- **Fix**: Reload the page you're testing on

### Batching not happening?
- **Check**: Console for "Split into X, batched to Y"
- **Fix**: Make sure sentences are short (< 30 chars)

---

## Advanced Testing

### Test Cache Expiry:
1. Read some text (gets cached)
2. Open DevTools → Application → IndexedDB → `MockingbirdCache`
3. Find entry → Edit timestamp to 8 days ago
4. Read same text again
5. **Expected**: New API call (cache expired)

### Test Multiple Voices:
1. Read text with Voice A
2. Switch to Voice B in settings
3. Read same text
4. **Expected**: New API call (different cache key per voice)

### Test Long Documents:
1. Open a long article (1000+ words)
2. Click "Read entire page"
3. Monitor Network tab for parallel requests
4. Check console for batching results

---

## Success Criteria

### ✅ All Features Working:
- [x] Cache hits on repeated text
- [x] Health check status updates
- [x] Retry logic recovers from failures
- [x] Sentences batched appropriately
- [x] Notifications show correct colors
- [x] Side panel shows connection status

### ✅ Performance Improvements:
- [x] Faster playback for cached content
- [x] Fewer API calls overall
- [x] Smooth operation even with network issues

### ✅ User Experience:
- [x] Clear error messages
- [x] Status always visible
- [x] No silent failures
- [x] Automatic recovery

---

## Reporting Issues

If something doesn't work:

1. **Check Console**: Look for error messages
2. **Check Network**: See if API calls succeed
3. **Check Cache**: Verify IndexedDB is accessible
4. **Note**: What you did, what happened, what you expected

---

**Testing Version**: 1.1.0  
**Last Updated**: January 29, 2026
