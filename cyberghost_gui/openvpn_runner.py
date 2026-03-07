from __future__ import annotations
import os
import shutil
import subprocess
from .config import OPENVPN_BIN
from .models import Paths

def validate_environment(paths: Paths) -> list[str]:
    errors = []
    if shutil.which(OPENVPN_BIN) is None:
        errors.append(f"OpenVPN binary not found: {OPENVPN_BIN}")
    for path in (paths.ca_cert, paths.client_cert, paths.client_key, paths.auth_file):
        if not path.exists():
            errors.append(f"Missing required file: {path}")
    return errors

def secure_private_key(paths: Paths) -> str | None:
    if not paths.client_key.exists():
        return None
    try:
        os.chmod(paths.client_key, 0o600)
        return None
    except PermissionError:
        return f"Could not chmod {paths.client_key}. Permissions may already be fine."

def build_command(instance: str, paths: Paths, protocol: str = "TCP", service: str = "openvpn") -> list[str]:
    proto = "udp" if protocol.upper() == "UDP" else "tcp"
    port = "443"
    # Known-good custom engine is OpenVPN. WireGuard is surfaced in UI but not yet custom-implemented.
    return [
        OPENVPN_BIN,
        "--client",
        "--remote", f"{instance}.cg-dialup.net", port,
        "--dev", "tun",
        "--proto", proto,
        "--auth-user-pass", str(paths.auth_file),
        "--auth-nocache",
        "--resolv-retry", "infinite",
        "--persist-tun",
        "--nobind",
        "--data-ciphers", "AES-256-GCM:AES-128-GCM:AES-256-CBC",
        "--data-ciphers-fallback", "AES-256-CBC",
        "--auth", "SHA256",
        "--ping", "5",
        "--ping-restart", "30",
        "--script-security", "2",
        "--remote-cert-tls", "server",
        "--route-delay", "5",
        "--verb", "4",
        "--ca", str(paths.ca_cert),
        "--cert", str(paths.client_cert),
        "--key", str(paths.client_key),
    ]

def spawn_openvpn(instance: str, paths: Paths, protocol: str = "TCP", service: str = "openvpn") -> subprocess.Popen[str]:
    return subprocess.Popen(build_command(instance, paths, protocol, service), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
