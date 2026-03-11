from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .assets import ensure_app_icon, ensure_flag_png
from .config import APP_TITLE
from .models import Profile, RecentEntry, Settings
from .service import VpnService

BG = "#08121f"
PANEL = "#0f1d32"
PANEL_ALT = "#13253f"
FG = "#e2e8f0"
MUTED = "#94a3b8"
ACCENT = "#0ea5e9"
SUCCESS = "#22c55e"
WARN = "#f59e0b"
ERROR = "#ef4444"


class SignalBus(QObject):
    invoke = Signal(object)
    log_line = Signal(str)
    status = Signal(str, str)
    ip_ok = Signal(dict)
    ip_error = Signal(str)
    countries_loaded = Signal(dict)
    countries_error = Signal(str)
    cities_loaded = Signal(str, list)
    cities_error = Signal(str)
    servers_loaded = Signal(str, list)
    servers_error = Signal(str)
    flag_ready = Signal(str)


class CyberGhostUI(QMainWindow):
    def __init__(self, service: VpnService) -> None:
        super().__init__()
        self.service = service
        self.bus = SignalBus()

        self.countries: dict[str, str] = {}
        self.selected_country_code = ""
        self.last_info: dict = {}
        self._country_loading = False
        self._city_loading = False
        self._state_probe_tick = 0

        self._wire_signals()
        self._build_ui()

        ensure_app_icon(self.service.paths.icon_file)
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(QIcon(str(self.service.paths.icon_file)))
        self.resize(1320, 900)
        self.setMinimumSize(1150, 820)

        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._tick_connection_stats)
        self._stats_timer.start(1000)

        QTimer.singleShot(50, self._bootstrap)

    def _wire_signals(self) -> None:
        self.bus.invoke.connect(lambda fn: fn())
        self.bus.log_line.connect(self._append)
        self.bus.status.connect(self._set_badge)
        self.bus.ip_ok.connect(self._apply_ip_info)
        self.bus.ip_error.connect(lambda err: self._append(f"IP lookup error: {err}"))
        self.bus.countries_loaded.connect(self._apply_countries)
        self.bus.countries_error.connect(lambda err: self._load_countries_failed(err))
        self.bus.cities_loaded.connect(self._apply_cities)
        self.bus.cities_error.connect(lambda err: self._cities_failed(err))
        self.bus.servers_loaded.connect(self._apply_servers)
        self.bus.servers_error.connect(lambda err: self._servers_failed(err))
        self.bus.flag_ready.connect(self._apply_flag)

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        title = QLabel("CyberGhost Modern")
        title.setStyleSheet("font-size: 30px; font-weight: 700; color: #f8fafc;")
        subtitle = QLabel("Qt UI with the same backend engine and recovery-aware sessions")
        subtitle.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)

        status_card = QFrame()
        status_card.setObjectName("statusCard")
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(14, 14, 14, 14)
        status_layout.setSpacing(16)

        self.badge = QLabel("READY")
        self.badge.setStyleSheet("padding: 6px 10px; border-radius: 8px; background: #334155; color: white; font-weight: 700;")
        self.flag_label = QLabel("")
        self.flag_label.setFixedWidth(46)
        self.flag_label.setAlignment(Qt.AlignCenter)

        self.server_var = QLabel("Server: -")
        self.server_var.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.ip_var = QLabel("IP: Unknown")
        self.location_var = QLabel("Location: Unknown")
        self.detail_var = QLabel("Idle")
        self.uptime_var = QLabel("Uptime: 00:00:00")
        self.traffic_var = QLabel("Traffic: down 0 B  up 0 B")

        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        info_col.addWidget(self.server_var)
        info_col.addWidget(self.ip_var)
        info_col.addWidget(self.location_var)
        info_col.addWidget(self.detail_var)
        info_col.addWidget(self.uptime_var)
        info_col.addWidget(self.traffic_var)

        status_layout.addWidget(self.badge, 0, Qt.AlignTop)
        status_layout.addWidget(self.flag_label, 0, Qt.AlignTop)
        status_layout.addLayout(info_col, 1)

        root_layout.addWidget(status_card)

        body = QHBoxLayout()
        body.setSpacing(14)

        left = QFrame()
        left.setObjectName("leftPanel")
        left.setFixedWidth(370)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(8)

        quick_title = QLabel("Quick Connect")
        quick_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        left_layout.addWidget(quick_title)

        self.country_combo = QComboBox()
        self.country_combo.setEditable(True)
        self.country_combo.activated.connect(self._on_country_activated)
        self.country_combo.lineEdit().editingFinished.connect(self._on_country_edit_finished)
        self.country_combo.lineEdit().returnPressed.connect(self._on_country_edit_finished)

        self.city_combo = QComboBox()
        self.city_combo.setEditable(True)
        self.city_combo.currentTextChanged.connect(self._on_city_text)

        self.server_combo = QComboBox()
        self.server_combo.setEditable(True)
        self.server_combo.currentTextChanged.connect(self._on_server_text)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["TCP", "UDP"])
        self.protocol_combo.setCurrentText(self.service.get_settings().default_protocol or "UDP")
        self.protocol_combo.currentTextChanged.connect(self._on_server_text)

        self.service_combo = QComboBox()
        self.service_combo.addItems(["openvpn"])
        self.service_combo.setCurrentText("openvpn")
        self.service_combo.currentTextChanged.connect(self._on_server_text)

        self.server_type_combo = QComboBox()
        self.server_type_combo.addItems(["traffic", "streaming", "torrent"])
        self.server_type_combo.setCurrentText(self.service.get_settings().default_server_type or "traffic")

        form = QFormLayout()
        form.addRow("Country", self.country_combo)
        form.addRow("City", self.city_combo)
        form.addRow("Server", self.server_combo)
        form.addRow("Protocol", self.protocol_combo)
        form.addRow("VPN Service", self.service_combo)
        form.addRow("Server Type", self.server_type_combo)
        left_layout.addLayout(form)

        self.quick_btn = QPushButton("Quick Connect")
        self.quick_btn.clicked.connect(self._quick_connect)
        self.connect_btn = QPushButton("Connect Selected")
        self.connect_btn.setEnabled(False)
        self.connect_btn.clicked.connect(self._connect)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        self.refresh_btn = QPushButton("Refresh Servers")
        self.refresh_btn.clicked.connect(lambda: self._load_countries(True))
        self.ip_btn = QPushButton("Check IP")
        self.ip_btn.clicked.connect(self._check_ip)

        left_layout.addWidget(self.quick_btn)
        left_layout.addWidget(self.connect_btn)
        left_layout.addWidget(self.stop_btn)
        left_layout.addWidget(self.refresh_btn)
        left_layout.addWidget(self.ip_btn)

        left_layout.addWidget(QLabel("Recent Servers"))
        self.recents_list = QListWidget()
        self.recents_list.itemDoubleClicked.connect(self._connect_recent)
        left_layout.addWidget(self.recents_list, 1)

        tabs = QTabWidget()

        dashboard = QWidget()
        dash_layout = QVBoxLayout(dashboard)
        dash_layout.addWidget(QLabel("Command Preview"))
        self.command_box = QPlainTextEdit()
        self.command_box.setReadOnly(True)
        self.command_box.setMaximumHeight(120)
        dash_layout.addWidget(self.command_box)
        logs_row = QHBoxLayout()
        logs_row.addWidget(QLabel("Connection Logs"))
        self.clear_logs_btn = QPushButton("Clear Logs")
        self.clear_logs_btn.clicked.connect(self._clear_logs)
        logs_row.addStretch(1)
        logs_row.addWidget(self.clear_logs_btn)
        dash_layout.addLayout(logs_row)
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        dash_layout.addWidget(self.log_box, 1)
        tabs.addTab(dashboard, "Dashboard")

        profiles_tab = QWidget()
        profiles_layout = QVBoxLayout(profiles_tab)
        profiles_layout.addWidget(QLabel("Saved Profiles"))
        self.profiles_list = QListWidget()
        self.profiles_list.itemDoubleClicked.connect(self._apply_profile)
        profiles_layout.addWidget(self.profiles_list)

        pbtns = QHBoxLayout()
        save_profile_btn = QPushButton("Save Current")
        save_profile_btn.clicked.connect(self._save_profile)
        apply_profile_btn = QPushButton("Apply")
        apply_profile_btn.clicked.connect(self._apply_profile)
        del_profile_btn = QPushButton("Delete")
        del_profile_btn.clicked.connect(self._delete_profile)
        pbtns.addWidget(save_profile_btn)
        pbtns.addWidget(apply_profile_btn)
        pbtns.addWidget(del_profile_btn)
        profiles_layout.addLayout(pbtns)
        tabs.addTab(profiles_tab, "Profiles")

        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)

        s = self.service.get_settings()
        self.autoconnect_var = QCheckBox("Autoconnect last profile on startup")
        self.autoconnect_var.setChecked(s.autoconnect_last_profile)
        self.stop_on_exit_var = QCheckBox("Stop VPN when closing app")
        self.stop_on_exit_var.setChecked(s.stop_vpn_on_exit)
        self.hide_logs_var = QCheckBox("Hide logs by default")
        self.hide_logs_var.setChecked(s.hide_logs_by_default)
        self.refresh_cache_var = QCheckBox("Refresh server cache on start")
        self.refresh_cache_var.setChecked(s.refresh_cache_on_start)
        self.auto_reconnect_var = QCheckBox("Auto reconnect if VPN drops")
        self.auto_reconnect_var.setChecked(getattr(s, "auto_reconnect", True))
        self.kill_switch_var = QCheckBox("Kill switch (experimental)")
        self.kill_switch_var.setChecked(getattr(s, "kill_switch", False))

        self.settings_protocol = QComboBox()
        self.settings_protocol.addItems(["TCP", "UDP"])
        self.settings_protocol.setCurrentText(s.default_protocol or "UDP")

        self.settings_service = QComboBox()
        self.settings_service.addItems(["openvpn"])
        self.settings_service.setCurrentText("openvpn")

        self.settings_server_type = QComboBox()
        self.settings_server_type.addItems(["traffic", "streaming", "torrent"])
        self.settings_server_type.setCurrentText(s.default_server_type or "traffic")

        settings_layout.addWidget(self.autoconnect_var)
        settings_layout.addWidget(self.stop_on_exit_var)
        settings_layout.addWidget(self.hide_logs_var)
        settings_layout.addWidget(self.refresh_cache_var)
        settings_layout.addWidget(self.auto_reconnect_var)
        settings_layout.addWidget(self.kill_switch_var)

        settings_form = QFormLayout()
        settings_form.addRow("Default Protocol", self.settings_protocol)
        settings_form.addRow("Default Service", self.settings_service)
        settings_form.addRow("Default Server Type", self.settings_server_type)
        settings_layout.addLayout(settings_form)

        save_settings_btn = QPushButton("Save Settings")
        save_settings_btn.clicked.connect(self._save_settings)
        settings_layout.addWidget(save_settings_btn)
        settings_layout.addStretch(1)

        tabs.addTab(settings_tab, "Settings")

        body.addWidget(left)
        body.addWidget(tabs, 1)
        root_layout.addLayout(body, 1)

        self.setStyleSheet(
            f"""
            QWidget {{ background: {BG}; color: {FG}; font-family: 'Segoe UI'; font-size: 13px; }}
            QLabel, QCheckBox {{ background: transparent; }}
            QFrame#statusCard {{ background: {PANEL_ALT}; border: 1px solid #24334d; border-radius: 12px; }}
            QFrame#leftPanel {{ background: {PANEL}; border: 1px solid #1f2c45; border-radius: 12px; }}
            QComboBox, QPlainTextEdit, QListWidget {{
                background: #0a1730;
                border: 1px solid #223350;
                border-radius: 8px;
                padding: 6px;
            }}
            QPushButton {{
                background: #123257;
                border: 1px solid #1d4572;
                border-radius: 8px;
                padding: 8px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #185087; }}
            QPushButton:disabled {{ background: #1f2937; color: #64748b; border-color: #334155; }}
            QTabWidget::pane {{ border: 1px solid #1f2c45; border-radius: 10px; background: {PANEL_ALT}; }}
            QTabBar::tab {{ background: #17263c; padding: 10px 14px; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 4px; }}
            QTabBar::tab:selected {{ background: #224067; }}
            """
        )

    def run(self) -> None:
        self.show()

    def _run_bg(self, fn) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def _append(self, text: str) -> None:
        self.log_box.appendPlainText(text)
        bar = self.log_box.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _set_badge(self, state: str, detail: str) -> None:
        colors = {
            "ready": "#334155",
            "connecting": ACCENT,
            "connected": SUCCESS,
            "reconnecting": WARN,
            "warning": WARN,
            "error": ERROR,
        }
        self.badge.setText(state.upper())
        self.badge.setStyleSheet(
            f"padding: 6px 10px; border-radius: 8px; background: {colors.get(state, '#334155')}; color: white; font-weight: 700;"
        )
        self.detail_var.setText(detail)

    def _set_flag(self, country_code: str) -> None:
        def worker() -> None:
            path = ensure_flag_png(self.service.paths.flags_dir, country_code)
            if path:
                self.bus.flag_ready.emit(str(path))

        self._run_bg(worker)

    def _apply_flag(self, path: str) -> None:
        pix = QPixmap(path)
        if not pix.isNull():
            self.flag_label.setPixmap(pix.scaledToHeight(26, Qt.SmoothTransformation))

    def _set_combo_items(self, combo: QComboBox, values: list[str]) -> None:
        current = combo.currentText().strip()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(values)
        combo.setCurrentText(current)
        combo.blockSignals(False)

    def _set_preview(self, text: str) -> None:
        self.command_box.setPlainText(text)

    def _country_display_values(self) -> list[str]:
        return list(self.countries.keys())

    def _bootstrap(self) -> None:
        ok = self.service.prepare_credentials()
        if not ok:
            self._append("Credentials not found. Expected ~/.cyberghost/config.ini with [device] token/secret.")

        self._load_profiles_ui()
        self._refresh_recents()
        self._load_countries(self.service.get_settings().refresh_cache_on_start)

        recovered = self.service.reconcile_runtime_state(self._append, force_scan=True)
        if recovered:
            if self.service.recovered_session_is_healthy():
                self._set_badge("connected", "Recovered active VPN session.")
            else:
                self._append("Recovered VPN process is stale (no active tunnel). Stopping it...")
                self._set_badge("connecting", "Cleaning stale recovered session...")
                self.service.stop(self._append)
                self._set_badge("ready", "Stale recovered session was stopped.")
        else:
            self._set_badge("ready", "Ready.")

        self._sync_action_buttons()
        self._check_ip()

        if self.service.get_settings().autoconnect_last_profile and self.service.list_profiles():
            last = self.service.list_profiles()[-1].name
            QTimer.singleShot(500, lambda: self._apply_profile(forced_name=last))

    def _fmt_bytes(self, value: int) -> str:
        units = ["B", "KB", "MB", "GB"]
        size = float(value)
        idx = 0
        while size >= 1024 and idx < len(units) - 1:
            size /= 1024.0
            idx += 1
        if idx == 0:
            return f"{int(size)} {units[idx]}"
        return f"{size:.1f} {units[idx]}"

    def _tick_connection_stats(self) -> None:
        secs = self.service.get_uptime_seconds()
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        self.uptime_var.setText(f"Uptime: {h:02d}:{m:02d}:{s:02d}")

        rx, tx = self.service.get_tun_stats() if secs > 0 else (0, 0)
        self.traffic_var.setText(f"Traffic: down {self._fmt_bytes(rx)}  up {self._fmt_bytes(tx)}")

        self._state_probe_tick += 1
        if self._state_probe_tick % 5 == 0:
            self.service.reconcile_runtime_state()
            self._sync_action_buttons()

    def _load_countries(self, force_refresh: bool) -> None:
        self._append("Loading country list...")
        self._set_badge("connecting", "Loading countries...")

        def worker() -> None:
            try:
                countries = self.service.get_countries(force_refresh=force_refresh)
                self.bus.countries_loaded.emit(countries)
            except Exception as exc:
                self.bus.countries_error.emit(str(exc))

        self._run_bg(worker)

    def _apply_countries(self, countries: dict[str, str]) -> None:
        self.countries = countries
        self._set_combo_items(self.country_combo, self._country_display_values())
        self._append("Countries loaded.")
        self._set_badge("ready", "Ready.")

    def _load_countries_failed(self, err: str) -> None:
        self._append(f"Error loading countries: {err}")
        self._set_badge("error", "Could not load countries.")

    def _force_country_match(self) -> None:
        current = self.country_combo.currentText().strip()
        if not current or not self.countries:
            return

        current_selected = self.selected_country_code
        matched_name = None
        matched_code = None

        if len(current) == 2 and current.isalpha():
            iso = current.upper()
            code_to_name = {code.upper(): name for name, code in self.countries.items()}
            matched_name = code_to_name.get(iso)
            if not matched_name:
                return
            matched_code = iso
        else:
            lowered = current.lower()
            for name, code in self.countries.items():
                if lowered == name.lower():
                    matched_name = name
                    matched_code = code
                    break
            if matched_name is None:
                for name, code in self.countries.items():
                    if lowered in name.lower():
                        matched_name = name
                        matched_code = code
                        break
            if matched_name is None:
                return

        if self.country_combo.currentText().strip() != matched_name:
            self.country_combo.setCurrentText(matched_name)

        if matched_code != current_selected:
            self._on_country()

    def _on_country_activated(self, _index: int) -> None:
        self._on_country()

    def _on_country_edit_finished(self) -> None:
        self._force_country_match()

    def _on_country(self) -> None:
        if self._country_loading:
            return

        name = self.country_combo.currentText().strip()
        if not name:
            return

        if name not in self.countries:
            self._force_country_match()
            name = self.country_combo.currentText().strip()
            if name not in self.countries:
                return

        new_code = self.countries[name]
        if self.selected_country_code == new_code and self.city_combo.currentText().strip():
            return

        self._country_loading = True
        self.selected_country_code = new_code
        self.city_combo.setCurrentText("")
        self.server_combo.setCurrentText("")
        self.server_var.setText("Server: -")
        self.connect_btn.setEnabled(False)
        self._set_preview("")
        self._append(f"Loading cities for {name} ({self.selected_country_code})...")
        self._set_badge("connecting", "Loading cities...")

        def worker() -> None:
            try:
                cities = self.service.get_cities(self.selected_country_code)
                self.bus.cities_loaded.emit(name, cities)
            except Exception as exc:
                self.bus.cities_error.emit(str(exc))

        self._run_bg(worker)

    def _apply_cities(self, country_name: str, cities: list[str]) -> None:
        self._set_combo_items(self.city_combo, cities)
        if cities:
            self.city_combo.setCurrentText(cities[0])
        self._country_loading = False
        self._append(f"Cities loaded for {country_name}.")
        self._set_badge("ready", "Ready.")
        if cities:
            self._on_city()

    def _cities_failed(self, err: str) -> None:
        self._country_loading = False
        self._append(f"Error loading cities: {err}")
        self._set_badge("error", "Could not load cities.")

    def _on_city_text(self, _text: str) -> None:
        self._on_city()

    def _on_city(self) -> None:
        if self._city_loading:
            return

        city = self.city_combo.currentText().strip()
        if not city or not self.selected_country_code:
            return

        current_server = self.server_combo.currentText().strip()
        if current_server:
            return

        self._city_loading = True
        self.server_combo.setCurrentText("")
        self.connect_btn.setEnabled(False)
        self._set_preview("")
        self._append(f"Loading servers for {city} ({self.selected_country_code})...")
        self._set_badge("connecting", "Loading servers...")

        def worker() -> None:
            try:
                servers = self.service.get_servers(self.selected_country_code, city)
                self.bus.servers_loaded.emit(city, servers)
            except Exception as exc:
                self.bus.servers_error.emit(str(exc))

        self._run_bg(worker)

    def _apply_servers(self, city: str, servers: list[str]) -> None:
        self._set_combo_items(self.server_combo, servers)
        if servers:
            self.server_combo.setCurrentText(servers[0])
            self._on_server()
        self._city_loading = False
        self._append(f"Servers loaded for {city}.")
        self._set_badge("ready", "Ready.")

    def _servers_failed(self, err: str) -> None:
        self._city_loading = False
        self._append(f"Error loading servers: {err}")
        self._set_badge("error", "Could not load servers.")

    def _on_server_text(self, _text: str) -> None:
        self._on_server()

    def _on_server(self) -> None:
        instance = self.server_combo.currentText().strip()
        if not instance:
            return
        self.connect_btn.setEnabled(True)
        proto = self.protocol_combo.currentText() or "UDP"
        service = self.service_combo.currentText() or "openvpn"
        self.server_var.setText(f"Server: {instance} ({proto}/{service})")
        self._set_preview(self.service.preview_command(instance, proto, service))

    def _quick_connect(self) -> None:
        try:
            countries = self.service.get_countries()
            if not countries:
                raise RuntimeError("No countries available.")
            first_country_name = next(iter(countries.keys()))
            code = countries[first_country_name]
            cities = self.service.get_cities(code)
            city = cities[0]
            servers = self.service.get_servers(code, city)
            server = servers[0]
            self.country_combo.setCurrentText(first_country_name)
            self.selected_country_code = code
            self._set_combo_items(self.city_combo, cities)
            self.city_combo.setCurrentText(city)
            self._set_combo_items(self.server_combo, servers)
            self.server_combo.setCurrentText(server)
            self._on_server()
            self._connect()
        except Exception as exc:
            self._append(f"Quick Connect failed: {exc}")
            self._set_badge("error", "Quick Connect failed.")

    def _connect(self) -> None:
        self._force_country_match()

        if self.country_combo.currentText().strip() and not self.server_combo.currentText().strip():
            try:
                self._on_country()
            except Exception:
                pass

        instance = self.server_combo.currentText().strip()
        protocol = self.protocol_combo.currentText() or "UDP"
        service = self.service_combo.currentText() or "openvpn"
        server_type = self.server_type_combo.currentText() or "traffic"

        if not instance:
            try:
                self._on_country()
                instance = self.server_combo.currentText().strip()
            except Exception:
                pass

        if not instance:
            QMessageBox.critical(self, APP_TITLE, "Select a server first.")
            return

        self.connect_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.server_var.setText(f"Server: {instance} ({protocol}/{service}/{server_type})")
        self._append(f"Connecting to {instance}.cg-dialup.net over {protocol} using {service} [{server_type}]...")
        if service == "openvpn":
            self._append("Using the built-in OpenVPN engine.")
        if protocol == "UDP":
            self._append("UDP mode selected.")
        self._set_badge("connecting", "Starting VPN engine...")

        def on_line(text: str) -> None:
            self.bus.log_line.emit(text)

        def on_status(state: str, detail: str) -> None:
            self.bus.invoke.emit(lambda: self._handle_connect_status(state, detail))

        def on_done() -> None:
            self.bus.invoke.emit(self._on_connect_done)

        country_name = self.country_combo.currentText().strip() or "Unknown"
        city_name = self.city_combo.currentText().strip()
        recent_entry = RecentEntry(
            country_name=country_name,
            country_code=self.selected_country_code,
            city=city_name,
            server=instance,
            protocol=protocol,
            service=service,
            server_type=server_type,
        )

        self.service.connect(instance, protocol, service, recent_entry, on_line, on_status, on_done)

    def _handle_connect_status(self, state: str, detail: str) -> None:
        self._set_badge(state, detail)
        if state == "connected":
            chosen_country = self.country_combo.currentText().strip()
            chosen_code = self.selected_country_code
            if chosen_country:
                self.location_var.setText(f"Location: {chosen_country}")
            if chosen_code:
                self._set_flag(chosen_code)
            QTimer.singleShot(300, self._check_ip)
            self._refresh_recents()

    def _on_connect_done(self) -> None:
        self.connect_btn.setEnabled(True)
        self._sync_action_buttons()
        if self.service.get_settings().auto_reconnect and self.server_var.text() != "Server: -":
            if self.service.should_auto_reconnect():
                QTimer.singleShot(1500, self._connect)

    def _stop(self) -> None:
        if not self.service.has_active_session():
            self._append("No active VPN session.")
            self._set_badge("ready", "Already stopped.")
            self._sync_action_buttons()
            return

        self.stop_btn.setEnabled(False)
        self.connect_btn.setEnabled(False)
        self._set_badge("connecting", "Stopping VPN engine...")

        def worker() -> None:
            stopped = self.service.stop(self.bus.log_line.emit)
            self.bus.invoke.emit(lambda: self._after_stop(stopped))

        self._run_bg(worker)

    def _after_stop(self, stopped: bool) -> None:
        if stopped:
            self._set_badge("ready", "Stopped.")
            self.server_var.setText("Server: -")
            self.location_var.setText("Location: Refreshing...")
            QTimer.singleShot(800, self._check_ip)
        else:
            self._set_badge("error", "Could not stop VPN. Check permissions.")
        self._sync_action_buttons()

    def _sync_action_buttons(self) -> None:
        active = self.service.has_active_session()
        self.connect_btn.setEnabled(True)
        self.stop_btn.setEnabled(active)

    def _check_ip(self) -> None:
        self._append("Checking public IP...")

        def worker() -> None:
            try:
                text, info = self.service.get_ip_info_text()
                self.bus.ip_ok.emit({"text": text, "info": info})
            except Exception as exc:
                self.bus.ip_error.emit(str(exc))

        self._run_bg(worker)

    def _apply_ip_info(self, payload: dict) -> None:
        text = payload.get("text", "")
        info = payload.get("info", {})
        self.last_info = info
        self.ip_var.setText(f"IP: {info.get('ip', 'Unknown')}")
        loc = f"Location: {info.get('city', '')}, {info.get('region', '')}, {info.get('country', '')}"
        self.location_var.setText(loc)
        active = self.service.has_active_session()
        active_country_code = self.service.get_active_session_country_code() if active else ""
        if active_country_code:
            self._set_flag(active_country_code)
        elif info.get("country_code"):
            self._set_flag(info["country_code"])
        if text:
            self._append(text)

    def _clear_logs(self) -> None:
        self.log_box.clear()

    def _refresh_recents(self) -> None:
        self.recents_list.clear()
        for item in self.service.recents:
            self.recents_list.addItem(self.service.format_recent_label(item))

    def _connect_recent(self, _item: QListWidgetItem | None = None) -> None:
        idx = self.recents_list.currentRow()
        if idx < 0 or idx >= len(self.service.recents):
            return

        entry = self.service.recents[idx]
        country_name = entry.country_name
        if country_name not in self.countries and entry.country_code:
            country_name = next((name for name, code in self.countries.items() if code == entry.country_code), country_name)

        if not country_name or (self.countries and country_name not in self.countries):
            QMessageBox.critical(self, APP_TITLE, "Recent server country is unavailable in the current country list.")
            return

        self.country_combo.setCurrentText(country_name)
        self.selected_country_code = entry.country_code or self.countries.get(country_name, "")

        try:
            cities = self.service.get_cities(self.selected_country_code) if self.selected_country_code else []
        except Exception:
            cities = []

        self._set_combo_items(self.city_combo, cities)
        if cities:
            self.city_combo.setCurrentText(entry.city if entry.city in cities else cities[0])
        else:
            self.city_combo.setCurrentText(entry.city)

        try:
            city_for_servers = self.city_combo.currentText().strip() or entry.city
            servers = (
                self.service.get_servers(self.selected_country_code, city_for_servers)
                if self.selected_country_code and city_for_servers
                else []
            )
        except Exception:
            servers = []

        if servers:
            self._set_combo_items(self.server_combo, servers)
        self.server_combo.setCurrentText(entry.server)
        self.protocol_combo.setCurrentText(entry.protocol or "UDP")
        self.service_combo.setCurrentText(entry.service or "openvpn")
        self.server_type_combo.setCurrentText(entry.server_type or "traffic")
        self._on_server()
        self._connect()

    def _save_profile(self) -> None:
        country_name = self.country_combo.currentText().strip()
        city = self.city_combo.currentText().strip()
        server = self.server_combo.currentText().strip()

        if not country_name or not city or not server:
            QMessageBox.critical(self, APP_TITLE, "Select country, city, and server first.")
            return

        name, ok = QInputDialog.getText(self, APP_TITLE, "Profile name:")
        if not ok or not name.strip():
            return

        profile = Profile(
            name=name.strip(),
            country_name=country_name,
            country_code=self.selected_country_code,
            city=city,
            server=server,
            protocol=self.protocol_combo.currentText() or "UDP",
            service=self.service_combo.currentText() or "openvpn",
            server_type=self.server_type_combo.currentText() or "traffic",
        )
        self.service.save_profile(profile)
        self._load_profiles_ui()

    def _load_profiles_ui(self) -> None:
        self.profiles_list.clear()
        for profile in self.service.list_profiles():
            self.profiles_list.addItem(f"{profile.name} [{profile.protocol}/{profile.service}/{profile.server_type}]")

    def _apply_profile(self, _item: QListWidgetItem | None = None, forced_name: str | None = None) -> None:
        target_name = forced_name
        if target_name is None:
            current = self.profiles_list.currentItem()
            if current is None:
                return
            target_name = current.text().split(" [", 1)[0]

        profile = next((p for p in self.service.list_profiles() if p.name == target_name), None)
        if not profile:
            return

        self.country_combo.setCurrentText(profile.country_name)
        self.selected_country_code = profile.country_code
        cities = self.service.get_cities(profile.country_code)
        self._set_combo_items(self.city_combo, cities)
        self.city_combo.setCurrentText(profile.city)
        servers = self.service.get_servers(profile.country_code, profile.city)
        self._set_combo_items(self.server_combo, servers)
        self.server_combo.setCurrentText(profile.server)
        self.protocol_combo.setCurrentText(profile.protocol or "UDP")
        self.service_combo.setCurrentText(profile.service or "openvpn")
        self.server_type_combo.setCurrentText(profile.server_type or "traffic")
        self._on_server()

    def _delete_profile(self) -> None:
        current = self.profiles_list.currentItem()
        if current is None:
            return

        name = current.text().split(" [", 1)[0]
        self.service.delete_profile(name)
        self._load_profiles_ui()

    def _save_settings(self) -> None:
        settings = Settings(
            autoconnect_last_profile=self.autoconnect_var.isChecked(),
            stop_vpn_on_exit=self.stop_on_exit_var.isChecked(),
            hide_logs_by_default=self.hide_logs_var.isChecked(),
            refresh_cache_on_start=self.refresh_cache_var.isChecked(),
            default_protocol=self.settings_protocol.currentText() or "UDP",
            default_service=self.settings_service.currentText() or "openvpn",
            default_server_type=self.settings_server_type.currentText() or "traffic",
            auto_reconnect=self.auto_reconnect_var.isChecked(),
            kill_switch=self.kill_switch_var.isChecked(),
        )
        self.service.update_settings(settings)
        self.protocol_combo.setCurrentText(settings.default_protocol)
        self.service_combo.setCurrentText(settings.default_service)
        self.server_type_combo.setCurrentText(settings.default_server_type)
        QMessageBox.information(self, APP_TITLE, "Settings saved.")

    def closeEvent(self, event) -> None:
        if self.service.get_settings().stop_vpn_on_exit:
            self.service.stop(self.bus.log_line.emit)
        event.accept()
