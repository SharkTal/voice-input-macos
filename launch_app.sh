#!/bin/bash
# Launch VoiceInput in a hidden Terminal window
# This way it inherits Terminal's mic + accessibility permissions
osascript -e '
tell application "Terminal"
    activate
    set w to do script "cd /Users/tal/.qclaw/workspace/voice-input && source .venv/bin/activate && python3 voice-app.py"
    set miniaturized of window 1 to true
end tell'
