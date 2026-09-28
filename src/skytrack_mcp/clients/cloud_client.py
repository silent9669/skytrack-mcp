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
from skytrack_mcp.platform import derive_token_encryption_key, get_platform_machine_id

CLOUD_BFF_URL = "https://platform.getskytrack.com"


def get_macos_machine_id() -> str:
    """Retrieve platform machine identifier (retained name for backward compatibility)."""
    return get_platform_machine_id()


def get_token_encryption_key() -> bytes:
    """Derive AES-256 key: SHA256(SHA256(machine_id).hexdigest())."""
    return derive_token_encryption_key()


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
        try:
            iv_hex, cipher_hex = enc.split(":", 1)
            if not iv_hex or not cipher_hex:
                return ""
            key = get_token_encryption_key()
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(bytes.fromhex(iv_hex)),
                backend=default_backend(),
            )
            decryptor = cipher.decryptor()
            padded = decryptor.update(bytes.fromhex(cipher_hex)) + decryptor.finalize()
            if not padded:
                return ""
            pad_len = padded[-1]
            if 1 <= pad_len <= 16:
                return padded[:-pad_len].decode("utf-8", errors="ignore")
            return padded.decode("utf-8", errors="ignore")
        except (ValueError, TypeError, OSError, RuntimeError, IndexError):
            return ""
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


def build_cloud_commands_v2(
    world: str = "default",
    vehicle: str = "x500_livox_mid_360",
    actions: Optional[List[Dict[str, Any]]] = None,
    spawn_location: Optional[List[float]] = None,
    takeoff_altitude: float = 2.5,
    target_speed: float = 2.0,
    safety_option: str = "avoid",
    end_action: str = "rtl",
) -> Dict[str, Any]:
    """Construct the full SkyTrack Cloud commands + v2 (client, mc, metadata) payload."""
    import datetime
    import uuid

    ui_actions: List[Dict[str, Any]] = []
    mc_actions: List[Dict[str, Any]] = []

    for act in actions or []:
        act_type = str(act.get("type", "navigate"))
        if act_type in ("navigate", "navigation", "waypoint") or ("x" in act and "y" in act):
            if "data" in act and isinstance(act["data"], list) and len(act["data"]) >= 3:
                coords = [float(act["data"][0]), float(act["data"][1]), float(act["data"][2])]
            else:
                coords = [
                    float(act.get("x", 0.0)),
                    float(act.get("y", 0.0)),
                    float(act.get("z", takeoff_altitude)),
                ]
            act_id = str(act.get("id") or uuid.uuid4())
            ui_actions.append({"id": act_id, "type": "navigate", "data": coords})
            mc_actions.append(
                {
                    "id": act_id,
                    "type": "navigation",
                    "frame": "enu",
                    "x": coords[0],
                    "y": coords[1],
                    "z": coords[2],
                    "targetSpeed": float(act.get("targetSpeed", target_speed)),
                }
            )
            after = act.get("after_action")
            if after:
                sub_id = str(uuid.uuid4())
                ui_actions.append({"id": sub_id, "type": after})
                if after == "drop-ball":
                    mc_actions.append({"id": sub_id, "type": "drop_payload"})
                elif after == "take-snapshot":
                    mc_actions.append({"id": sub_id, "type": "camera_trigger", "operation": "snapshot"})
                elif after == "start-recording-video":
                    mc_actions.append({"id": sub_id, "type": "camera_trigger", "operation": "recording_on"})
                elif after == "stop-recording-video":
                    mc_actions.append({"id": sub_id, "type": "camera_trigger", "operation": "recording_off"})
        else:
            act_id = str(act.get("id") or uuid.uuid4())
            ui_actions.append({"id": act_id, "type": act_type, **({"data": act["data"]} if "data" in act else {})})
            if act_type == "drop-ball":
                mc_actions.append({"id": act_id, "type": "drop_payload"})
            elif act_type == "take-snapshot":
                mc_actions.append({"id": act_id, "type": "camera_trigger", "operation": "snapshot"})
            elif act_type == "start-recording-video":
                mc_actions.append({"id": act_id, "type": "camera_trigger", "operation": "recording_on"})
            elif act_type == "stop-recording-video":
                mc_actions.append({"id": act_id, "type": "camera_trigger", "operation": "recording_off"})

    mc_actions.append({"id": "end-rtl", "type": end_action})
    spawn = [float(v) for v in (spawn_location or [0.0, 0.0, 0.0])[:3]]

    top_actions = [*ui_actions, {"id": "end-rtl", "type": end_action}]
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    return {
        "world": world,
        "spawn": spawn,
        "waypoints": [],
        "actions": top_actions,
        "v2": {
            "client": {
                "avoidZones": [],
                "sequences": [
                    {
                        "id": f"seq-{world}-route",
                        "type": "route",
                        "targetSpeed": float(target_speed),
                        "actions": ui_actions,
                    }
                ],
                "spawnLocation": spawn,
            },
            "mc": {
                "actions": mc_actions,
                "settings": {
                    "avoidanceMode": safety_option,
                    "noFlyZones": [],
                    "smart": True,
                    "takeoffAltitude": float(takeoff_altitude),
                },
            },
            "metadata": {
                "codeMode": False,
                "end": {"id": "end-rtl", "type": end_action},
                "lastSync": now_iso,
                "safetyOption": safety_option,
                "takeoffAltitude": float(takeoff_altitude),
                "vehicle": {"name": vehicle, "tags": ["camera", "firefighting-balls"]},
                "world": {"name": world, "tags": ["general"]},
            },
        },
    }


def create_cloud_mission(
    name: str,
    project_id: str,
    world: str = "default",
    vehicle: str = "x500_livox_mid_360",
    actions: Optional[List[Dict[str, Any]]] = None,
    spawn_location: Optional[List[float]] = None,
    takeoff_altitude: float = 2.5,
    target_speed: float = 2.0,
    client_data_dir: Path = CLIENT_DATA_DIR,
) -> Dict[str, Any]:
    """Create a new mission on SkyTrack Cloud with full v2 schema so it displays on SkyTrack App UI."""
    commands = build_cloud_commands_v2(
        world=world,
        vehicle=vehicle,
        actions=actions or [],
        spawn_location=spawn_location or [0.0, 0.0, 0.0],
        takeoff_altitude=takeoff_altitude,
        target_speed=target_speed,
    )
    payload = {
        "name": name,
        "projectId": project_id.removeprefix("prj-"),
        "commands": commands,
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
    vehicle: Optional[str] = None,
    actions: Optional[List[Dict[str, Any]]] = None,
    spawn_location: Optional[List[float]] = None,
    takeoff_altitude: float = 2.5,
    target_speed: float = 2.0,
    safety_option: str = "avoid",
    end_action: str = "rtl",
    client_data_dir: Path = CLIENT_DATA_DIR,
) -> Dict[str, Any]:
    """Update a mission's full commands and v2 structure on SkyTrack Cloud."""
    clean_id = mission_id.removeprefix("mis-")
    commands = build_cloud_commands_v2(
        world=world or "default",
        vehicle=vehicle or "x500_livox_mid_360",
        actions=actions or [],
        spawn_location=spawn_location or [0.0, 0.0, 0.0],
        takeoff_altitude=takeoff_altitude,
        target_speed=target_speed,
        safety_option=safety_option,
        end_action=end_action,
    )
    payload: Dict[str, Any] = {"commands": commands}
    if name is not None:
        payload["name"] = name

    return call_cloud_api(
        f"/api/v1/user/missions/{clean_id}",
        method="PATCH",
        body=payload,
        client_data_dir=client_data_dir,
    )
