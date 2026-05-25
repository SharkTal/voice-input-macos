#!/bin/bash
# Build VoiceInput.app — macOS menu bar voice input app
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="VoiceInput"
APP_DIR="$SCRIPT_DIR/$APP_NAME.app"

echo "Building $APP_NAME.app..."

# Remove old build
rm -rf "$APP_DIR"

# Create app bundle structure
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Create Info.plist
cat > "$APP_DIR/Contents/Info.plist" << PLIST
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
    <string>1.1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.1.0</string>
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
    <key>NSAppleEventsUsageDescription</key>
    <string>Voice Input needs accessibility access for global hotkey.</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
</dict>
</plist>
PLIST

# Create launcher script with robust path handling
cat > "$APP_DIR/Contents/MacOS/VoiceInput" << LAUNCHER
#!/bin/bash
# VoiceInput launcher — works when opened from Finder

export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"

# Find project directory (relative to this script)
PROJECT_DIR="\$(cd "\$(dirname "\$0")/../.." && pwd)"

# If running from the .app bundle, the project is the parent of VoiceInput.app
if [ ! -f "\$PROJECT_DIR/voice-app.py" ]; then
    # Try: the .app is inside the project directory
    PROJECT_DIR="\$(dirname "\$0")/../../.."
    PROJECT_DIR="\$(cd "\$PROJECT_DIR" 2>/dev/null && pwd)"
fi

# Fallback: hardcoded path
if [ ! -f "\$PROJECT_DIR/voice-app.py" ]; then
    PROJECT_DIR="/Users/tal/.qclaw/workspace/voice-input"
fi

cd "\$PROJECT_DIR" || exit 1

# Activate venv
if [ -f "\$PROJECT_DIR/.venv/bin/activate" ]; then
    source "\$PROJECT_DIR/.venv/bin/activate"
fi

# Run the app
exec python3 "\$PROJECT_DIR/voice-app.py"
LAUNCHER

chmod +x "$APP_DIR/Contents/MacOS/VoiceInput"

# Copy icon if available
if [ -f "$SCRIPT_DIR/VoiceInput.app/Contents/Resources/AppIcon.icns" ]; then
    cp "$SCRIPT_DIR/VoiceInput.app/Contents/Resources/AppIcon.icns" "$APP_DIR/Contents/Resources/AppIcon.icns" 2>/dev/null || true
fi
if [ -f "$SCRIPT_DIR/icon-source.png" ]; then
    # Rebuild iconset from source
    ICONSET="$APP_DIR.iconset"
    mkdir -p "$ICONSET"
    sips -z 1024 1024 "$SCRIPT_DIR/icon-source.png" --out "$ICONSET/icon_512x512@2x.png" 2>/dev/null
    sips -z 512 512 "$SCRIPT_DIR/icon-source.png" --out "$ICONSET/icon_512x512.png" 2>/dev/null
    sips -z 256 256 "$SCRIPT_DIR/icon-source.png" --out "$ICONSET/icon_256x256.png" 2>/dev/null
    sips -z 128 128 "$SCRIPT_DIR/icon-source.png" --out "$ICONSET/icon_128x128.png" 2>/dev/null
    sips -z 64 64 "$SCRIPT_DIR/icon-source.png" --out "$ICONSET/icon_32x32@2x.png" 2>/dev/null
    sips -z 32 32 "$SCRIPT_DIR/icon-source.png" --out "$ICONSET/icon_32x32.png" 2>/dev/null
    sips -z 16 16 "$SCRIPT_DIR/icon-source.png" --out "$ICONSET/icon_16x16.png" 2>/dev/null
    cp "$ICONSET/icon_16x16.png" "$ICONSET/icon_16x16@2x.png"
    cp "$ICONSET/icon_128x128.png" "$ICONSET/icon_128x128@2x.png"
    cp "$ICONSET/icon_256x256.png" "$ICONSET/icon_256x256@2x.png"
    iconutil -c icns "$ICONSET" -o "$APP_DIR/Contents/Resources/AppIcon.icns" 2>/dev/null
    rm -rf "$ICONSET"
fi

# Remove quarantine
xattr -cr "$APP_DIR" 2>/dev/null || true

echo ""
echo "✅ $APP_NAME.app created:"
echo "   $APP_DIR"
echo ""
echo "To install:"
echo "  cp -r '$APP_DIR' /Applications/"
echo "  xattr -cr /Applications/VoiceInput.app"
echo ""
echo "To run:"
echo "  open '$APP_DIR'"
