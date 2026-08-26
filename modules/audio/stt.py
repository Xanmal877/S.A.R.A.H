import asyncio
import logging

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from modules.audio.audio_config import SAMPLE_RATE, CHUNK

logger = logging.getLogger("STT")

SILENCE_RMS_THRESHOLD = 300      # int16 RMS below this counts as silence
SILENCE_DURATION_S = 1.2         # stop recording after this much trailing silence
MAX_UTTERANCE_S = 15.0           # hard cap so a stuck mic can't record forever


class SpeechToText:
    """
    Records a single utterance from the microphone (starting immediately -
    call this right after WakeWordListener.wait() fires) and transcribes it
    locally with faster-whisper. Recording stops on trailing silence or the
    max-duration cap, whichever comes first.
    """

    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8", mic_device=None):
        self.mic_device = mic_device
        self._model = None
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type

    def _load_model(self):
        if self._model is None:
            self._model = WhisperModel(self._model_size, device=self._device, compute_type=self._compute_type)
        return self._model

    def _record_sync(self) -> np.ndarray:
        frames = []
        silence_chunks = 0
        silence_chunk_limit = int(SILENCE_DURATION_S * SAMPLE_RATE / CHUNK)
        max_chunks = int(MAX_UTTERANCE_S * SAMPLE_RATE / CHUNK)

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                             blocksize=CHUNK, device=self.mic_device) as stream:
            for _ in range(max_chunks):
                data, _ = stream.read(CHUNK)
                chunk = data[:, 0]
                frames.append(chunk)
                rms = np.sqrt(np.mean(chunk.astype(np.float64) ** 2))
                if rms < SILENCE_RMS_THRESHOLD:
                    silence_chunks += 1
                    if len(frames) > 3 and silence_chunks >= silence_chunk_limit:
                        break
                else:
                    silence_chunks = 0

        return np.concatenate(frames) if frames else np.array([], dtype=np.int16)

    def _transcribe_sync(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        model = self._load_model()
        audio_float = audio.astype(np.float32) / 32768.0
        segments, _info = model.transcribe(audio_float, language="en")
        return " ".join(s.text.strip() for s in segments).strip()

    async def listen_and_transcribe(self) -> str:
        audio = await asyncio.to_thread(self._record_sync)
        return await asyncio.to_thread(self._transcribe_sync, audio)
