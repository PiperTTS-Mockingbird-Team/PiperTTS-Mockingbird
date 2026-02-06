"""
Cross-platform audio playback utility for WAV files.
Handles Windows, macOS, and Linux with native system tools.
"""
import os
import sys
import shutil
import subprocess
import wave


def play_wav_sync(wav_path: str) -> None:
    """
    Play a WAV file synchronously (blocks until playback completes).
    
    Args:
        wav_path: Path to the WAV file to play
    """
    if os.name == "nt":
        # Windows: Use winsound (built-in)
        import winsound
        winsound.PlaySound(wav_path, winsound.SND_FILENAME)
    elif sys.platform == "darwin":
        # macOS: Use afplay (built-in)
        subprocess.run(["afplay", wav_path], check=False)
    else:
        # Linux: Try aplay (ALSA) then paplay (PulseAudio)
        if shutil.which("aplay"):
            subprocess.run(["aplay", "-q", wav_path], check=False)
        elif shutil.which("paplay"):
            subprocess.run(["paplay", wav_path], check=False)
        else:
            raise RuntimeError("No audio player found (install alsa-utils or pulseaudio-utils)")


def play_wav_async(wav_path: str):
    """
    Start playing a WAV file asynchronously (returns immediately).
    
    Args:
        wav_path: Path to the WAV file to play
        
    Returns:
        On Windows: None (winsound handles async internally)
        On Mac/Linux: subprocess.Popen object (can be terminated)
    """
    if os.name == "nt":
        # Windows: Use winsound async mode
        import winsound
        winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        return None
    elif sys.platform == "darwin":
        # macOS: Use afplay in background
        return subprocess.Popen(["afplay", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # Linux: Try aplay then paplay
        cmd = None
        if shutil.which("aplay"):
            cmd = ["aplay", "-q", wav_path]
        elif shutil.which("paplay"):
            cmd = ["paplay", wav_path]
        
        if cmd:
            return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            raise RuntimeError("No audio player found (install alsa-utils or pulseaudio-utils)")


def stop_playback(process=None) -> None:
    """
    Stop any currently playing audio.
    
    Args:
        process: On Mac/Linux, the subprocess.Popen object from play_wav_async()
                 On Windows, pass None
    """
    if os.name == "nt":
        # Windows: Purge winsound
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
    else:
        # Mac/Linux: Terminate the subprocess
        if process:
            try:
                process.terminate()
                process.wait(timeout=1)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass


def get_wav_duration(wav_path: str) -> float:
    """
    Get the duration of a WAV file in seconds.
    
    Args:
        wav_path: Path to the WAV file
        
    Returns:
        Duration in seconds
    """
    with wave.open(wav_path, 'rb') as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        return frames / float(rate)
