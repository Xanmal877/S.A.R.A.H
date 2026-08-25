import requests
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LLMClient")

class LLMClient:
    """
    A swappable reasoning engine (Ollama/local model, OpenAI-compatible API, etc).
    This is NOT Sarah's identity - it's the cognitive component she currently
    happens to be running on. Her personality, memory, and goals live in
    agents/sarah_identity.md and the personality/memory modules, not here.
    """
    def __init__(self, base_url="http://localhost:11434", model="deepseek-v4-flash:cloud", api_type="ollama", num_ctx: int = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_type = api_type.lower()
        self.num_ctx = num_ctx  # Ollama context window, in tokens; None = model default

    @classmethod
    def from_node_config(cls) -> "LLMClient":
        """
        Builds this node's default reasoning-engine client from
        ~/.sarah/hive_config.json ("model"/"api_type"/"num_ctx") instead of
        the class defaults, so different machines (e.g. the Pi "core" vs.
        desktop-class "peer" clients) can each run a different model
        without a code change. See modules/hive/config.py.
        """
        from modules.hive.config import load_config
        cfg = load_config()
        kwargs = {
            "model": cfg.get("model", "deepseek-v4-flash:cloud"),
            "api_type": cfg.get("api_type", "ollama"),
            "num_ctx": cfg.get("num_ctx"),
        }
        if cfg.get("base_url"):
            kwargs["base_url"] = cfg["base_url"]
        return cls(**kwargs)

    @property
    def is_local(self) -> bool:
        """
        True only if this reasoning engine runs on this machine. Ollama's
        ":cloud" model suffix routes the request through Ollama's cloud
        proxy, and a non-loopback base_url means the engine is remote too.
        Privacy-sensitive context (e.g. screen OCR - see
        modules/perception/screen_watcher.py) should be gated on this,
        since a non-local engine means that data leaves the machine.
        """
        if ":cloud" in self.model.lower():
            return False
        host = self.base_url.split("//", 1)[-1].split(":", 1)[0].split("/", 1)[0]
        return host in ("localhost", "127.0.0.1", "::1")

    def _sync_generate(self, prompt: str) -> str:
        try:
            if self.api_type == "ollama":
                url = f"{self.base_url}/api/generate"
                payload = {"model": self.model, "prompt": prompt, "stream": False}
                if self.num_ctx:
                    payload["options"] = {"num_ctx": self.num_ctx}
                response = requests.post(url, json=payload, timeout=30)
                response.raise_for_status()
                return response.json().get("response", "")
            elif self.api_type == "openai":
                url = f"{self.base_url}/v1/chat/completions"
                # max_tokens is generous on purpose: a "thinking" model (see
                # models/*.gguf via llama-server) spends part of the budget
                # on a reasoning_content phase before the real answer - too
                # small a budget gets cut off mid-thought with empty content.
                payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1024}
                response = requests.post(url, json=payload, timeout=120)
                response.raise_for_status()
                message = response.json()["choices"][0]["message"]
                return message.get("content") or message.get("reasoning_content", "")
            else:
                raise ValueError(f"Unsupported api_type: {self.api_type}")
        except requests.exceptions.Timeout:
            return "Error: LLM request timed out."
        except requests.exceptions.ConnectionError:
            return "Error: Failed to connect to the LLM server."
        except requests.exceptions.RequestException as e:
            return f"Error: HTTP request failed: {str(e)}"
        except Exception as e:
            return f"Error: An unexpected error occurred: {str(e)}"

    async def generate_response(self, prompt: str, system_prompt: str = "You are a helpful AI assistant.") -> str:
        """
        Generates a response given a prompt and a system prompt.
        """
        full_prompt = f"SYSTEM: {system_prompt}\n\nUSER: {prompt}"
        return await asyncio.to_thread(self._sync_generate, full_prompt)

    async def generate_decision(self, prompt: str) -> str:
        return await asyncio.to_thread(self._sync_generate, prompt)

    def _sync_generate_vision(self, prompt: str, image_b64: str) -> str:
        try:
            if self.api_type != "ollama":
                raise ValueError("Vision generation currently only supports api_type='ollama'.")
            url = f"{self.base_url}/api/generate"
            payload = {"model": self.model, "prompt": prompt, "images": [image_b64], "stream": False}
            if self.num_ctx:
                payload["options"] = {"num_ctx": self.num_ctx}
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.exceptions.Timeout:
            return "Error: Vision request timed out."
        except requests.exceptions.ConnectionError:
            return "Error: Failed to connect to the local vision model."
        except requests.exceptions.RequestException as e:
            return f"Error: HTTP request failed: {str(e)}"
        except Exception as e:
            return f"Error: An unexpected error occurred: {str(e)}"

    async def describe_image(self, image_b64: str, prompt: str) -> str:
        """
        Sends an image to this reasoning engine for a text description.
        Hard privacy boundary: refuses unless this client is local (see
        `is_local`). Screen images (modules/perception/screen_watcher.py)
        must never be sent anywhere non-local - only the resulting text
        description, after this call, is allowed to travel further.
        """
        if not self.is_local:
            raise RuntimeError(
                "describe_image() refused: this LLMClient is not local. "
                "Images must only ever be sent to a local reasoning engine."
            )
        return await asyncio.to_thread(self._sync_generate_vision, prompt, image_b64)
