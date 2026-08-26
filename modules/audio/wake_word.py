import asyncio
import logging
import os

import sounddevice as sd
import openwakeword
from openwakeword.model import Model

logger = logging.getLogger("WakeWord")

SAMPLE_RATE = 16000
CHUNK = 1280  # openWakeWord expects 80ms frames at 16kHz

_MODEL_DIR = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")

# openWakeWord ships a handful of pretrained wake words; there is no
# pretrained "Hey Sarah" model (that needs training on custom data, which is
# future work - see openWakeWord's training notebook). "hey_jarvis" is the
# closest available stand-in for now: say "Hey Jarvis" to wake her up.
DEFAULT_WAKE_WORD = "hey_jarvis"


class WakeWordListener:
    """
    Always-on wake-word detection over the default microphone. `wait()`
    blocks (off the event loop, via asyncio.to_thread) until the wake word
    is heard, then returns - callers typically follow with recording +
    transcription (see modules/audio/stt.py).
    """

    def __init__(self, wake_word: str = DEFAULT_WAKE_WORD, threshold: float = 0.7, device=None):
        self.wake_word = wake_word
        self.threshold = threshold
        self.device = device  # sounddevice device name/index, None = system default
        model_path = os.path.join(_MODEL_DIR, f"{wake_word}_v0.1.onnx")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"No bundled wake word model at {model_path}")
        self._model = Model(wakeword_model_paths=[model_path])
        self._key = f"{wake_word}_v0.1"

    def _wait_sync(self):
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                             blocksize=CHUNK, device=self.device) as stream:
            while True:
                data, _ = stream.read(CHUNK)
                score = self._model.predict(data[:, 0])[self._key]
                if score >= self.threshold:
                    logger.info(f"Wake word '{self.wake_word}' detected (score={score:.2f})")
                    return

    async def wait(self):
        await asyncio.to_thread(self._wait_sync)
