#!/usr/bin/env python3
"""
Voice Input macOS App — Menu Bar + Global Hotkey
Click menu bar icon or press Ctrl+Space to start voice input.

Usage:
  python3 voice-app.py
"""

import os
import sys
import json
import tempfile
import subprocess
import threading
import urllib.request
from pathlib import Path

import rumps
from pynput import keyboard
import Quartz

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
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
LANGUAGE = "fi-FI"


def record_audio(duration=10):
    """Record audio with ffmpeg"""
    output = tempfile.mktemp(suffix=".m4a")
    cmd = [
        "ffmpeg", "-f", "avfoundation", "-i", ":1",
        "-af", "volume=20dB",
        "-ar", "16000", "-ac", "1",
        "-t", str(duration),
        "-y", output
    ]
    result = subprocess.run(cmd, capture_output=True)
    return output if result.returncode == 0 else None


def azure_transcribe(audio_path):
    """Transcribe with Azure Speech API"""
    if not AZURE_KEY:
        return None, "Azure key not configured"

    with open(audio_path, "rb") as f:
        audio_data = f.read()

    url = f"https://{AZURE_REGION}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?language={LANGUAGE}&format=detailed"

    req = urllib.request.Request(url, data=audio_data, method="POST")
    req.add_header("Ocp-Apim-Subscription-Key", AZURE_KEY)
    req.add_header("Content-Type", "audio/m4a; codec=audio/pcm; samplerate=16000")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            if "NBest" in data and data["NBest"]:
                return data["NBest"][0].get("Display"), None
            return None, "No speech detected"
    except Exception as e:
        return None, str(e)


def deepseek_correct(text):
    """Correct text with DeepSeek"""
    if not DEEPSEEK_KEY:
        return text

    system_prompt = """Olet suomen kielen korjaaja. Käyttäjä puhuu ääneen ja puheentunnistus tekee virheitä.

Tehtäväsi:
1. Korjaa puheentunnistuksen virheet (väärät sanat, puuttuvat kirjaimet)
2. Lisää oikea välimerkitys (pisteet, pilkut, kysymysmerkit)
3. Korjaa kielioppivirheet
4. Älä muuta merkitystä tai lisää sisältöä

Palauta VAIN korjattu teksti, ei selityksiä."""

    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        "temperature": 0.1,
        "max_tokens": 2048
    }).encode()

    req = urllib.request.Request("https://api.deepseek.com/v1/chat/completions", data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {DEEPSEEK_KEY}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"].strip()
    except:
        return text


def copy_and_paste(text):
    """Copy to clipboard and simulate Cmd+V"""
    process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    process.communicate(text.encode("utf-8"))

    # Simulate Cmd+V
    cmd_v_down = Quartz.CGEventCreateKeyboardEvent(None, 0x09, True)
    cmd_v_up = Quartz.CGEventCreateKeyboardEvent(None, 0x09, False)
    Quartz.CGEventSetFlags(cmd_v_down, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventSetFlags(cmd_v_up, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, cmd_v_down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, cmd_v_up)


class VoiceInputApp(rumps.App):
    def __init__(self):
        super(VoiceInputApp, name="🎤", quit_button=None)
        self.is_recording = False
        self.hotkey_listener = None
        self._setup_hotkey()

    def _setup_hotkey(self):
        """Setup global hotkey Ctrl+Space"""
        def on_hotkey():
            if not self.is_recording:
                self.start_recording(None)

        # Run hotkey listener in background
        def run_listener():
            with keyboard.GlobalHotKeys({
                '<ctrl>+<space>': on_hotkey
            }) as h:
                h.join()

        thread = threading.Thread(target=run_listener, daemon=True)
        thread.start()

    @rumps.clicked("Start Recording")
    def start_recording(self, _):
        if self.is_recording:
            return

        self.is_recording = True
        self.title = "🔴"
        rumps.notification("Voice Input", "Recording...", "Speak now (10s max)")

        # Run in background thread
        thread = threading.Thread(target=self._process_voice)
        thread.start()

    def _process_voice(self):
        try:
            # Record
            audio_path = record_audio(duration=10)
            if not audio_path:
                rumps.alert("Error", "Recording failed")
                return

            # Transcribe
            rumps.notification("Voice Input", "Transcribing...", "")
            text, error = azure_transcribe(audio_path)

            # Cleanup
            if audio_path and os.path.exists(audio_path):
                os.unlink(audio_path)

            if not text:
                rumps.alert("Error", error or "No speech detected")
                return

            # Correct
            rumps.notification("Voice Input", "Correcting...", "")
            corrected = deepseek_correct(text)

            # Copy and paste
            copy_and_paste(corrected)
            rumps.notification("Voice Input", "Done!", corrected[:50] + "..." if len(corrected) > 50 else corrected)

        except Exception as e:
            rumps.alert("Error", str(e))
        finally:
            self.is_recording = False
            self.title = "🎤"

    @rumps.clicked("Quit")
    def quit_app(self, _):
        rumps.quit_application()


if __name__ == "__main__":
    app = VoiceInputApp()
    app.run()
