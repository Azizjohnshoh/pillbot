from gtts import gTTS
import os

def generate_tts(text, filename="voice.mp3", lang="uz"):
    try:
        tts = gTTS(text=text, lang=lang)
        tts.save(filename)
        return filename
    except Exception as e:
        print("TTS error:", e)
        return None
