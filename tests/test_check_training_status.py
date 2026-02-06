from __future__ import annotations

import sys
import os

# Add tools directory to path to import check_training_status
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
from check_training_status import TrainingState, classify_processes


def test_classify_processes_idle():
    state = classify_processes(
        [
            "root 1 0.0 0.0 /bin/bash -lc echo hi",
            "root 2 0.0 0.0 sleep 999",
        ]
    )
    assert state == TrainingState.IDLE


def test_classify_processes_training_detects_python_module():
    state = classify_processes(
        [
            "root 10 0.0 0.0 /bin/bash ./utils/piper_training.sh",
            "root 11 1.0 2.0 python3 -m piper_train --dataset-dir /app/tts_dojo/x/training_folder/ --accelerator gpu",
        ]
    )
    assert state == TrainingState.TRAINING


def test_classify_processes_preprocess_detects_module():
    state = classify_processes(
        [
            "root 11 1.0 2.0 python3 -m piper_train.preprocess --dataset-dir /app/tts_dojo/x/training_folder/",
        ]
    )
    assert state == TrainingState.PREPROCESSING
