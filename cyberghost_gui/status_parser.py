from __future__ import annotations

def classify_log_line(line: str) -> tuple[str | None, str]:
    text = line.strip()
    lower = text.lower()
    if "initialization sequence completed" in lower:
        return "connected", "Connected successfully."
    if "auth_failed" in lower:
        return "error", "Authentication failed."
    if "cannot ioctl tunsetiff" in lower or "operation not permitted" in lower:
        return "error", "Tunnel permission missing."
    if "peer connection initiated" in lower:
        return "connecting", "Secure channel established."
    if "push_reply" in lower:
        return "connecting", "Configuration received from server."
    if "inactivity timeout" in lower or "ping-restart" in lower:
        return "reconnecting", "Connection timed out, reconnecting."
    if "resolvconf" in lower and "permission denied" in lower:
        return "warning", "Connected, but DNS helper lacks permission."
    if "exiting due to fatal error" in lower:
        return "error", "OpenVPN exited with a fatal error."
    return None, text
