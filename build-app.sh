#!/bin/bash
# Build VoiceInput.app from Python script
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="VoiceInput"
APP_DIR="$SCRIPT_DIR/$APP_NAME.app"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "Building $APP_NAME.app..."

# Create app bundle structure
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"
mkdir -p "$APP_DIR/Contents/Frameworks"

# Create Info.plist
cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>VoiceInput</string>
    <key>CFBundleDisplayName</key>
    <string>Voice Input</string>
    <key>CFBundleIdentifier</key>
    <string>com.sisu.voiceinput</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>VoiceInput</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>Voice Input needs microphone access for speech recognition.</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
</dict>
</plist>
PLIST

# Create launcher script
cat > "$APP_DIR/Contents/MacOS/VoiceInput" << LAUNCHER
#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"
cd "$SCRIPT_DIR"
source "$VENV_DIR/bin/activate"
exec python3 "$SCRIPT_DIR/voice-app.py"
LAUNCHER

chmod +x "$APP_DIR/Contents/MacOS/VoiceInput"

# Create a simple icon (using SF Symbols)
python3 -c "
import subprocess, os
icon_path = '$APP_DIR/Contents/Resources/AppIcon.icns'
# Use system microphone icon - create a simple icns
# For now, just skip icon creation
print('App bundle created (no custom icon)')
"

echo ""
echo "✅ $APP_NAME.app created at:"
echo "   $APP_DIR"
echo ""
echo "To install:"
echo "  cp -r '$APP_DIR' /Applications/"
echo ""
echo "To run now:"
echo "  open '$APP_DIR'"
echo ""
echo "To add to Login Items:"
echo "  System Settings → General → Login Items → Add $APP_NAME"
