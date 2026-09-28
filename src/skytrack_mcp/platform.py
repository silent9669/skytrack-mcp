"""Platform discovery and cross-platform abstractions for SkyTrack MCP.

Provides OS-aware resolution for:
- SkyTrack Desktop ClientData directory (macOS, Linux XDG, Windows)
- Hardware machine identifier for token decryption without hardcoding macOS ioreg
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

LINUX_MACHINE_ID_PATHS: list[Path] = [
    Path("/etc/machine-id"),
    Path("/var/lib/dbus/machine-id"),
]


def get_default_client_data_dir() -> Path:
    """Return the platform-specific default ClientData path.

    Can always be overridden via the SKYTRACK_CLIENT_DATA environment variable.
    """
    env_override = os.environ.get("SKYTRACK_CLIENT_DATA")
    if env_override:
        return Path(env_override)

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SkyTrack" / "ClientData"

    if sys.platform.startswith("linux"):
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            return Path(xdg_config) / "SkyTrack" / "ClientData"
        return Path.home() / ".config" / "SkyTrack" / "ClientData"

    # Windows / other fallback
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SkyTrack" / "ClientData"
    return Path.home() / ".config" / "SkyTrack" / "ClientData"


def get_platform_machine_id() -> str:
    """Retrieve platform machine identifier for token key derivation.

    - On macOS: parses IOPlatformUUID via ioreg
    - On Linux: reads /etc/machine-id or /var/lib/dbus/machine-id
    - Fallback: deterministic MAC-derived node identifier
    """
    if sys.platform == "darwin":
        try:
            res = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                text=True,
                timeout=5.0,
            )
            match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', res)
            if match:
                return match.group(1).lower().strip()
            raw = res.split("IOPlatformUUID")[1].split("\n")[0]
            return re.sub(r'[\s="]', "", raw).lower().strip()
        except (subprocess.SubprocessError, OSError, UnicodeDecodeError):
            pass

    if sys.platform.startswith("linux"):
        for path in LINUX_MACHINE_ID_PATHS:
            try:
                if path.exists():
                    val = path.read_text(encoding="utf-8").strip()
                    if val:
                        return val.lower()
            except (OSError, UnicodeDecodeError):
                continue

    # Deterministic fallback when OS-level hardware ID query fails
    node = uuid.getnode()
    return f"fallback-node-{node:012x}"


def derive_token_encryption_key(machine_id: str | None = None) -> bytes:
    """Derive AES-256 key: SHA256(SHA256(machine_id).hexdigest())."""
    mid = machine_id or get_platform_machine_id()
    first_hash = hashlib.sha256(mid.encode("utf-8")).hexdigest()
    return hashlib.sha256(first_hash.encode("utf-8")).digest()
