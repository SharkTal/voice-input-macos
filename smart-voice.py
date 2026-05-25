#!/usr/bin/env python3
"""
Smart Voice Input — Azure Speech + AI Auto-Correction
Like 豆包语音输入法: voice → STT → LLM correction → clean text → clipboard

Usage:
  python3 smart-voice.py                    # Default: record until silence
  python3 smart-voice.py --duration 10      # Record 10 seconds
  python3 smart-voice.py --lang fi-FI       # Finnish (default)
  python3 smart-voice.py --lang zh-CN       # Chinese
  python3 smart-voice.py --no-correct       # Skip AI correction (raw STT only)
  python3 smart-voice.py --llm openai       # Force OpenAI backend
  python3 smart-voice.py --llm deepseek     # Force DeepSeek backend
  python3 smart-voice.py --llm ollama       # Force Ollama (local)
  python3 smart-voice.py --prompt custom    # Custom correction style
"""

import argparse
import json
import os
import sys
import subprocess
import tempfile
import time
from pathlib import Path

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

# LLM API configs (add your keys to .env)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")

# Correction system prompts by language
CORRECTION_PROMPTS = {
    "fi-FI": """Olet suomen kielen korjaaja. Käyttäjä puhuu ääneen ja puheentunnistus tekee virheitä.

Tehtäväsi:
1. Korjaa puheentunnistuksen virheet (väärät sanat, puuttuvat kirjaimet)
2. Lisää oikea välimerkitys (pisteet, pilkut, kysymysmerkit)
3. Korjaa kielioppivirheet
4. Jos sana on epäselva, valitse kontekstiin sopivin sana
5. Älä muuta merkitystä tai lisää sisältöä

Palauta VAIN korjattu teksti, ei selityksiä.""",

    "zh-CN": """你是中文语音纠错助手。用户语音输入后，语音识别可能有错误。

你的任务：
1. 修正语音识别的同音字错误
2. 添加正确的标点符号
3. 修正语法错误
4. 如果词语不明确，选择上下文最合适的词
5. 不要改变原意或添加内容

只返回纠正后的文本，不要解释。""",

    "sv-SE": """Du är en svensk språkkorrekturläsare. Användaren talar och taligenkänningen gör fel.

Din uppgift:
1. Rätta taligenkänningsfel
2. Lägg till korrekt interpunktion
3. Rätta grammatiska fel
4. Om ett ord är oklart, välj det som passar kontexten bäst
5. Ändra inte innebörden eller lägg till innehåll

Returnera ENDAST den korrigerade texten, inga förklaringar.""",

    "en-US": """You are an English speech correction assistant. The user dictated text and the speech recognition may have errors.

Your task:
1. Fix speech recognition errors (wrong words, missing letters)
2. Add proper punctuation
3. Fix grammar errors
4. If a word is unclear, choose the most contextually appropriate one
5. Do not change meaning or add content

Return ONLY the corrected text, no explanations."""
}

DEFAULT_PROMPT = CORRECTION_PROMPTS["fi-FI"]


