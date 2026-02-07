"""Check whether training is active and which dojo/voice it is for.

Primary source of truth: the running PiperTTS Mockingbird server API:
  GET /api/training/active

Fallback: inspect the Docker container process list for piper_train commands.

This is intentionally dependency-free (stdlib only) so it can be run as a VS Code task.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_BASE_URL = "http://127.0.0.1:5002"
DEFAULT_CONTAINER = "textymcspeechy-piper"

# Compile regexes once (module import time) for faster repeated use.
_VOICE_PATTERNS = (
    # e.g. /app/tts_dojo/<voice>_dojo/...
    re.compile(r"/app/tts_dojo/(?P<voice>[^/\s]+)_dojo\b"),
    # e.g. tts_dojo/<voice>_dojo/...
    re.compile(r"\btts_dojo/(?P<voice>[^/\s]+)_dojo\b"),
)


def _http_get_json(url: str, timeout_s: float = 1.5) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = resp.read().decode("utf-8", errors="replace")
    return json.loads(data)


def _parse_active_from_api(payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
    voices = payload.get("voices")
    if not isinstance(voices, list):
        voices = []
    voices = [str(v) for v in voices if v]
    active = bool(payload.get("active")) or bool(voices)
    return active, voices


def _extract_voice_candidates_from_ps(lines: List[str]) -> List[str]:
    voices: List[str] = []
    for line in lines:
        l = line.strip()
        if not l:
            continue
        ll = l.lower()
        if "piper_train" not in ll:
            continue
        for pat in _VOICE_PATTERNS:
            m = pat.search(l)
            if m:
                voices.append(m.group("voice"))
    # de-dupe preserving order
    out: List[str] = []
    seen = set()
    for v in voices:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _docker_ps_aux(container: str) -> Optional[List[str]]:
    """Return process lines from the training container (best-effort).

    Optimized for speed:
    - Avoid an extra `docker ps` call. If the container isn't running, `docker exec`
      will fail quickly.
    - Prefer a filtered process listing to reduce output size.
    """

    try:
        # Fast path: only return piper-related lines (much less output than full ps).
        # Use `sh -lc` for broad compatibility.
        fast = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "sh",
                "-lc",
                "ps aux | grep -i piper_train | grep -v grep | head -n 25",
            ],
            capture_output=True,
            text=True,
        )
        if fast.returncode == 0:
            lines = (fast.stdout or "").splitlines()
            # If grep finds nothing, it will typically exit 1; treat that separately below.
            if lines:
                return lines

        # Fallback: full listing for environments where the fast pipeline isn't available.
        full = subprocess.run(
            ["docker", "exec", container, "ps", "aux"],
            capture_output=True,
            text=True,
        )
        if full.returncode != 0:
            return None
        return (full.stdout or "").splitlines()
    except Exception:
        return None


def check_active_training(base_url: str = DEFAULT_BASE_URL, container: str = DEFAULT_CONTAINER) -> Dict[str, Any]:
    # 1) Preferred: ask the running server (it already knows which dojos are active)
    api_url = base_url.rstrip("/") + "/api/training/active"
    try:
        # Local server should respond quickly; keep this short so the tool feels instant.
        payload = _http_get_json(api_url, timeout_s=0.75)
        active, voices = _parse_active_from_api(payload)
        return {
            "source": "api",
            "api_url": api_url,
            "active": active,
            "voices": voices,
            "dojos": [f"{v}_dojo" for v in voices],
        }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        pass

    # 2) Fallback: inspect docker container processes and infer voice from paths
    ps_lines = _docker_ps_aux(container)
    if ps_lines is None:
        return {
            "source": "none",
            "active": False,
            "voices": [],
            "dojos": [],
            "detail": "Server API not reachable and Docker container not running/accessible.",
        }

    voices = _extract_voice_candidates_from_ps(ps_lines)
    active = bool(voices) or any("piper_train" in (l or "").lower() for l in ps_lines)
    return {
        "source": "docker",
        "container": container,
        "active": active,
        "voices": voices,
        "dojos": [f"{v}_dojo" for v in voices],
    }


def main() -> int:
    result = check_active_training()

    # Human-friendly output for task runner
    print("--- Active Training Check ---")
    print(f"Source: {result.get('source')}")
    print(f"Active: {bool(result.get('active'))}")

    voices = result.get("voices") or []
    if voices:
        print("Voices:")
        for v in voices:
            print(f"- {v} (dojo: {v}_dojo)")
    else:
        detail = result.get("detail")
        if detail:
            print(detail)

    # Also emit a compact JSON line (useful for future scripting)
    print("\nJSON:")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
