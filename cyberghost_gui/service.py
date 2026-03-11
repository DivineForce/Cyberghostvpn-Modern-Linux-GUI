from __future__ import annotations
import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from .config import CYBERGHOST_BIN
from .credentials import discover_credentials, write_auth_file
from .cyberghost_cli import list_cities, list_countries, list_servers
from .ipinfo import fetch_ip_info
from .models import Paths, Profile, Settings, RecentEntry, ActiveSession
from .openvpn_runner import build_command, secure_private_key, spawn_openvpn, validate_environment
from .status_parser import classify_log_line
from .store import (
    clear_active_session,
    load_active_session,
    load_cache,
    load_profiles,
    load_recents,
    load_settings,
    save_active_session,
    save_cache,
    save_profiles,
    save_recents,
    save_settings,
)

LogFn = Callable[[str], None]
StatusFn = Callable[[str, str], None]


class VpnService:
    def __init__(self, paths: Paths, logger: LogFn) -> None:
        self.paths = paths
        self.logger = logger
        self.proc: subprocess.Popen[str] | None = None
        self.cache = load_cache(paths)
        self.profiles = load_profiles(paths)
        self.settings = load_settings(paths)
        self.recents: list[RecentEntry] = load_recents(paths)
        self.connected_since: float | None = None
        self.stats_start_rx: int | None = None
        self.stats_start_tx: int | None = None
        self._proc_lock = threading.Lock()
        self._session_id = 0
        self._manual_stop_sessions: set[int] = set()
        self._last_disconnect_transient = False
        self._active_session: ActiveSession | None = load_active_session(paths)
        self._last_probe_at = 0.0

    def prepare_credentials(self) -> bool:
        creds = discover_credentials(self.paths)
        if not creds:
            self.logger("No credentials found in config.ini or token file.")
            return False
        write_auth_file(self.paths, creds)
        self.logger(f"Credentials loaded from: {creds.source} [{creds.username_key}/{creds.password_key}]")
        warning = secure_private_key(self.paths)
        if warning:
            self.logger(warning)
        return True

    def get_countries(self, force_refresh: bool = False) -> dict[str, str]:
        if self.cache.countries and not force_refresh:
            return self.cache.countries
        self.cache.countries = list_countries()
        save_cache(self.paths, self.cache)
        return self.cache.countries

    def get_cities(self, country_code: str, force_refresh: bool = False) -> list[str]:
        if country_code in self.cache.cities_by_country and not force_refresh:
            return self.cache.cities_by_country[country_code]
        cities = list_cities(country_code)
        self.cache.cities_by_country[country_code] = cities
        save_cache(self.paths, self.cache)
        return cities

    def get_servers(self, country_code: str, city: str, force_refresh: bool = False) -> list[str]:
        key = f"{country_code}:{city}"
        if key in self.cache.servers_by_city and not force_refresh:
            return self.cache.servers_by_city[key]
        servers = list_servers(country_code, city)
        self.cache.servers_by_city[key] = servers
        save_cache(self.paths, self.cache)
        return servers

    def preview_command(self, instance: str, protocol: str = "TCP", service: str = "openvpn") -> str:
        return " ".join(build_command(instance, self.paths, protocol, service))

    def get_ip_info_text(self) -> tuple[str, dict]:
        info = fetch_ip_info()
        text = f"IP: {info['ip']} | {info['city']}, {info['region']}, {info['country']}"
        if info.get("org"):
            text += f" | {info['org']}"
        return text, info

    @staticmethod
    def format_recent_label(entry: RecentEntry) -> str:
        return f"{entry.country_name} - {entry.server}"

    def add_recent(self, entry: RecentEntry) -> None:
        normalized = RecentEntry(
            country_name=entry.country_name or "Unknown",
            country_code=entry.country_code or "",
            city=entry.city or "",
            server=entry.server,
            protocol=entry.protocol or "UDP",
            service=entry.service or "openvpn",
            server_type=entry.server_type or "traffic",
            last_used=time.time(),
        )
        self.recents = [
            r
            for r in self.recents
            if not (
                r.country_code == normalized.country_code
                and r.city == normalized.city
                and r.server == normalized.server
                and r.protocol == normalized.protocol
                and r.service == normalized.service
            )
        ]
        self.recents.insert(0, normalized)
        self.recents = self.recents[:12]
        save_recents(self.paths, self.recents)

    def list_profiles(self) -> list[Profile]:
        return list(self.profiles)

    def save_profile(self, profile: Profile) -> None:
        self.profiles = [p for p in self.profiles if p.name != profile.name]
        self.profiles.append(profile)
        self.profiles.sort(key=lambda p: p.name.lower())
        save_profiles(self.paths, self.profiles)

    def delete_profile(self, name: str) -> None:
        self.profiles = [p for p in self.profiles if p.name != name]
        save_profiles(self.paths, self.profiles)

    def get_settings(self) -> Settings:
        return self.settings

    def get_uptime_seconds(self) -> int:
        if not self.connected_since:
            return 0
        return max(0, int(time.time() - self.connected_since))

    def get_tun_stats(self) -> tuple[int, int]:
        rx = 0
        tx = 0
        try:
            data = subprocess.check_output(["ip", "-s", "link", "show", "tun0"], text=True, stderr=subprocess.DEVNULL)
            lines = data.splitlines()
            for idx, line in enumerate(lines):
                if "RX:" in line and idx + 1 < len(lines):
                    nums = lines[idx + 1].split()
                    if nums:
                        rx = int(nums[0])
                if "TX:" in line and idx + 1 < len(lines):
                    nums = lines[idx + 1].split()
                    if nums:
                        tx = int(nums[0])
        except Exception:
            pass
        if self.stats_start_rx is None:
            self.stats_start_rx = rx
        if self.stats_start_tx is None:
            self.stats_start_tx = tx
        return max(0, rx - (self.stats_start_rx or 0)), max(0, tx - (self.stats_start_tx or 0))

    def update_settings(self, settings: Settings) -> None:
        self.settings = settings
        save_settings(self.paths, settings)

    def reconcile_runtime_state(self, on_line: LogFn | None = None, force_scan: bool = False) -> bool:
        now = time.time()
        if not force_scan and (now - self._last_probe_at) < 3:
            with self._proc_lock:
                if self.proc is not None and self.proc.poll() is None:
                    return True
            return self._active_session is not None
        self._last_probe_at = now

        with self._proc_lock:
            if self.proc is not None and self.proc.poll() is None:
                if self._active_session is None or self._active_session.pid != self.proc.pid:
                    self._persist_active_session(
                        pid=self.proc.pid,
                        instance=self._active_session.instance if self._active_session else "unknown",
                        protocol=self._active_session.protocol if self._active_session else self.settings.default_protocol,
                        service=self._active_session.service if self._active_session else "openvpn",
                        recent=None,
                        source="tracked",
                    )
                if on_line and force_scan:
                    on_line(f"Active tracked VPN session detected (PID {self.proc.pid}).")
                return True

        if self._active_session is not None and self._is_pid_alive(self._active_session.pid):
            if self._active_session.source != "recovered":
                self._active_session.source = "recovered"
                save_active_session(self.paths, self._active_session)
            if self.connected_since is None:
                self.connected_since = self._active_session.started_at or time.time()
            if on_line and force_scan:
                on_line(f"Active persisted VPN session detected (PID {self._active_session.pid}).")
            return True

        pid = self._detect_openvpn_pid()
        if pid is not None:
            self._adopt_external_session(pid)
            if on_line:
                on_line(f"Recovered external VPN session (PID {pid}).")
            return True

        self._clear_active_session()
        if on_line and force_scan:
            on_line("No active VPN process detected in system state.")
        return False

    def connect(self, instance: str, protocol: str, service: str, recent_entry: RecentEntry, on_line: LogFn, on_status: StatusFn, on_done: Callable[[], None]) -> None:
        errors = validate_environment(self.paths)
        if errors:
            for e in errors:
                on_line(e)
            on_status("error", "Missing required files.")
            on_done()
            return

        self.add_recent(recent_entry)
        effective_service = service.lower()
        if effective_service != "openvpn":
            on_line("WireGuard/service-type UI is present, but custom direct connection remains OpenVPN-based in this build.")
            effective_service = "openvpn"

        with self._proc_lock:
            running_proc = self.proc if self.proc and self.proc.poll() is None else None
            running_session = self._session_id if running_proc else None

        if running_proc is not None and running_session is not None:
            on_line("Existing VPN session detected. Stopping it before reconnect...")
            if not self._stop_process(running_proc, running_session, on_line):
                on_status("error", "Failed to stop current VPN session.")
                on_done()
                return
        elif self.reconcile_runtime_state(force_scan=True):
            on_line("Recovered external VPN session detected. Stopping it before reconnect...")
            if not self.stop(on_line):
                on_status("error", "Failed to stop current VPN session.")
                on_done()
                return

        self._last_disconnect_transient = False
        try:
            proc = spawn_openvpn(instance, self.paths, protocol, effective_service)
        except Exception as exc:
            on_line(f"Failed to start OpenVPN: {exc}")
            on_status("error", "Could not launch OpenVPN.")
            on_done()
            return

        with self._proc_lock:
            self._session_id += 1
            session_id = self._session_id
            self.proc = proc

        self._persist_active_session(
            pid=proc.pid,
            instance=instance,
            protocol=protocol,
            service=effective_service,
            recent=recent_entry,
            source="tracked",
        )

        def worker() -> None:
            last_state: str | None = None
            if proc.stdout is not None:
                for line in proc.stdout:
                    clean = line.rstrip()
                    on_line(clean)
                    state, msg = classify_log_line(clean)
                    if state:
                        last_state = state
                    if state == "connected":
                        self.connected_since = time.time()
                        self.stats_start_rx = None
                        self.stats_start_tx = None
                        if self._active_session is not None:
                            self._active_session.started_at = self.connected_since
                            save_active_session(self.paths, self._active_session)
                    if state and msg:
                        on_status(state, msg)
            on_line("[Disconnected]")
            was_connected = self.connected_since is not None
            manual_stop = session_id in self._manual_stop_sessions
            self._last_disconnect_transient = (
                (not manual_stop)
                and (was_connected or last_state in {"reconnecting", "connecting"})
                and last_state != "error"
            )
            self.connected_since = None
            self.stats_start_rx = None
            self.stats_start_tx = None
            with self._proc_lock:
                if self.proc is proc:
                    self.proc = None
            self._manual_stop_sessions.discard(session_id)
            self._clear_active_session()
            on_done()

        threading.Thread(target=worker, daemon=True).start()

    def stop(self, on_line: LogFn | None = None) -> bool:
        log = on_line or self.logger
        with self._proc_lock:
            proc = self.proc if self.proc and self.proc.poll() is None else None
            session_id = self._session_id if proc else None
        if proc is not None and session_id is not None:
            log("Stopping VPN connection...")
            stopped = self._stop_process(proc, session_id, log)
            if stopped:
                self._clear_active_session()
            return stopped

        if self.reconcile_runtime_state(force_scan=True):
            pid = self._active_session.pid if self._active_session is not None else None
            if pid is None:
                log("No active VPN session.")
                return True
            log(f"Stopping recovered VPN session (PID {pid})...")
            stopped = self._stop_external_pid(pid, log)
            if stopped:
                self._clear_active_session()
            return stopped

        log("No active VPN session.")
        return True

    def should_auto_reconnect(self) -> bool:
        return self._last_disconnect_transient

    def has_active_session(self) -> bool:
        return self.reconcile_runtime_state(force_scan=True)

    def get_active_session_country_code(self) -> str:
        session = self._active_session
        if session and session.country_code:
            return session.country_code
        return ""

    def recovered_session_is_healthy(self) -> bool:
        session = self._active_session
        if session is None or session.source != "recovered":
            return True
        if not self._is_pid_alive(session.pid):
            return False
        return self._has_tun_interface()

    def _stop_process(self, proc: subprocess.Popen[str], session_id: int, log: LogFn) -> bool:
        self._manual_stop_sessions.add(session_id)
        if proc.poll() is not None:
            return True
        try:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=10)
            return True
        except subprocess.TimeoutExpired:
            log("OpenVPN did not stop in time. Terminating process...")
            try:
                proc.terminate()
                proc.wait(timeout=5)
                return True
            except subprocess.TimeoutExpired:
                pass
            except Exception as exc:
                log(f"Terminate failed: {exc}")
        except Exception as exc:
            log(f"Signal SIGINT failed: {exc}")
        try:
            log("Force-killing OpenVPN process...")
            proc.kill()
            proc.wait(timeout=2)
            return True
        except Exception as exc:
            log(f"Kill failed: {exc}")
            return False

    def _stop_external_pid(self, pid: int, log: LogFn) -> bool:
        # Prefer direct process signals first; this avoids sudo-only CLI noise for recovered sessions.
        try:
            os.kill(pid, signal.SIGINT)
        except Exception:
            pass

        if self._wait_pid_exit(pid, 10):
            return True

        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass

        if self._wait_pid_exit(pid, 4):
            return True

        try:
            result = subprocess.run(
                [CYBERGHOST_BIN, "--stop"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=12,
            )
            output = (result.stdout or "").strip()
            # Ignore expected non-root warning from cyberghostvpn CLI in GUI mode.
            if output and "without sudo" not in output.lower():
                log(result.stdout.strip())
            if result.returncode == 0 and self._wait_pid_exit(pid, 8):
                return True
        except Exception:
            pass

        if not self._is_pid_alive(pid):
            return True

        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception:
            pass

        if self._wait_pid_exit(pid, 3):
            return True

        log("Could not stop recovered VPN process.")
        return False

    def _wait_pid_exit(self, pid: int, timeout_s: int) -> bool:
        end = time.time() + timeout_s
        while time.time() < end:
            if not self._is_pid_alive(pid):
                return True
            time.sleep(0.25)
        return not self._is_pid_alive(pid)

    def _is_pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except OSError:
            return False
        except Exception:
            return self._is_pid_alive_fallback(pid)

    def _is_pid_alive_fallback(self, pid: int) -> bool:
        try:
            out = subprocess.check_output(["ps", "-p", str(pid), "-o", "pid="], text=True, stderr=subprocess.DEVNULL)
            return bool(out.strip())
        except Exception:
            pass
        try:
            out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], text=True, stderr=subprocess.DEVNULL)
            return "No tasks are running" not in out
        except Exception:
            return False

    def _has_tun_interface(self) -> bool:
        try:
            result = subprocess.run(
                ["ip", "link", "show", "tun0"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=4,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _detect_openvpn_pid(self) -> int | None:
        if self._active_session is not None and self._is_pid_alive(self._active_session.pid):
            return self._active_session.pid

        try:
            out = subprocess.check_output(["pgrep", "-x", "openvpn"], text=True, stderr=subprocess.DEVNULL)
            pids = [int(line.strip()) for line in out.splitlines() if line.strip().isdigit()]
            if pids:
                return pids[0]
        except Exception:
            pass

        try:
            out = subprocess.check_output(["ps", "-eo", "pid=,comm="], text=True, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2 and parts[0].isdigit() and parts[1] in {"openvpn", "openvpn.exe"}:
                    return int(parts[0])
        except Exception:
            pass

        try:
            out = subprocess.check_output(["tasklist", "/FI", "IMAGENAME eq openvpn.exe", "/FO", "CSV", "/NH"], text=True, stderr=subprocess.DEVNULL)
            for raw in out.splitlines():
                line = raw.strip().strip('"')
                if not line or line.startswith("INFO:"):
                    continue
                cols = [c.strip('"') for c in raw.split(",")]
                if len(cols) >= 2 and cols[1].isdigit():
                    return int(cols[1])
        except Exception:
            pass

        return None

    def _persist_active_session(
        self,
        pid: int,
        instance: str,
        protocol: str,
        service: str,
        recent: RecentEntry | None,
        source: str,
    ) -> None:
        session = ActiveSession(
            pid=pid,
            instance=instance,
            protocol=protocol,
            service=service,
            country_name=recent.country_name if recent else (self._active_session.country_name if self._active_session else "Unknown"),
            country_code=recent.country_code if recent else (self._active_session.country_code if self._active_session else ""),
            city=recent.city if recent else (self._active_session.city if self._active_session else ""),
            server_type=recent.server_type if recent else (self._active_session.server_type if self._active_session else "traffic"),
            started_at=time.time(),
            source=source,
        )
        self._active_session = session
        save_active_session(self.paths, session)

    def _adopt_external_session(self, pid: int) -> None:
        now = time.time()
        current = self._active_session
        session = ActiveSession(
            pid=pid,
            instance=current.instance if current else "unknown",
            protocol=current.protocol if current else self.settings.default_protocol,
            service="openvpn",
            country_name=current.country_name if current else "Unknown",
            country_code=current.country_code if current else "",
            city=current.city if current else "",
            server_type=current.server_type if current else "traffic",
            started_at=current.started_at if current and current.started_at else now,
            source="recovered",
        )
        self._active_session = session
        if self.connected_since is None:
            self.connected_since = session.started_at
        save_active_session(self.paths, session)

    def _clear_active_session(self) -> None:
        self._active_session = None
        self.connected_since = None
        self.stats_start_rx = None
        self.stats_start_tx = None
        clear_active_session(self.paths)
