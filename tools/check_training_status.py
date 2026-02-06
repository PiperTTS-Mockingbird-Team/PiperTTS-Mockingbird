import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List

try:
    from src.central_log import log_event
except Exception:
    log_event = None


class TrainingState(str, Enum):
    IDLE = "idle"
    PREPROCESSING = "preprocessing"
    TRAINING = "training"


def _is_piper_line(line: str) -> bool:
    l = line.lower()
    return ("piper_train" in l) and ("grep" not in l)


def classify_processes(ps_aux_lines: Iterable[str]) -> TrainingState:
    lines = [line.strip() for line in ps_aux_lines if line.strip()]
    lines_lower = [line.lower() for line in lines]

    is_any_piper = any("piper_train" in line for line in lines_lower)
    is_preprocessing = any("piper_train.preprocess" in line for line in lines_lower)

    if is_preprocessing:
        return TrainingState.PREPROCESSING
    if is_any_piper:
        return TrainingState.TRAINING
    return TrainingState.IDLE


def extract_piper_process_lines(ps_aux_lines: Iterable[str], *, limit: int = 10) -> List[str]:
    piper_lines = [line for line in ps_aux_lines if _is_piper_line(line)]
    return piper_lines[:limit]

def check_training():
    container_name = "textymcspeechy-piper"
    print(f"--- Piper Training Monitor ---")
    
    try:
        # Check if container is running
        check_container = subprocess.run(["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"], capture_output=True, text=True)
        
        if container_name not in check_container.stdout:
            print(f"Status: Container '{container_name}' is NOT running.")
            return

        # Check for python processes (training/preprocess)
        check_proc = subprocess.run(
            ["docker", "exec", container_name, "ps", "aux"],
            capture_output=True,
            text=True,
        )

        proc_lines = check_proc.stdout.splitlines()
        state = classify_processes(proc_lines)
        piper_lines = extract_piper_process_lines(proc_lines)
        
        if state == TrainingState.TRAINING:
            print("Status: TRAINING IS RUNNING ✅")
            print("Action: Training is currently active.")
            if piper_lines:
                print("\n--- Piper Processes ---")
                for line in piper_lines[:10]:
                    print(line)
        elif state == TrainingState.PREPROCESSING:
            print("Status: PREPROCESSING IS RUNNING ⌛")
            if piper_lines:
                print("\n--- Piper Processes ---")
                for line in piper_lines[:10]:
                    print(line)
        else:
            print("Status: Container is idle (No training/preprocessing detected).")

        if log_event is not None:
            log_event(
                "training_status",
                fields={
                    "container": container_name,
                    "state": state.value,
                },
            )

        # Check for latest checkpoint activity
        print("\n--- Recent Activity ---")
        find_logs = subprocess.run(["docker", "exec", container_name, "bash", "-c", "find /app/tts_dojo -name 'last.ckpt' -o -name 'dataset.jsonl'"], capture_output=True, text=True)
        if find_logs.stdout:
            print("Active Files found:")
            print(find_logs.stdout.strip())
        else:
            print("No active training files (checkpoints/datasets) detected in dojos.")

    except Exception as e:
        print(f"Error checking status: {e}")

if __name__ == "__main__":
    check_training()
    input("\nPress Enter to exit...")
