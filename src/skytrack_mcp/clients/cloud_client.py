"""SkyTrack Cloud BFF API client: authentication decryption, projects, and missions."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from skytrack_mcp.config import CLIENT_DATA_DIR

CLOUD_BFF_URL = "https://platform.getskytrack.com"


def get_macos_machine_id() -> str:
    """Retrieve macOS IOPlatformUUID via ioreg."""
    try:
        res = subprocess.check_output(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            text=True,
            timeout=5.0,
        )
        match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', res)
        if match:
            return match.group(1).lower().strip()
        # Fallback split
        raw = res.split("IOPlatformUUID")[1].split("\n")[0]
        return re.sub(r'[\s="]', "", raw).lower().strip()
    except Exception as exc:
        raise RuntimeError(f"Failed to get macOS machine id: {exc}")


def get_token_encryption_key() -> bytes:
    """Derive AES-256 key: SHA256(SHA256(IOPlatformUUID).hexdigest())."""
    uuid_str = get_macos_machine_id()
    first_hash = hashlib.sha256(uuid_str.encode("utf-8")).hexdigest()
    return hashlib.sha256(first_hash.encode("utf-8")).digest()


def decrypt_client_data_file(file_path: Path) -> str:
    """Decrypt an encrypted file (.token or .csrf) from ClientData."""
    if not file_path.exists():
        return ""
    raw = file_path.read_text(encoding="utf-8").strip()
    if raw.startswith("PLAINTEXT:"):
        return re.sub(r"[^\x20-\x7E]", "", raw[10:]).strip()
    if raw.startswith("ENCRYPTED:"):
        enc = re.sub(r"[^\x20-\x7E]", "", raw[10:]).strip()
        if ":" not in enc:
            return ""
        iv_hex, cipher_hex = enc.split(":", 1)
        key = get_token_encryption_key()
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(bytes.fromhex(iv_hex)),
            backend=default_backend(),
        )
        decryptor = cipher.decryptor()
        padded = decryptor.update(bytes.fromhex(cipher_hex)) + decryptor.finalize()
        pad_len = padded[-1]
        if 1 <= pad_len <= 16:
            return padded[:-pad_len].decode("utf-8", errors="ignore")
        return padded.decode("utf-8", errors="ignore")
    return raw


def get_cloud_auth_credentials(client_data_dir: Path = CLIENT_DATA_DIR) -> Dict[str, str]:
    """Retrieve access token and csrf token from ClientData."""
    access_token = decrypt_client_data_file(client_data_dir / ".token")
    csrf_token = decrypt_client_data_file(client_data_dir / ".csrf")
    return {
        "access_token": access_token,
        "csrf_token": csrf_token,
    }


def call_cloud_api(
    endpoint: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    client_data_dir: Path = CLIENT_DATA_DIR,
) -> Dict[str, Any]:
    """Call SkyTrack Cloud BFF API (https://platform.getskytrack.com)."""
    creds = get_cloud_auth_credentials(client_data_dir)
    access_token = creds["access_token"]
    csrf_token = creds["csrf_token"]

    if not access_token or not csrf_token:
        raise ValueError("SkyTrack credentials not found or could not be decrypted from ClientData.")

    url = f"{CLOUD_BFF_URL}{endpoint}"
    if params:
        query_str = urllib.parse.urlencode(params)
        url = f"{url}?{query_str}"

    headers = {
        "X-Csrf-Token": csrf_token,
        "X-Onboarding-Plan": "",
        "Cookie": f"iam_access_token={access_token};uav_platform_csrf_token={csrf_token}",
        "User-Agent": "SkyTrack/0.9.35",
        "Accept": "application/json",
    }

    data_bytes = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as err:
        err_msg = err.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Cloud API {method} {endpoint} failed ({err.code}): {err_msg}")


def list_cloud_projects(client_data_dir: Path = CLIENT_DATA_DIR) -> List[Dict[str, Any]]:
    """List all projects for the current user from SkyTrack Cloud."""
    return call_cloud_api(
        "/api/v1/projects",
        method="GET",
        params={
            "offset": 0,
            "limit": 100,
            "sort_field": "updated_at",
            "sort_direction": "desc",
        },
        client_data_dir=client_data_dir,
    )


def create_cloud_mission(
    name: str,
    project_id: str,
    world: str = "default",
    actions: Optional[List[Dict[str, Any]]] = None,
    client_data_dir: Path = CLIENT_DATA_DIR,
) -> Dict[str, Any]:
    """Create a new mission on SkyTrack Cloud so it displays on SkyTrack App UI."""
    payload = {
        "name": name,
        "projectId": project_id,
        "commands": {
            "world": world,
            "waypoints": [],
            "actions": actions or [],
        },
        "type": "private",
    }
    return call_cloud_api(
        "/api/v1/user/missions",
        method="POST",
        body=payload,
        client_data_dir=client_data_dir,
    )


def update_cloud_mission(
    mission_id: str,
    name: Optional[str] = None,
    world: Optional[str] = None,
    actions: Optional[List[Dict[str, Any]]] = None,
    spawn_location: Optional[List[float]] = None,
    client_data_dir: Path = CLIENT_DATA_DIR,
) -> Dict[str, Any]:
    """Update a mission's commands and actions on SkyTrack Cloud."""
    commands: Dict[str, Any] = {}
    if world is not None:
        commands["world"] = world
    if actions is not None:
        commands["actions"] = actions
    if spawn_location is not None:
        commands["spawn"] = spawn_location

    payload: Dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if commands:
        payload["commands"] = commands

    return call_cloud_api(
        f"/api/v1/user/missions/{mission_id}",
        method="PATCH",
        body=payload,
        client_data_dir=client_data_dir,
    )
