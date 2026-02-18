"""Restore metadata.csv from transcription_quality_report.json"""
import json
from pathlib import Path

report_path = Path("training/make piper voice models/tts_dojo/cc_dojo/dataset/wav/transcription_quality_report.json")
meta_path = Path("training/make piper voice models/tts_dojo/cc_dojo/dataset/metadata.csv")

report = json.load(open(report_path, 'r'))

lines = []
for fname in sorted(report['files'].keys(), key=lambda x: int(x.replace('.wav', ''))):
    f = report['files'][fname]
    if f['status'] == 'accepted':
        stem = fname.replace('.wav', '')
        text = f['text_preview']
        lines.append(f'{stem}|{text}')

with open(meta_path, 'w', encoding='utf-8', newline='\n') as fout:
    fout.write('\n'.join(lines) + '\n')

print(f"Restored {len(lines)} lines to {meta_path}")
