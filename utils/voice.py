
"""Voice notification helper using gTTS (example)"""
from gtts import gTTS
import os, tempfile

def text_to_speech(text, lang='uz'):
    tts = gTTS(text=text, lang=lang)
    fd, path = tempfile.mkstemp(suffix='.mp3')
    os.close(fd)
    tts.save(path)
    return path
