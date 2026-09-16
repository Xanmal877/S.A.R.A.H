import json
import os
import secrets
import socket
import subprocess

SARAH_HOME = os.path.expanduser("~/.sarah")
CONFIG_PATH = os.path.join(SARAH_HOME, "hive_config.json")
SECRET_PATH = os.path.join(SARAH_HOME, "hive_secret")
TLS_CERT_PATH = os.path.join(SARAH_HOME, "hive_cert.pem")
TLS_KEY_PATH = os.path.join(SARAH_HOME, "hive_key.pem")

DEFAULT_CONFIG = {
    "role": "peer",       # "peer" (default: serves read-only info to others) or
                           # "core" (also actively discovers + polls peers)
    "port": 8787,
    "node_name": None,     # defaults to hostname if unset
    "poll_interval": 20.0,
    "model": "deepseek-v4-flash:cloud",  # reasoning model; Ollama's ":cloud" suffix routes
                             # the request through Ollama's cloud proxy, so this node's
                             # reasoning runs via the cloud while staying on api_type "ollama".
    "api_type": "ollama",   # default reasoning runtime is Ollama at localhost:11434. The
                             # selected Ollama model tag ("local" vs ":cloud") chooses
                             # local vs cloud reasoning - no separate routing required.
    "base_url": None,       # None = LLMClient's own default (http://localhost:11434). A node
                             # that deliberately points at a remote/no-longer-default Ollama
                             # (e.g. a hive peer) can override this explicitly.
    "num_ctx": 8192,        # requested context window, in tokens
    "auto_start_llama_server": False,  # default reasoning is Ollama now, so no local
                             # llama-server is auto-started. (Legacy llama-server nodes must
                             # set api_type "openai" + base_url + this true explicitly.)
    "llama_model_path": "models/Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf",
    "llama_port": 8090,
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    if not cfg.get("node_name"):
        cfg["node_name"] = socket.gethostname()
    return cfg


def load_secret() -> bytes:
    """Returns None if no shared secret is provisioned. Callers must fail
    closed (refuse to serve/query) rather than run unauthenticated."""
    if not os.path.exists(SECRET_PATH):
        return None
    with open(SECRET_PATH, "rb") as f:
        return f.read().strip()


def init_secret(force: bool = False) -> str:
    """
    Generates a new hive shared secret locally and writes it to
    ~/.sarah/hive_secret (chmod 600). This is never transmitted over the
    network - copy the resulting file to other trusted machines yourself
    (scp/USB/etc.) so they can join the same hive.
    """
    os.makedirs(SARAH_HOME, exist_ok=True)
    if os.path.exists(SECRET_PATH) and not force:
        raise FileExistsError(f"{SECRET_PATH} already exists. Pass force=True to overwrite.")
    key = secrets.token_hex(32)
    with open(SECRET_PATH, "w") as f:
        f.write(key)
    os.chmod(SECRET_PATH, 0o600)
    return key


def has_tls_cert() -> bool:
    return os.path.exists(TLS_CERT_PATH) and os.path.exists(TLS_KEY_PATH)


def init_tls_cert(force: bool = False) -> None:
    """
    Generates a single self-signed cert/key pair, shared by every hive node
    the same way the HMAC secret is: never transmitted over the network,
    copied out-of-band (scp/USB) to every machine joining the hive. Every
    node uses the *same* cert+key to both serve (present the cert) and
    verify (trust exactly that cert, nothing else) hive TLS connections -
    this mirrors the existing pre-shared-secret trust model rather than
    introducing per-node PKI/CA management.
    """
    os.makedirs(SARAH_HOME, exist_ok=True)
    if has_tls_cert() and not force:
        raise FileExistsError(
            f"{TLS_CERT_PATH} / {TLS_KEY_PATH} already exist. Pass force=True to overwrite."
        )
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", TLS_KEY_PATH, "-out", TLS_CERT_PATH,
            "-days", "3650", "-subj", "/CN=sarah-hive",
        ],
        check=True,
        capture_output=True,
    )
    os.chmod(TLS_KEY_PATH, 0o600)
    os.chmod(TLS_CERT_PATH, 0o644)
