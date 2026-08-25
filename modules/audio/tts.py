import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import wave

logger = logging.getLogger("TTS")

VOICES_DIR = os.path.expanduser("~/.sarah/piper_voices")
DEFAULT_VOICE = "en_US-lessac-medium"

_PLAYERS = ["paplay", "aplay", "ffplay"]


class TextToSpeech:
    """
    Local, offline text-to-speech via Piper (github.com/OHF-Voice/piper1-gpl)
    - fast even on CPU, no PyTorch/GPU dependency, chosen over XTTS v2
    because this only needs to run on client-class machines (never the Pi
    "brain" node - see agents/sarah_identity.md), and over espeak because
    Piper's neural voices sound far less robotic.

    Speaks through this machine's own speakers when someone asks Sarah a
    question directly on it (see sarah_cli.py). Model is loaded lazily on
    first use and kept in memory after that.
    """

    def __init__(self, voice: str = DEFAULT_VOICE):
        self.voice_name = voice
        self._voice = None  # lazy-loaded piper.PiperVoice
        self.player = next((p for p in _PLAYERS if shutil.which(p)), None)
        if not self.player:
            logger.warning("No audio player found (tried paplay/aplay/ffplay) - speech will be synthesized but not played.")

    def _load_voice(self):
        if self._voice is not None:
            return self._voice
        model_path = os.path.join(VOICES_DIR, f"{self.voice_name}.onnx")
        if not os.path.exists(model_path):
            logger.warning(
                f"Piper voice not found at {model_path}. Run: "
                f"python3 -m piper.download_voices --download-dir {VOICES_DIR} {self.voice_name}"
            )
            return None
        from piper import PiperVoice
        self._voice = PiperVoice.load(model_path)
        return self._voice

    def _speak_sync(self, text: str):
        voice = self._load_voice()
        if voice is None:
            return
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name
            with wave.open(wav_path, "wb") as wav_file:
                voice.synthesize_wav(text, wav_file)

            if self.player:
                subprocess.run([self.player, wav_path], timeout=60,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.warning(f"TTS playback failed: {e}")
        finally:
            try:
                os.remove(wav_path)
            except Exception:
                pass

    async def speak(self, text: str):
        if not text:
            return
        await asyncio.to_thread(self._speak_sync, text)


tts = TextToSpeech()
