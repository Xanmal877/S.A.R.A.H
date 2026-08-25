import time


class PeerRegistry:
    """
    Tracks currently-known hive peers (populated by HiveDiscovery). This is
    the allowlist source for anything that treats "known hive peer" as a
    trust boundary - e.g. modules/system/remote_shell.py refuses to SSH
    into a host that isn't in here.
    """

    def __init__(self):
        self._peers = {}  # name -> {"host":..., "port":..., "last_seen":...}

    def update(self, name: str, host: str, port: int):
        self._peers[name] = {"host": host, "port": port, "last_seen": time.time()}

    def remove(self, name: str):
        self._peers.pop(name, None)

    def all(self) -> dict:
        return dict(self._peers)

    def known_hosts(self) -> set:
        return {p["host"] for p in self._peers.values()}


peer_registry = PeerRegistry()
