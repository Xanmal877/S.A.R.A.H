import asyncio
import logging
import socket
import ssl

from zeroconf import ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from .config import load_secret
from .peer_registry import peer_registry
from .protocol import ProtocolError, decode_message, encode_message
from .tls import client_context

logger = logging.getLogger("HiveDiscovery")

SERVICE_TYPE = "_sarah-hive._tcp.local."


def _local_ip() -> str:
    # Doesn't actually send anything - just asks the OS which local
    # interface would be used to reach an external address, to find our
    # LAN-facing IP (works even without real internet access).
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())
    finally:
        s.close()


class HiveDiscovery:
    """
    Advertises this node on the LAN via mDNS and keeps `peer_registry`
    updated with every other Sarah hive node it discovers. Every node runs
    this (see agents/baseAgent.py) regardless of role - "core" vs "peer"
    only changes whether a node additionally *polls* discovered peers for
    info (see HiveCore).
    """

    def __init__(self, node_name: str, port: int):
        self.node_name = node_name
        self.port = port
        self.aiozc = None
        self.browser = None
        self.service_info = None
        self.secret = load_secret()

    async def start(self):
        self.aiozc = AsyncZeroconf()
        local_ip = _local_ip()
        self.service_info = AsyncServiceInfo(
            SERVICE_TYPE,
            f"{self.node_name}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(local_ip)],
            port=self.port,
            properties={"node": self.node_name},
        )
        await self.aiozc.async_register_service(self.service_info)
        self.browser = AsyncServiceBrowser(
            self.aiozc.zeroconf, SERVICE_TYPE, handlers=[self._on_change]
        )
        logger.info(f"Hive discovery started as '{self.node_name}' at {local_ip}:{self.port}")

    def _on_change(self, zeroconf, service_type, name, state_change):
        asyncio.ensure_future(self._handle_change(zeroconf, service_type, name, state_change))

    async def _handle_change(self, zeroconf, service_type, name, state_change):
        if self.service_info and name == self.service_info.name:
            return  # ignore our own advertisement

        if state_change in (ServiceStateChange.Added, ServiceStateChange.Updated):
            info = AsyncServiceInfo(service_type, name)
            ok = await info.async_request(zeroconf, 3000)
            if ok and info.addresses:
                host = socket.inet_ntoa(info.addresses[0])
                props = info.properties or {}
                peer_name = props.get(b"node", name.encode()).decode()
                if not await self._verify_peer(host, info.port):
                    logger.warning(
                        f"Ignoring mDNS announcement for '{peer_name}' at {host}:{info.port} - "
                        "failed authenticated ping (not a real hive peer, or missing/mismatched secret)"
                    )
                    return
                peer_registry.update(peer_name, host, info.port)
                logger.info(f"Discovered hive peer '{peer_name}' at {host}:{info.port}")
        elif state_change == ServiceStateChange.Removed:
            peer_name = name[: -len("." + SERVICE_TYPE)] if name.endswith(SERVICE_TYPE) else name
            peer_registry.remove(peer_name)

    async def _verify_peer(self, host: str, port: int) -> bool:
        """Proves the announcer actually holds the shared hive secret before
        it's added to peer_registry - mDNS itself is unauthenticated, so
        without this any device on the LAN could announce as a hive node
        and land in the trust boundary modules/system/remote_shell.py reads
        for its SSH-target allowlist."""
        if not self.secret:
            return False
        ssl_ctx = client_context()
        if not ssl_ctx:
            return False
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ssl_ctx), timeout=3
            )
        except (OSError, asyncio.TimeoutError, ssl.SSLError):
            return False
        try:
            writer.write(encode_message(self.secret, "ping"))
            await writer.drain()
            raw = await asyncio.wait_for(reader.readline(), timeout=3)
            envelope = decode_message(self.secret, raw)
            return envelope.get("data", {}).get("status") == "ok"
        except (ProtocolError, asyncio.TimeoutError, OSError, ssl.SSLError):
            return False
        finally:
            writer.close()

    async def stop(self):
        if self.browser:
            await self.browser.async_cancel()
        if self.aiozc:
            if self.service_info:
                await self.aiozc.async_unregister_service(self.service_info)
            await self.aiozc.async_close()
