# Voice Input — macOS Finnish Speech-to-Text

Two engines: **Azure** (cloud, highest accuracy) and **Whisper** (offline, privacy).

## Quick Start

### Azure (cloud, recommended)
```bash
cd ~/.qclaw/workspace/voice-input
source .venv/bin/activate
python3 azure-stt.py                # Record → recognize → copy to clipboard
python3 azure-stt.py --duration 30  # Record 30 seconds
python3 azure-stt.py --lang sv-SE   # Swedish
```

### Whisper (offline)
```bash
cd ~/.qclaw/workspace/voice-input
source .venv/bin/activate
python3 whisper-stt.py              # Record → transcribe → copy to clipboard
python3 whisper-stt.py --model small  # Faster, less accurate
python3 whisper-stt.py --lang fi
```

## Installed Components
- ✅ whisper-cpp (brew) — CLI at `whisper-cli`
- ✅ ggml-medium model (1.4GB) — `models/ggml-medium.bin`
- ✅ sox (brew) — audio recording via `rec`
- ✅ Azure Speech SDK (pip venv) — `azure-cognitiveservices-speech 1.50.0`
- ✅ Azure region: norwayeast, language: fi-FI

## Files
- `.env` — Azure credentials (gitignored)
- `.venv/` — Python virtualenv (gitignored)
- `models/` — Whisper GGML models (gitignored)
- `azure-stt.py` — Azure Speech-to-Text script
- `whisper-stt.py` — Whisper offline transcription script

## macOS Shortcut (optional)
Add to Hammerspoon or use Automator for a global hotkey that runs:
```bash
cd ~/.qclaw/workspace/voice-input && source .venv/bin/activate && python3 azure-stt.py
```