def record_audio(output_path, duration=None, sample_rate=16000):
    """Record audio using ffmpeg with gain boost"""
    try:
        subprocess.run(["which", "ffmpeg"], capture_output=True, check=True)
        raw_path = output_path.replace(".wav", "_raw.wav")
        dur_args = ["-t", str(duration)] if duration else []
        print("🎙️  Recording... (Ctrl+C to stop)" + (f" {duration}s" if duration else " auto-stop on silence"))
        cmd = ["ffmpeg", "-f", "avfoundation", "-i", ":1",
               "-af", "volume=20dB",
               "-ar", str(sample_rate), "-ac", "1", "-sample_fmt", "s16"] + \
              dur_args + ["-y", raw_path]
        subprocess.run(cmd, check=True)

        # Trim silence with sox
        if duration is None:
            try:
                subprocess.run(["which", "sox"], capture_output=True, check=True)
                cmd = ["sox", raw_path, output_path,
                       "silence", "1", "0.1", "1%", "1", "1.5", "1%"]
                subprocess.run(cmd, check=True)
                os.unlink(raw_path)
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

        if raw_path != output_path:
            os.rename(raw_path, output_path)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fallback to sox
    try:
        subprocess.run(["which", "rec"], capture_output=True, check=True)
        vol = ["vol", "4"]
        if duration:
            cmd = ["rec", "-r", str(sample_rate), "-c", "1", "-b", "16", output_path] + \
                  vol + ["trim", "0", str(duration)]
        else:
            cmd = ["rec", "-r", str(sample_rate), "-c", "1", "-b", "16", output_path] + \
                  vol + ["silence", "1", "0.1", "3%", "1", "2.0", "3%"]
        print("🎙️  Recording with sox... (Ctrl+C to stop)")
        subprocess.run(cmd, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    print("Error: Need ffmpeg or sox for recording.", file=sys.stderr)
    return False


def azure_recognize(audio_path, language="fi-FI"):
    """Azure Speech recognition with continuous mode"""
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError:
        print("Error: azure-cognitiveservices-speech not installed", file=sys.stderr)
        sys.exit(1)

    speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
    speech_config.speech_recognition_language = language
    speech_config.set_property(speechsdk.PropertyId.SpeechServiceResponse_PostProcessingOption, "TrueText")

    audio_config = speechsdk.audio.AudioConfig(filename=audio_path)
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    results = []
    done = False

    def handle_result(evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            results.append(evt.result.text)

    def handle_stop(evt):
        nonlocal done
        done = True

    recognizer.recognized.connect(handle_result)
    recognizer.session_stopped.connect(handle_stop)
    recognizer.canceled.connect(handle_stop)

    print("🔄 Recognizing with Azure...")
    recognizer.start_continuous_recognition()

    start = time.time()
    while not done and (time.time() - start) < 30:
        time.sleep(0.1)

    recognizer.stop_continuous_recognition()

    if results:
        return " ".join(results)
    return None


def llm_correct_openai(raw_text, language="fi-FI", custom_prompt=None):
    """Correct text using OpenAI-compatible API"""
    import urllib.request

    api_key = OPENAI_API_KEY or DEEPSEEK_API_KEY
    base_url = OPENAI_BASE_URL if OPENAI_API_KEY else DEEPSEEK_BASE_URL
    model = OPENAI_MODEL if OPENAI_API_KEY else DEEPSEEK_MODEL

    if not api_key:
        return None, "No API key configured"

    system_prompt = custom_prompt or CORRECTION_PROMPTS.get(language, DEFAULT_PROMPT)

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": raw_text}
        ],
        "temperature": 0.1,
        "max_tokens": 2048
    }).encode("utf-8")

    url = f"{base_url}/chat/completions"
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    try:
        print(f"🤖 Correcting with {model}...")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip(), None
    except Exception as e:
        return None, str(e)


def llm_correct_ollama(raw_text, language="fi-FI", custom_prompt=None):
    """Correct text using local Ollama"""
    import urllib.request

    system_prompt = custom_prompt or CORRECTION_PROMPTS.get(language, DEFAULT_PROMPT)

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": raw_text}
        ],
        "stream": False,
        "options": {"temperature": 0.1}
    }).encode("utf-8")

    url = f"{OLLAMA_BASE_URL}/api/chat"
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        print(f"🤖 Correcting with Ollama ({OLLAMA_MODEL})...")
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["message"]["content"].strip(), None
    except Exception as e:
        return None, str(e)


def llm_correct(raw_text, language="fi-FI", backend="auto", custom_prompt=None):
    """Auto-select or force LLM backend for correction"""
    if backend == "auto":
        # Priority: OpenAI/DeepSeek > Ollama
        if OPENAI_API_KEY or DEEPSEEK_API_KEY:
            backend = "openai"
        else:
            backend = "ollama"

    if backend == "ollama":
        return llm_correct_ollama(raw_text, language, custom_prompt)
    else:
        return llm_correct_openai(raw_text, language, custom_prompt)


def copy_to_clipboard(text):
    process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    process.communicate(text.encode("utf-8"))
    return process.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Smart Voice Input — STT + AI Correction")
    parser.add_argument("--duration", "-d", type=int, help="Recording duration in seconds")
    parser.add_argument("--lang", "-l", default="fi-FI", help="Language (default: fi-FI)")
    parser.add_argument("--no-correct", action="store_true", help="Skip AI correction")
    parser.add_argument("--llm", choices=["openai", "deepseek", "ollama", "auto"],
                       default="auto", help="LLM backend (default: auto)")
    parser.add_argument("--prompt", type=str, help="Custom correction prompt")
    args = parser.parse_args()

    if not AZURE_KEY:
        print("Error: AZURE_SPEECH_KEY not set. Check voice-input/.env", file=sys.stderr)
        sys.exit(1)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        if not record_audio(tmp_path, duration=args.duration):
            sys.exit(1)

        raw_text = azure_recognize(tmp_path, language=args.lang)

        if not raw_text:
            print("\n❌ No speech detected")
            sys.exit(1)

        print(f"\n📝 Raw: {raw_text}")

        if args.no_correct:
            final_text = raw_text
        else:
            corrected, error = llm_correct(raw_text, language=args.lang,
                                           backend=args.llm, custom_prompt=args.prompt)
            if corrected:
                final_text = corrected
                print(f"✅ Corrected: {final_text}")
            else:
                print(f"⚠️  Correction failed ({error}), using raw text")
                final_text = raw_text

        if copy_to_clipboard(final_text):
            print("📋 Copied to clipboard")

    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    main()
