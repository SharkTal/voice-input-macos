#!/usr/bin/env python3
"""
Voice Input macOS App — Menu Bar + Global Hotkey
Click menu bar icon or press Cmd+↑ to start/stop voice input.

Usage:
  python3 voice-app.py

Hotkey: Cmd+↑ (press to start, press again to stop)
"""

import os
import sys
import json
import tempfile
import subprocess
import threading
import urllib.request
import wave
import time
from pathlib import Path

import rumps
import Quartz
import numpy as np
import sounddevice as sd

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
LANGUAGE = os.environ.get("VOICE_LANGUAGE", "fi-FI")
MAX_DURATION = int(os.environ.get("RECORD_DURATION", "60"))  # max 60s safety limit

# Audio settings
SAMPLE_RATE = 16000
CHANNELS = 1

# Global stop flag for toggle recording
_stop_recording = threading.Event()


def record_audio_toggle():
    """Record audio until stop signal or MAX_DURATION. Returns WAV path."""
    global _stop_recording
    _stop_recording.clear()

    frames = []
    block_duration = 0.5  # record in 0.5s chunks
    block_samples = int(block_duration * SAMPLE_RATE)

    def callback(indata, frames_count, time_info, status):
        frames.append(indata.copy())

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16',
                           blocksize=block_samples, callback=callback):
            elapsed = 0
            while not _stop_recording.is_set() and elapsed < MAX_DURATION:
                time.sleep(0.1)
                elapsed += 0.1

        if not frames:
            return None

        # Concatenate all frames
        recording = np.concatenate(frames, axis=0)

        # Auto-gain: boost quiet recordings
        rms = np.sqrt(np.mean(recording.astype(float)**2))
        if rms > 0 and rms < 300:
            gain = min(3000.0 / rms, 30.0)
            recording = np.clip(recording.astype(float) * gain, -32768, 32767).astype('int16')

        # Save as WAV
        output = tempfile.mktemp(suffix=".wav")
        with wave.open(output, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(recording.tobytes())

        return output
    except Exception as e:
        print(f"Recording error: {e}")
        return None


def azure_transcribe(audio_path):
    """Transcribe with Azure Speech SDK"""
    if not AZURE_KEY:
        return None, "Azure key not configured"

    try:
        import azure.cognitiveservices.speech as speechsdk

        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_recognition_language = LANGUAGE

        audio_config = speechsdk.audio.AudioConfig(filename=audio_path)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

        result = recognizer.recognize_once_async().get()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            return result.text, None
        elif result.reason == speechsdk.ResultReason.NoMatch:
            return None, "No speech detected — try speaking louder or closer to mic"
        elif result.reason == speechsdk.ResultReason.Canceled:
            details = result.cancellation_details
            return None, f"Canceled: {details.reason}. {details.error_details}"
        else:
            return None, f"Unknown error: {result.reason}"

    except Exception as e:
        return None, str(e)


def deepseek_correct(text):
    """Correct text with DeepSeek"""
    if not DEEPSEEK_KEY:
        return text

    lang_map = {
        "fi-FI": "suomen kielen",
        "zh-CN": "中文",
        "sv-SE": "svenska",
        "en-US": "English",
    }
    lang_name = lang_map.get(LANGUAGE, "text")

    system_prompt = f"""Olet {lang_name} korjaaja. Käyttäjä puhuu ääneen ja puheentunnistus tekee virheitä.

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
        "max_tokens": 4096
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


def has_accessibility():
    """Check if we have accessibility permissions"""
    return Quartz.AXIsProcessTrusted()


class VoiceInputApp(rumps.App):
    def __init__(self):
        rumps.App.__init__(self, "🎤", quit_button=None)
        self.is_recording = False
        self.hotkey_active = False
        self.menu = [
            "🎙️ Start Recording",
            "⏹️ Stop Recording",
            None,  # separator
            "⚙️ Accessibility Settings",
            "Quit"
        ]
        self._setup_hotkey()

    def _setup_hotkey(self):
        """Setup global hotkey Cmd+Up (graceful if no permission)"""
        try:
            from pynput import keyboard

            if not has_accessibility():
                print("⚠️  No accessibility permission — global hotkey disabled")
                print("   Enable at: System Settings → Privacy & Security → Accessibility")
                print("   You can still use the menu bar icon to record.")
                return

            def on_hotkey():
                if self.is_recording:
                    self.stop_recording(None)
                else:
                    self.start_recording(None)

            def run_listener():
                with keyboard.GlobalHotKeys({
                    '<cmd>+<up>': on_hotkey
                }) as h:
                    h.join()

            thread = threading.Thread(target=run_listener, daemon=True)
            thread.start()
            self.hotkey_active = True
            print("✅ Global hotkey Cmd+↑ active (toggle: press to start/stop)")

        except Exception as e:
            print(f"⚠️  Hotkey setup failed: {e}")
            print("   Use menu bar icon instead.")

    @rumps.clicked("🎙️ Start Recording")
    def start_recording(self, _):
        if self.is_recording:
            return

        self.is_recording = True
        self.title = "🔴"
        rumps.notification("Voice Input", "Recording...", "Press Cmd+↑ or click Stop when done")

        thread = threading.Thread(target=self._process_voice)
        thread.start()

    @rumps.clicked("⏹️ Stop Recording")
    def stop_recording(self, _):
        if not self.is_recording:
            return
        _stop_recording.set()
        rumps.notification("Voice Input", "Stopping...", "Processing your speech")

    def _process_voice(self):
        try:
            # Record until stop or max duration
            audio_path = record_audio_toggle()
            if not audio_path:
                rumps.notification("Voice Input", "Error", "Recording failed")
                return

            # Transcribe
            rumps.notification("Voice Input", "Transcribing...", "")
            text, error = azure_transcribe(audio_path)

            # Cleanup
            if audio_path and os.path.exists(audio_path):
                os.unlink(audio_path)

            if not text:
                rumps.notification("Voice Input", "No speech", error or "Try speaking louder")
                return

            # Correct
            rumps.notification("Voice Input", "Correcting...", "")
            corrected = deepseek_correct(text)

            # Copy and paste
            copy_and_paste(corrected)
            preview = corrected[:50] + "..." if len(corrected) > 50 else corrected
            rumps.notification("Voice Input", "Done!", preview)

        except Exception as e:
            rumps.notification("Voice Input", "Error", str(e))
        finally:
            self.is_recording = False
            self.title = "🎤"

    @rumps.clicked("⚙️ Accessibility Settings")
    def open_accessibility(self, _):
        subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])

    @rumps.clicked("Quit")
    def quit_app(self, _):
        rumps.quit_application()


if __name__ == "__main__":
    app = VoiceInputApp()
    app.run()
