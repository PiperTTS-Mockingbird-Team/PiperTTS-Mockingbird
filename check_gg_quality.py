import json
r = json.load(open('training/make piper voice models/tts_dojo/gg_dojo/dataset/wav/transcription_quality_report.json'))
print(f"Total files: {r['total_files']}")
print(f"Summary: {json.dumps(r.get('summary', {}), indent=2)}")
filtered = [(f, d) for f, d in r['files'].items() if d['status'] == 'filtered']
print(f"Filtered out: {len(filtered)}")
for f, d in filtered:
    print(f"  {f}: {d['reason']} | metrics={d.get('metrics', {})}")
accepted = [(f, d) for f, d in r['files'].items() if d['status'] == 'accepted']
print(f"Accepted: {len(accepted)}")
