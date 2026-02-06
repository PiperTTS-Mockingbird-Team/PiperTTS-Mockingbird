# Text Chunking Guide

## Overview

The server automatically handles long texts by splitting them into chunks, processing each chunk, and seamlessly concatenating the audio. You don't need to do anything special - just send your text!

## How It Works

### Automatic Chunking
- **Trigger**: Texts over 5,000 characters are automatically chunked
- **Method**: Splits at sentence boundaries (periods, question marks, exclamation points)
- **Processing**: Each chunk is synthesized separately
- **Output**: Audio chunks are concatenated into a single WAV file

### Smart Splitting
The chunking algorithm:
1. Splits text at sentence endings (`.`, `!`, `?`)
2. Keeps sentences together (won't split mid-sentence)
3. Aims for ~5,000 character chunks
4. Falls back to hard splits if no sentence boundaries found

## Configuration

### Chunk Size
Control how large each chunk is:
```bash
export PIPER_CHUNK_SIZE=5000  # Default: 5,000 chars
```

**Smaller chunks** (3,000):
- ✅ Less memory per chunk
- ✅ Better for low-memory systems
- ⚠️ More chunks = more processing time

**Larger chunks** (10,000):
- ✅ Fewer chunks = faster processing
- ✅ Less audio concatenation overhead
- ⚠️ More memory per chunk

### Maximum Text Length
Safety limit to prevent abuse:
```bash
export PIPER_MAX_TEXT_LENGTH=100000  # Default: 100K chars
```

This is just a safety limit. Most texts will be automatically chunked well before this.

## Examples

### Example 1: Short Text (No Chunking)
```json
{
  "text": "Hello world! This is a short message.",
  "voice_model": "en_US-ryan-high.onnx"
}
```
- **Chunks**: 1 (no chunking needed)
- **Processing**: Direct synthesis

### Example 2: Medium Text (Automatic Chunking)
```json
{
  "text": "This is a longer document with multiple paragraphs... (6,000 chars)",
  "voice_model": "en_US-ryan-high.onnx"
}
```
- **Chunks**: 2 (split at ~5K chars)
- **Processing**: Synthesize → Concatenate
- **Log**: "Split text into 2 chunks (6000 chars total)"

### Example 3: Very Long Text
```json
{
  "text": "An entire article or book chapter... (50,000 chars)",
  "voice_model": "en_US-ryan-high.onnx"
}
```
- **Chunks**: 10 (split at ~5K each)
- **Processing**: Synthesize 10 chunks → Concatenate
- **Logs**: Shows progress for each chunk

## Monitoring

### Server Logs
Watch for chunking activity:
```
INFO: Split text into 3 chunks (15234 chars total)
INFO: Processing chunk 1/3 (5123 chars)
INFO: Processing chunk 2/3 (5098 chars)
INFO: Processing chunk 3/3 (5013 chars)
INFO: Concatenating 3 audio chunks
```

### Client Detection
The client receives the final concatenated audio - no indication of chunking.

## Performance Tips

### For Speed
```bash
export PIPER_CHUNK_SIZE=10000  # Bigger chunks = fewer pieces
```

### For Memory
```bash
export PIPER_CHUNK_SIZE=3000   # Smaller chunks = less memory
```

### For Quality
- Default 5,000 works great for most cases
- Chunking at sentence boundaries prevents awkward pauses
- Audio concatenation is seamless (same sample rate, format)

## Edge Cases

### No Sentence Boundaries
If text has no periods/punctuation:
- Falls back to hard 5,000-char splits
- May split mid-word as last resort

### Mixed Languages
- Chunking works with any language
- Splits on punctuation marks
- Non-Latin scripts supported

### Very Long Sentences
If a single sentence exceeds chunk size:
- That sentence goes in its own chunk
- Next sentences continue in following chunks

## Troubleshooting

### "Text too long" Error
You exceeded 100K characters:
```bash
# Increase limit (use carefully)
export PIPER_MAX_TEXT_LENGTH=200000
```

### Slow Processing
Too many chunks:
```bash
# Increase chunk size
export PIPER_CHUNK_SIZE=10000
```

### Memory Issues
Chunks too large:
```bash
# Decrease chunk size
export PIPER_CHUNK_SIZE=3000
```

### Audio Quality Issues
If you hear breaks between chunks:
- This shouldn't happen - audio is seamlessly concatenated
- Check logs for errors during concatenation
- Ensure all chunks use the same voice/model

## API Behavior

### Request
```bash
curl -X POST http://localhost:8786/api/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Very long text here... (10000+ chars)",
    "voice_model": "en_US-ryan-high.onnx"
  }'
```

### Response
- Returns single WAV file
- No indication of chunking
- Same format as non-chunked requests

### Streaming
- Chunking works with streaming endpoints
- Each chunk is processed and sent sequentially
- Client sees continuous audio stream

## Best Practices

1. **Don't Pre-chunk**: Let the server handle it automatically
2. **Use Natural Text**: Proper punctuation helps chunking work better
3. **Monitor Logs**: Watch chunk processing for performance insights
4. **Tune for Your System**: Adjust `CHUNK_SIZE` based on memory/speed needs
5. **Test Long Texts**: Verify your use case works with expected text lengths

## Technical Details

### WAV Concatenation
- Reads parameters from first WAV chunk
- Extracts raw audio frames from each chunk
- Writes concatenated frames with consistent headers
- Preserves sample rate, bit depth, channels

### Memory Management
- Processes one chunk at a time
- Previous chunks can be garbage collected
- Only final concatenated audio held in memory
- Efficient for very long texts

### Sentence Splitting Regex
```python
re.split(r'([.!?]+[\s]+)', text)
```
Splits on: `. `, `! `, `? `, `... `, etc.

## See Also

- [MEMORY_OPTIMIZATION.md](MEMORY_OPTIMIZATION.md) - Memory tuning guide
- [MEMORY_SETTINGS.md](MEMORY_SETTINGS.md) - Quick settings reference
