import json

report_path = r"training\make piper voice models\tts_dojo\cc_dojo\dataset\wav\transcription_quality_report.json"

with open(report_path, 'r') as f:
    report = json.load(f)

print("\n" + "="*60)
print("FILTERED FILES:")
print("="*60)

filtered_files = [(name, data) for name, data in report['files'].items() if data['status'] == 'filtered']

if filtered_files:
    for filename, data in filtered_files:
        print(f"\nFile: {filename}")
        print(f"Reason: {data['reason']}")
        print(f"Metrics:")
        print(f"  no_speech_prob: {data['metrics']['no_speech_prob']} (threshold: >0.6)")
        print(f"  avg_logprob: {data['metrics']['avg_logprob']} (threshold: <-1.0)")
        print(f"  compression: {data['metrics']['compression_ratio']} (threshold: >2.4)")
        print(f"Text preview: {data.get('text_preview', 'N/A')}")
else:
    print("No files were filtered")

print("\n" + "="*60)
print("SUMMARY:")
print("="*60)
print(f"Total: {report['summary']['total_processed']}")
print(f"Accepted: {report['summary']['accepted']}")
print(f"Filtered: {report['summary']['filtered']}")
print(f"Pass rate: {report['summary']['pass_rate']}%")
print("="*60 + "\n")
