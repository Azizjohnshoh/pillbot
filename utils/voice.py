
from gtts import gTTS
import time, os
VOICE_DIR = "voice"
os.makedirs(VOICE_DIR, exist_ok=True)
def text_to_speech(text, lang='uz'):
    fn = f"tts_{int(time.time())}.mp3"
    path = os.path.join(VOICE_DIR, fn)
    tts = gTTS(text=text, lang=lang)
    tts.save(path)
    return path
