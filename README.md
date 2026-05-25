# 🎤 VoiceInput — AI-Powered Voice Input for macOS

Smart voice input for macOS: speak in Finnish (or any language), get corrected text pasted directly at your cursor.

**Like 豆包语音输入法, but for macOS — and fully customizable.**

## How It Works

```
🎙️ Record Audio → Azure Speech-to-Text → DeepSeek AI Correction → 📋 Auto-Paste
```

1. Press **Ctrl+Space** (or click menu bar icon)
2. Speak for up to 10 seconds
3. Your text appears at the cursor — auto-corrected with proper punctuation

## Features

- 🌍 **Multi-language**: Finnish, Chinese, Swedish, English (configurable)
- 🤖 **AI Auto-Correction**: Fixes speech recognition errors, adds punctuation
- ⌨️ **Global Hotkey**: Ctrl+Space from anywhere in macOS
- 🔒 **Privacy**: Audio processed via Azure (EU region), text corrected by DeepSeek
- 🎯 **Menu Bar App**: No Dock icon, lives in status bar
- 📋 **Auto-Paste**: Text appears directly at cursor position

## Requirements

- macOS 14+ (Apple Silicon or Intel)
- [Homebrew](https://brew.sh)
- Python 3.11+
- FFmpeg (`brew install ffmpeg`)
- Azure Speech Services API key ([free tier: 5h/month](https://azure.microsoft.com/en-us/services/cognitive-services/speech-to-text/))
- DeepSeek API key ([cheap, ~$0.14/M tokens](https://platform.deepseek.com/))

## Installation

### Quick Install

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/voice-input-macos.git
cd voice-input-macos

# Setup
chmod +x setup.sh && ./setup.sh

# Run
open VoiceInput.app
```

### Manual Setup

```bash
# Install dependencies
brew install ffmpeg sox

# Create Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env with your API keys

# Build app
chmod +x build-app.sh && ./build-app.sh

# Run
open VoiceInput.app
```

## Configuration

Edit `.env`:

```env
# Azure Speech (required)
AZURE_SPEECH_REGION=norwayeast
AZURE_SPEECH_KEY=your-azure-key

# DeepSeek for AI correction (optional but recommended)
DEEPSEEK_API_KEY=your-deepseek-key

# Language (fi-FI, zh-CN, sv-SE, en-US)
VOICE_LANGUAGE=fi-FI

# Recording duration (seconds)
RECORD_DURATION=10
```

## Usage

| Action | How |
|--------|-----|
| Start recording | **Ctrl+Space** or click 🎤 menu bar icon |
| Stop recording | Wait for auto-stop (10s) |
| Change language | Edit `.env` → `VOICE_LANGUAGE` |
| Skip AI correction | Use `--no-correct` flag in CLI mode |

## CLI Mode (without app)

```bash
source .venv/bin/activate

# Full pipeline: record → transcribe → correct → paste
python3 smart-voice.py --duration 10

# Azure only (no AI correction)
python3 azure-stt.py --duration 10

# Chinese
python3 smart-voice.py --lang zh-CN --duration 10
```

## Architecture

```
voice-input-macos/
├── voice-app.py          # macOS menu bar app (rumps)
├── smart-voice.py        # CLI: Azure STT + DeepSeek correction
├── azure-stt.py          # CLI: Azure STT only
├── whisper-stt.py        # CLI: Offline Whisper (optional)
├── build-app.sh          # Build VoiceInput.app bundle
├── setup.sh              # One-click setup script
├── requirements.txt      # Python dependencies
├── .env.example          # API key template
└── VoiceInput.app/       # Built macOS app bundle
```

## Cost Estimate

| Service | Free Tier | Paid |
|---------|-----------|------|
| Azure Speech | 5 hours/month | $1/hour |
| DeepSeek | — | ~$0.001 per correction |

Typical usage: **~$0.50/month** for daily voice input.

## Roadmap

- [ ] Real-time streaming transcription (no 10s wait)
- [ ] Multiple language profiles with hotkey switching
- [ ] Local Whisper option (fully offline)
- [ ] Custom correction prompts per app
- [ ] Swift native app (no Python dependency)
- [ ] Mac App Store distribution

## License

MIT License — use it, modify it, ship it.

## Acknowledgments

- Inspired by 豆包语音输入法 (Doubao Voice Input)
- Built with [Azure Speech](https://azure.microsoft.com/en-us/services/cognitive-services/speech-to-text/), [DeepSeek](https://deepseek.com/), [rumps](https://github.com/jaredks/rumps)
