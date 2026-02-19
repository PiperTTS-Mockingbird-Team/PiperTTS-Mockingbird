import time
from youtube_transcript_api import YouTubeTranscriptApi

video_id = 'VEuqn9YDobU'
try:
    t0 = time.perf_counter()
    api = YouTubeTranscriptApi()
    fetched = api.fetch(video_id, languages=['en', 'en-GB'])
    text = ' '.join(snip.text for snip in fetched)
    elapsed = time.perf_counter() - t0
    print(f'SUCCESS: fetched {len(text)} chars in {elapsed:.2f}s')
    print('Preview:', text[:300])
except Exception as e:
    print('Error:', type(e).__name__, e)
