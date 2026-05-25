#!/usr/bin/env python3
"""
Azure Speech-to-Text for macOS — Finnish voice input
Records audio → sends to Azure Speech → prints result → copies to clipboard

Usage:
  python3 azure-stt.py              # Record until silence (auto-stop)
  python3 azure-stt.py --duration 30  # Record for 30 seconds
  python3 azure-stt.py --lang fi-FI   # Finnish (default)
  python3 azure-stt.py --lang sv-SE   # Swedish
  python3 azure-stt.py --no-copy      # Don't copy to clipboard
"""

import argparse
import os
import sys
import subprocess
import tempfile
import wave
import json
from pathlib import Path

# Load .env
def load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().strip().split("\n"):
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

load_env()

AZURE_KEY = os.environ.get("AZURE_SPEECH_KEY", "")
AZURE_REGION = os.environ.get("AZURE_SPEECH_REGION", "norwayeast")

if not AZURE_KEY:
    print("Error: AZURE_SPEECH_KEY not set. Check voice-input/.env", file=sys.stderr)
    sys.exit(1)

def record_audio(output_path, duration=None, sample_rate=16000):
    """Record audio using ffmpeg with gain boost, then sox for silence detection"""
    # Step 1: Record with ffmpeg (better macOS mic support + volume boost)
    try:
        subprocess.run(["which", "ffmpeg"], capture_output=True, check=True)
        raw_path = output_path.replace(".wav", "_raw.wav")
        dur_args = ["-t", str(duration)] if duration else []
        print("🎙️  Recording... (Ctrl+C to stop)" + (f" {duration}s" if duration else " auto-stop on silence"))
        # Record with volume boost (20dB) for quiet MacBook mics
        cmd = ["ffmpeg", "-f", "avfoundation", "-i", ":1",
               "-af", "volume=20dB",
               "-ar", str(sample_rate), "-ac", "1", "-sample_fmt", "s16"] + \
              dur_args + ["-y", raw_path]
        subprocess.run(cmd, check=True)
        
        # Step 2: If no duration set, trim silence with sox
        if duration is None:
            try:
                subprocess.run(["which", "sox"], capture_output=True, check=True)
                cmd = ["sox", raw_path, output_path,
                       "silence", "1", "0.1", "1%", "1", "1.5", "1%"]
                subprocess.run(cmd, check=True)
                os.unlink(raw_path)
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        
        # Rename raw to final if no sox processing
        if raw_path != output_path:
            os.rename(raw_path, output_path)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fallback to sox
    try:
        subprocess.run(["which", "rec"], capture_output=True, check=True)
        if duration:
            cmd = ["rec", "-r", str(sample_rate), "-c", "1", "-b", "16", output_path,
                   "vol", "4", "trim", "0", str(duration)]
        else:
            cmd = ["rec", "-r", str(sample_rate), "-c", "1", "-b", "16", output_path,
                   "vol", "4", "silence", "1", "0.1", "3%", "1", "2.0", "3%"]
        print("🎙️  Recording with sox... (Ctrl+C to stop)")
        subprocess.run(cmd, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    print("Error: Need 'ffmpeg' or 'sox' for recording. Install with: brew install ffmpeg", file=sys.stderr)
    return False

def recognize_speech(audio_path, language="fi-FI"):
    """Send audio to Azure Speech API for recognition (continuous mode)"""
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError:
        print("Error: azure-cognitiveservices-speech not installed", file=sys.stderr)
        print("Run: pip install azure-cognitiveservices-speech", file=sys.stderr)
        sys.exit(1)

    speech_config = speechsdk.SpeechConfig(
        subscription=AZURE_KEY,
        region=AZURE_REGION
    )
    speech_config.speech_recognition_language = language
    # Enable dictation mode for better free-form text recognition
    speech_config.set_property(speechsdk.PropertyId.SpeechServiceResponse_PostProcessingOption, "TrueText")

    audio_config = speechsdk.audio.AudioConfig(filename=audio_path)
    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=audio_config
    )

    # Use continuous recognition for better results
    results = []
    done = False

    def handle_result(evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            results.append(evt.result.text)

    def handle_stop(evt):
        nonlocal done
        done = True

    recognizer.recognized.connect(handle_result)
    recognizer.session_stopped.connect(handle_stop)
    recognizer.canceled.connect(handle_stop)

    print("🔄 Recognizing...")
    recognizer.start_continuous_recognition()

    import time
    timeout = 30  # max 30s wait
    start = time.time()
    while not done and (time.time() - start) < timeout:
        time.sleep(0.1)

    recognizer.stop_continuous_recognition()

    if results:
        return " ".join(results)
    return None

def copy_to_clipboard(text):
    """Copy text to macOS clipboard"""
    process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    process.communicate(text.encode("utf-8"))
    return process.returncode == 0

def main():
    parser = argparse.ArgumentParser(description="Azure Speech-to-Text voice input")
    parser.add_argument("--duration", "-d", type=int, help="Recording duration in seconds")
    parser.add_argument("--lang", "-l", default="fi-FI", help="Language code (default: fi-FI)")
    parser.add_argument("--no-copy", action="store_true", help="Don't copy result to clipboard")
    args = parser.parse_args()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        if not record_audio(tmp_path, duration=args.duration):
            sys.exit(1)

        text = recognize_speech(tmp_path, language=args.lang)

        if text:
            print(f"\n✅ {text}")
            if not args.no_copy:
                if copy_to_clipboard(text):
                    print("📋 Copied to clipboard")
        else:
            print("\n❌ No speech detected")
            sys.exit(1)
    finally:
        os.unlink(tmp_path)

if __name__ == "__main__":
    main()
