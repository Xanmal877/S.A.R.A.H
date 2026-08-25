import atexit
import logging
import os
import subprocess
import time

import requests

logger = logging.getLogger("LlamaServerManager")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LLAMA_BIN_DIR = os.path.join(PROJECT_ROOT, "llama.cpp", "bin")
LLAMA_SERVER_BIN = os.path.join(LLAMA_BIN_DIR, "llama-server")
LOG_PATH = os.path.expanduser("~/.sarah/llama_server.log")


class LlamaServerManager:
    """
    Owns the lifecycle of a local llama-server process serving a GGUF model
    (see llama.cpp/bin/ and models/) - starts it on demand if nothing is
    already listening on the configured port, and stops it on process exit.
    Only relevant for nodes configured with api_type="openai" pointing at a
    local llama-server base_url (see modules/hive/config.py); Ollama-backed
    nodes don't need this at all.
    """

    def __init__(self):
        self._proc = None
        self._registered_exit = False

    def _is_up(self, base_url: str) -> bool:
        try:
            r = requests.get(f"{base_url}/health", timeout=2)
            return r.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def ensure_running(self, model_path: str, port: int = 8090, n_gpu_layers: int = 999, timeout: float = 60.0):
        base_url = f"http://127.0.0.1:{port}"
        if self._is_up(base_url):
            logger.info(f"llama-server already listening on {port}")
            return

        if not os.path.exists(LLAMA_SERVER_BIN):
            logger.warning(f"llama-server binary not found at {LLAMA_SERVER_BIN} - not starting.")
            return
        model_full_path = model_path if os.path.isabs(model_path) else os.path.join(PROJECT_ROOT, model_path)
        if not os.path.exists(model_full_path):
            logger.warning(f"Model file not found at {model_full_path} - not starting llama-server.")
            return

        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        env = dict(os.environ)
        env["LD_LIBRARY_PATH"] = LLAMA_BIN_DIR + ":" + env.get("LD_LIBRARY_PATH", "")

        log_file = open(LOG_PATH, "a")
        self._proc = subprocess.Popen(
            [LLAMA_SERVER_BIN, "-m", model_full_path, "--port", str(port), "-ngl", str(n_gpu_layers)],
            env=env, stdout=log_file, stderr=subprocess.STDOUT,
        )
        logger.info(f"Starting llama-server (pid {self._proc.pid}) on port {port} with {model_full_path}")

        if not self._registered_exit:
            atexit.register(self.stop)
            self._registered_exit = True

        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._is_up(base_url):
                logger.info("llama-server is up")
                return
            if self._proc.poll() is not None:
                logger.warning(f"llama-server exited early (code {self._proc.returncode}) - see {LOG_PATH}")
                return
            time.sleep(0.5)
        logger.warning(f"llama-server did not become healthy within {timeout}s")

    def stop(self):
        if self._proc and self._proc.poll() is None:
            logger.info(f"Stopping llama-server (pid {self._proc.pid})")
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None


llama_manager = LlamaServerManager()
