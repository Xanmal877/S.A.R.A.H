import ssl

from .config import TLS_CERT_PATH, TLS_KEY_PATH, has_tls_cert


def server_context() -> ssl.SSLContext | None:
    """TLS context for HiveServer. None if no cert is provisioned - callers
    must fail closed (refuse to listen) rather than ever serve plaintext."""
    if not has_tls_cert():
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=TLS_CERT_PATH, keyfile=TLS_KEY_PATH)
    return ctx


def client_context() -> ssl.SSLContext | None:
    """TLS context for connecting out to another hive node. Trusts exactly
    the one shared self-signed cert (not a CA, not the system trust store)
    since every node presents the same cert - hostname/IP verification is
    meaningless here and is intentionally disabled."""
    if not has_tls_cert():
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cafile=TLS_CERT_PATH)
    return ctx
