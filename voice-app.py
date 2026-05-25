#!/usr/bin/env python3
"""
Voice Input macOS App — Menu Bar + Global Hotkey + HTTP Trigger
Click menu bar icon, press Cmd+↑, or curl localhost:52777 to start/stop.

Usage:
  python3 voice-app.py

Hotkey: Cmd+↑ (press to start, press again to stop)
HTTP:   curl http://localhost:52777/toggle
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
import ctypes
import ctypes.util
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

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
MAX_DURATION = int(os.environ.get("RECORD_DURATION", "60"))

HTTP_PORT = 52777

# Audio settings
SAMPLE_RATE = 16000
CHANNELS = 1

# Global stop flag
_stop_recording = threading.Event()
_app_instance = None  # reference to rumps app


def has_accessibility():
    """Check accessibility permission via ctypes (pyobjc Quartz doesn't have this)"""
    try:
        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library('ApplicationServices'))
        return bool(lib.AXIsProcessTrusted())
    except:
        return False


def prompt_accessibility():
    """Prompt user to grant accessibility (opens system dialog)"""
    try:
        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library('ApplicationServices'))
        # kAXTrustedCheckOptionPrompt = True to show the system dialog
        prompt_key = ctypes.c_void_p
        options = ctypes.py_object({"kAXTrustedCheckOptionPrompt": True})
        return bool(lib.AXIsProcessTrustedWithOptions(options))
    except:
        return False


# ─── Audio Recording ──────────────────────────────────────────

def record_audio_toggle():
    """Record audio until stop signal or MAX_DURATION. Returns WAV path."""
    global _stop_recording
    _stop_recording.clear()

    frames = []
    block_samples = int(0.5 * SAMPLE_RATE)

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

        recording = np.concatenate(frames, axis=0)

        # Auto-gain
        rms = np.sqrt(np.mean(recording.astype(float)**2))
        if rms > 0 and rms < 300:
            gain = min(3000.0 / rms, 30.0)
            recording = np.clip(recording.astype(float) * gain, -32768, 32767).astype('int16')

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


# ─── Azure Transcription ──────────────────────────────────────

def azure_transcribe(audio_path):
    """Continuous recognition — transcribes entire audio file."""
    if not AZURE_KEY:
        return None, "Azure key not configured"

    try:
        import azure.cognitiveservices.speech as speechsdk

        speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
        speech_config.speech_recognition_language = LANGUAGE

        audio_config = speechsdk.audio.AudioConfig(filename=audio_path)
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

        results = []
        done = threading.Event()

        def on_recognized(evt):
            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech and evt.result.text:
                results.append(evt.result.text)
                print(f"  Segment: {evt.result.text}")

        def on_session_stopped(evt):
            done.set()

        def on_canceled(evt):
            done.set()

        recognizer.recognized.connect(on_recognized)
        recognizer.session_stopped.connect(on_session_stopped)
        recognizer.canceled.connect(on_canceled)

        recognizer.start_continuous_recognition_async().get()
        done.wait(timeout=120)
        recognizer.stop_continuous_recognition_async().get()

        if results:
            return " ".join(results), None
        else:
            return None, "No speech detected — try speaking louder or closer to mic"

    except Exception as e:
        return None, str(e)


# ─── DeepSeek Correction ──────────────────────────────────────

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


# ─── Clipboard & Paste ────────────────────────────────────────

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


# ─── HTTP Server (alternative trigger) ────────────────────────

class ToggleHandler(BaseHTTPRequestHandler):
    """HTTP endpoint: curl localhost:52777/toggle to start/stop recording"""
    def do_GET(self):
        global _app_instance
        if self.path == '/toggle' and _app_instance:
            if _app_instance.is_recording:
                _app_instance.stop_recording(None)
            else:
                _app_instance.start_recording(None)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"recording": _app_instance.is_recording}).encode())
        elif self.path == '/status' and _app_instance:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"recording": _app_instance.is_recording}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress HTTP logs


def start_http_server():
    """Start HTTP trigger server in background"""
    try:
        server = HTTPServer(('127.0.0.1', HTTP_PORT), ToggleHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"✅ HTTP trigger: curl http://localhost:{HTTP_PORT}/toggle")
    except OSError as e:
        print(f"⚠️  HTTP server failed (port {HTTP_PORT} in use?): {e}")


# ─── Main App ─────────────────────────────────────────────────

class VoiceInputApp(rumps.App):
    def __init__(self):
        rumps.App.__init__(self, "🎤", quit_button=None)
        self.is_recording = False
        self.hotkey_active = False
        self.menu = [
            "🎙️ Start Recording",
            "⏹️ Stop Recording",
            None,
            "⚙️ Accessibility Settings",
            "Quit"
        ]

    def start_hotkey(self):
        """Try to start global hotkey (needs accessibility permission)"""
        try:
            from pynput import keyboard

            if not has_accessibility():
                # Try prompting for permission
                prompt_accessibility()
                if not has_accessibility():
                    print("⚠️  No accessibility permission — global hotkey disabled")
                    print("   Enable at: System Settings → Privacy & Security → Accessibility")
                    print(f"   Alternative: curl http://localhost:{HTTP_PORT}/toggle")
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
            print(f"   Alternative: curl http://localhost:{HTTP_PORT}/toggle")

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
            audio_path = record_audio_toggle()
            if not audio_path:
                rumps.notification("Voice Input", "Error", "Recording failed")
                return

            rumps.notification("Voice Input", "Transcribing...", "")
            text, error = azure_transcribe(audio_path)

            if audio_path and os.path.exists(audio_path):
                os.unlink(audio_path)

            if not text:
                rumps.notification("Voice Input", "No speech", error or "Try speaking louder")
                return

            rumps.notification("Voice Input", "Correcting...", "")
            corrected = deepseek_correct(text)

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
    _app_instance = VoiceInputApp()

    # Start HTTP trigger (always works, no permission needed)
    start_http_server()

    # Try hotkey (needs accessibility)
    _app_instance.start_hotkey()

    _app_instance.run()
