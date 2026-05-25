#!/bin/bash
# This script is called by the AppleScript wrapper
cd /Users/tal/.qclaw/workspace/voice-input
source .venv/bin/activate
exec python3 voice-app.py >> /tmp/voiceinput.log 2>&1
