#!/bin/bash
# One-click setup for VoiceInput macOS app
set -e

echo "🎤 VoiceInput Setup"
echo "===================="

# Check brew
if ! command -v brew &> /dev/null; then
    echo "❌ Homebrew not found. Install from https://brew.sh"
    exit 1
fi

# Install system dependencies
echo "📦 Installing system dependencies..."
brew install ffmpeg sox 2>/dev/null || true

# Create Python venv
echo "🐍 Setting up Python environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt 2>/dev/null || pip install azure-cognitiveservices-speech rumps pynput pyobjc-framework-Quartz pyobjc-framework-Cocoa

# Check .env
if [ ! -f .env ]; then
    echo ""
    echo "⚠️  No .env file found!"
    cp .env.example .env
    echo "📝 Created .env from template. Please add your API keys:"
    echo "   - AZURE_SPEECH_KEY (required) — https://azure.microsoft.com/en-us/services/cognitive-services/speech-to-text/"
    echo "   - DEEPSEEK_API_KEY (recommended) — https://platform.deepseek.com/"
    echo ""
    echo "   Run: nano .env"
    echo ""
fi

# Build app
echo "🔨 Building VoiceInput.app..."
chmod +x build-app.sh
./build-app.sh

echo ""
echo "✅ Setup complete!"
echo ""
echo "To run:"
echo "  open VoiceInput.app"
echo ""
echo "To install to Applications:"
echo "  cp -r VoiceInput.app /Applications/"
