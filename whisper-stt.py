#!/usr/bin/env python3
"""
Whisper.cpp Speech-to-Text — Offline Finnish voice input
Records audio → runs whisper-cpp locally → prints result → copies to clipboard

Usage:
  python3 whisper-stt.py              # Record until silence (auto-stop)
  python3 whisper-stt.py --duration 30  # Record for 30 seconds  
  python3 whisper-stt.py --lang fi     # Finnish (default)
  python3 whisper-stt.py --model small # Use small model (faster, less accurate)
"""

import argparse
import os
import sys
import subprocess
import tempfile
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"

def get_model(model_size="medium"):
    """Find or download whisper model"""
    model_path = MODELS_DIR / f"ggml-{model_size}.bin"
    if model_path.exists():
        return str(model_path)
    print(f"Model {model_path} not found.", file=sys.stderr)
    print(f"Download from: https://huggingface.co/ggerganov/whisper.cpp/tree/main", file=sys.stderr)
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

def whisper_transcribe(audio_path, model_path, language="fi"):
    """Run whisper-cpp on audio file"""
    # Convert to 16kHz WAV if needed
    wav_path = audio_path
    if not audio_path.endswith(".wav"):
        wav_path = audio_path.rsplit(".", 1)[0] + "_16k.wav"
        subprocess.run(["ffmpeg", "-y", "-i", audio_path,
                       "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", wav_path],
                      capture_output=True, check=True)

    cmd = ["whisper-cli", "-m", model_path, "-l", language, "-f", wav_path, "--no-timestamps"]
    print("🔄 Transcribing with Whisper (offline)...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        # whisper-cpp outputs the text, clean it up
        text = result.stdout.strip()
        # Remove empty lines and the header whisper sometimes adds
        lines = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith("[")]
        return " ".join(lines) if lines else None
    else:
        print(f"Whisper error: {result.stderr}", file=sys.stderr)
        return None

def copy_to_clipboard(text):
    process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    process.communicate(text.encode("utf-8"))
    return process.returncode == 0

def main():
    parser = argparse.ArgumentParser(description="Whisper.cpp offline voice input")
    parser.add_argument("--duration", "-d", type=int, help="Recording duration in seconds")
    parser.add_argument("--lang", "-l", default="fi", help="Language code (default: fi)")
    parser.add_argument("--model", "-m", default="medium", 
                       choices=["tiny", "base", "small", "medium", "large"],
                       help="Model size (default: medium)")
    args = parser.parse_args()

    model_path = get_model(args.model)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        if not record_audio(tmp_path, duration=args.duration):
            sys.exit(1)

        text = whisper_transcribe(tmp_path, model_path, language=args.lang)

        if text:
            print(f"\n✅ {text}")
            if copy_to_clipboard(text):
                print("📋 Copied to clipboard")
        else:
            print("\n❌ No speech detected")
            sys.exit(1)
    finally:
        os.unlink(tmp_path)

if __name__ == "__main__":
    main()
