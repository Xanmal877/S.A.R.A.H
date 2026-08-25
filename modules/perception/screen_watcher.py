import asyncio
import base64
import difflib
import logging
import os
import subprocess
import tempfile
import time

logger = logging.getLogger("ScreenWatcher")

# Deliberately asks for a *description*, not a transcription. The local
# vision model is the only thing that ever sees the raw screenshot; this
# text is the sole output allowed to leave that boundary (see
# LLMClient.describe_image / LLMClient.is_local).
REDACTION_PROMPT = (
    "You are looking at a screenshot of a personal computer desktop. In a few sentences, "
    "describe what is generally happening on screen - which kinds of apps/windows are open, "
    "the general nature of the content, and what the user appears to be doing - so another "
    "AI system can react to the context.\n\n"
    "IMPORTANT: Do not transcribe or repeat any specific sensitive data visible on screen, "
    "even partially. Never include: passwords, API keys/tokens, seed phrases, credit card or "
    "bank account numbers, the literal contents of private messages/emails, or personal "
    "identifying information (full names, addresses, phone numbers, email addresses). Describe "
    "the *category* of such content instead (e.g. \"a password entry field\", \"a private chat "
    "conversation\", \"a code editor with a config file\") without quoting the actual text. "
    "Be a general observer, not a transcriber."
)


class ScreenWatcher:
    """
    Gives Sarah continuous, lightweight visual awareness: periodically
    captures the full screen and has a local vision model describe (and
    redact) it, on its own cadence (default every 7s, independent of the
    1s agent tick), so ObservationModule can fold what's on-screen into
    her world state.

    Capture uses `spectacle` (KDE's headless screenshot tool - this
    machine's desktop environment) as a subprocess. The screenshot image
    itself is only ever handed to `vision_client`, which must be local
    (LLMClient.is_local) - `describe_image` refuses otherwise. Only the
    resulting sanitized text description is kept/exposed further, e.g. to
    a cloud reasoning engine.
    """

    def __init__(self, vision_client, interval: float = 7.0):
        if not vision_client.is_local:
            raise ValueError(
                "ScreenWatcher requires a local vision_client - raw screen "
                "images must never be sent to a non-local reasoning engine."
            )
        self.vision_client = vision_client
        self.interval = interval
        self.last_capture_time = 0.0
        self.last_text = ""
        self.last_changed = False

    def _capture_and_encode_sync(self) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            shot_path = os.path.join(tmpdir, "screen.png")
            try:
                subprocess.run(
                    ["spectacle", "-b", "-n", "-o", shot_path],
                    timeout=10, check=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.warning(f"Screenshot capture failed: {e}")
                return ""

            if not os.path.exists(shot_path):
                return ""

            with open(shot_path, "rb") as f:
                return base64.b64encode(f.read()).decode()

    async def maybe_capture(self) -> bool:
        """Capture + describe on the configured interval. Returns True if
        a new description was obtained this call."""
        now = time.monotonic()
        if now - self.last_capture_time < self.interval:
            return False
        self.last_capture_time = now

        image_b64 = await asyncio.to_thread(self._capture_and_encode_sync)
        if not image_b64:
            return False

        description = await self.vision_client.describe_image(image_b64, REDACTION_PROMPT)
        if description.startswith("Error:"):
            logger.warning(f"Vision description failed: {description}")
            return False

        self.last_changed = self._is_significant_change(self.last_text, description)
        self.last_text = description
        return True

    @staticmethod
    def _is_significant_change(old: str, new: str, threshold: float = 0.35) -> bool:
        if not old and new:
            return True
        if not new:
            return False
        ratio = difflib.SequenceMatcher(None, old, new).ratio()
        return (1.0 - ratio) >= threshold

    def get_summary(self) -> str:
        if not self.last_text:
            return "No screen description captured yet."
        changed_note = " (changed since last look)" if self.last_changed else " (largely unchanged)"
        return f"{self.last_text}{changed_note}"
