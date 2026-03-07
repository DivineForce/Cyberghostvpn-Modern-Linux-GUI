from __future__ import annotations
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from .assets import ensure_app_icon, ensure_flag_png
from .config import APP_TITLE, WINDOW_SIZE
from .helpers import filter_matches
from .models import Profile, Settings
from .service import VpnService

BG = "#0b1020"
PANEL = "#111827"
PANEL2 = "#0f172a"
INPUT = "#1f2937"
FG = "#e5e7eb"
MUTED = "#94a3b8"
ACCENT = "#2563eb"
SUCCESS = "#22c55e"
WARN = "#f59e0b"
ERROR = "#ef4444"
BTN = "#172033"
BTN_ACTIVE = "#22304a"
SCROLL = "#22304a"

class SearchableCombobox(ttk.Combobox):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self._all_values = []
        self._code_map = {}
        self.bind("<KeyRelease>", self._on_keyrelease)
        self.bind("<Button-1>", self._on_click)

    def set_source(self, values: list[str], code_map: dict[str, str] | None = None):
        self._all_values = list(values)
        self._code_map = code_map or {}
        self.configure(values=values)

    def _on_click(self, _event=None):
        self.icursor(tk.END)

    def _on_keyrelease(self, event=None):
        if event and event.keysym in {"Up", "Down", "Return", "Escape", "Tab"}:
            return
        current = self.get()
        filtered = filter_matches(self._all_values, current, self._code_map)
        self.configure(values=filtered)

class CyberGhostUI(tk.Tk):
    def __init__(self, service: VpnService) -> None:
        super().__init__()
        self.service = service
        self.countries: dict[str, str] = {}
        self.country_code_map: dict[str, str] = {}
        self.selected_country_code = ""
        self.last_info: dict = {}
        self.flag_img_ref = None
        self._country_loading = False
        self._city_loading = False
        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(1080, 920)
        self.configure(bg=BG)
        ensure_app_icon(self.service.paths.icon_file)
        try:
            icon = tk.PhotoImage(file=str(self.service.paths.icon_file))
            self.iconphoto(True, icon)
            self._icon_ref = icon
        except Exception:
            self._icon_ref = None
        self.option_add("*TCombobox*Listbox.background", INPUT)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", FG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._style()
        self._build()
        self.after(50, self._bootstrap)
        self.after(1000, self._tick_connection_stats)

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("Root.TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("PanelAlt.TFrame", background=PANEL2)
        style.configure("Title.TLabel", background=BG, foreground=FG, font=("Segoe UI", 19, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=MUTED)
        style.configure("Panel.TLabel", background=PANEL, foreground=FG)
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Accent.TLabel", background=PANEL2, foreground=FG, font=("Segoe UI", 12, "bold"))
        style.configure("Primary.TButton", padding=(12, 10), font=("Segoe UI", 10, "bold"), background=BTN, foreground=FG, bordercolor=BTN, lightcolor=BTN, darkcolor=BTN)
        style.configure("Secondary.TButton", padding=(12, 10), background=BTN, foreground=FG, bordercolor=BTN, lightcolor=BTN, darkcolor=BTN)
        style.map("Primary.TButton", background=[("active", BTN_ACTIVE), ("pressed", BTN_ACTIVE)], foreground=[("active", FG)])
        style.map("Secondary.TButton", background=[("active", BTN_ACTIVE), ("pressed", BTN_ACTIVE)], foreground=[("active", FG)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 8), background=PANEL, foreground=FG)
        style.map("TNotebook.Tab", background=[("selected", PANEL2)], foreground=[("selected", FG)])
        style.configure("TCombobox", fieldbackground=INPUT, background=INPUT, foreground=FG, bordercolor="#334155", lightcolor=INPUT, darkcolor=INPUT, arrowcolor=FG, insertcolor=FG)
        style.map("TCombobox", fieldbackground=[("readonly", INPUT), ("!readonly", INPUT)], background=[("readonly", INPUT), ("!readonly", INPUT)], foreground=[("readonly", FG), ("!readonly", FG)], arrowcolor=[("readonly", FG), ("active", FG)])
        style.layout("Dark.Vertical.TScrollbar", style.layout("Vertical.TScrollbar"))
        style.configure("Dark.Vertical.TScrollbar", background=SCROLL, darkcolor=SCROLL, lightcolor=SCROLL, troughcolor=PANEL2, arrowcolor=FG, bordercolor=PANEL2)

    def _make_scrolled(self, parent, **kwargs):
        frame = tk.Frame(parent, bg=PANEL2)
        text = tk.Text(frame, bg=kwargs.get("bg", "#020617"), fg=kwargs.get("fg", FG), insertbackground=kwargs.get("insertbackground", FG), relief="flat", padx=kwargs.get("padx", 10), pady=kwargs.get("pady", 10), height=kwargs.get("height", 10), wrap=kwargs.get("wrap", tk.WORD))
        scroll = ttk.Scrollbar(frame, orient="vertical", style="Dark.Vertical.TScrollbar", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return frame, text

    def _build(self) -> None:
        header = ttk.Frame(self, style="Root.TFrame")
        header.pack(fill="x", padx=18, pady=(16, 10))
        ttk.Label(header, text="CyberGhost Modern", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Dashboard to solve CyberGhost VPN issues by DivineForce based on @Ifleg's cyberghost gui fix", style="Sub.TLabel").pack(anchor="w")

        top = ttk.Frame(self, style="Root.TFrame")
        top.pack(fill="x", padx=16, pady=(0, 12))

        self.status_card = tk.Frame(top, bg=PANEL2, highlightthickness=1, highlightbackground="#1f2937")
        self.status_card.pack(fill="x")

        inner = ttk.Frame(self.status_card, style="PanelAlt.TFrame")
        inner.pack(fill="x", padx=14, pady=14)

        self.badge = tk.Label(inner, text="READY", bg="#334155", fg="white", padx=10, pady=5, font=("Segoe UI", 10, "bold"))
        self.badge.grid(row=0, column=0, sticky="w")

        self.flag_label = tk.Label(inner, bg=PANEL2)
        self.flag_label.grid(row=0, column=1, sticky="w", padx=(14, 0))

        self.server_var = tk.StringVar(value="Server: -")
        self.ip_var = tk.StringVar(value="IP: Unknown")
        self.location_var = tk.StringVar(value="Location: Unknown")
        self.detail_var = tk.StringVar(value="Idle")

        ttk.Label(inner, textvariable=self.server_var, style="Accent.TLabel").grid(row=0, column=2, sticky="w", padx=(10, 0))
        ttk.Label(inner, textvariable=self.ip_var, style="Sub.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(inner, textvariable=self.location_var, style="Sub.TLabel").grid(row=1, column=2, sticky="w", padx=(10, 0), pady=(8, 0))
        ttk.Label(inner, textvariable=self.detail_var, style="Sub.TLabel").grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.uptime_var = tk.StringVar(value="Uptime: 00:00:00")
        self.traffic_var = tk.StringVar(value="Traffic: down 0 B  up 0 B")
        ttk.Label(inner, textvariable=self.uptime_var, style="Sub.TLabel").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Label(inner, textvariable=self.traffic_var, style="Sub.TLabel").grid(row=3, column=2, sticky="w", padx=(10,0), pady=(8,0))

        body = ttk.Frame(self, style="Root.TFrame")
        body.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        left = ttk.Frame(body, style="Panel.TFrame", padding=16)
        left.pack(side="left", fill="y")

        notebook = ttk.Notebook(body)
        notebook.pack(side="left", fill="both", expand=True, padx=(14, 0))

        dashboard = ttk.Frame(notebook, style="PanelAlt.TFrame")
        profiles_tab = ttk.Frame(notebook, style="PanelAlt.TFrame")
        settings_tab = ttk.Frame(notebook, style="PanelAlt.TFrame")
        notebook.add(dashboard, text="Dashboard")
        notebook.add(profiles_tab, text="Profiles")
        notebook.add(settings_tab, text="Settings")

        ttk.Label(left, text="Quick Connect", style="Panel.TLabel").pack(anchor="w", pady=(0, 12))

        ttk.Label(left, text="Country", style="Panel.TLabel").pack(anchor="w")
        self.country_combo = SearchableCombobox(left, state="normal", width=36)
        self.country_combo.pack(fill="x", pady=(4, 12))
        self.country_combo.bind("<<ComboboxSelected>>", self._on_country)
        self.country_combo.bind("<FocusOut>", self._force_country_match)
        self.country_combo.bind("<Return>", self._force_country_match)

        ttk.Label(left, text="City", style="Panel.TLabel").pack(anchor="w")
        self.city_combo = SearchableCombobox(left, state="normal", width=36)
        self.city_combo.pack(fill="x", pady=(4, 12))
        self.city_combo.bind("<<ComboboxSelected>>", self._on_city)

        ttk.Label(left, text="Server", style="Panel.TLabel").pack(anchor="w")
        self.server_combo = SearchableCombobox(left, state="normal", width=36)
        self.server_combo.pack(fill="x", pady=(4, 12))
        self.server_combo.bind("<<ComboboxSelected>>", self._on_server)

        ttk.Label(left, text="Protocol", style="Panel.TLabel").pack(anchor="w")
        self.protocol_combo = ttk.Combobox(left, state="readonly", values=["TCP", "UDP"], width=36)
        self.protocol_combo.pack(fill="x", pady=(4, 12))
        self.protocol_combo.set(self.service.get_settings().default_protocol or "UDP")
        self.protocol_combo.bind("<<ComboboxSelected>>", self._on_server)

        ttk.Label(left, text="VPN Service", style="Panel.TLabel").pack(anchor="w")
        self.service_combo = ttk.Combobox(left, state="readonly", values=["openvpn"], width=36)
        self.service_combo.pack(fill="x", pady=(4, 12))
        self.service_combo.set("openvpn")
        self.service_combo.bind("<<ComboboxSelected>>", self._on_server)

        ttk.Label(left, text="Server Type", style="Panel.TLabel").pack(anchor="w")
        self.server_type_combo = ttk.Combobox(left, state="readonly", values=["traffic", "streaming", "torrent"], width=36)
        self.server_type_combo.pack(fill="x", pady=(4, 12))
        self.server_type_combo.set(self.service.get_settings().default_server_type or "traffic")

        self.quick_btn = ttk.Button(left, text="Quick Connect", style="Primary.TButton", command=self._quick_connect)
        self.quick_btn.pack(fill="x", pady=(0, 8))
        self.connect_btn = ttk.Button(left, text="Connect Selected", style="Primary.TButton", command=self._connect, state="disabled")
        self.connect_btn.pack(fill="x", pady=(0, 8))
        self.stop_btn = ttk.Button(left, text="Stop", style="Secondary.TButton", command=self._stop, state="disabled")
        self.stop_btn.pack(fill="x", pady=(0, 8))
        self.refresh_btn = ttk.Button(left, text="Refresh Servers", style="Secondary.TButton", command=lambda: self._load_countries(True))
        self.refresh_btn.pack(fill="x", pady=(0, 8))
        self.ip_btn = ttk.Button(left, text="Check IP", style="Secondary.TButton", command=self._check_ip)
        self.ip_btn.pack(fill="x")

        ttk.Label(left, text="Recent Servers", style="Panel.TLabel").pack(anchor="w", pady=(18, 6))
        self.recents_list = tk.Listbox(left, height=16, bg=INPUT, fg=FG, selectbackground=ACCENT, relief="flat")
        self.recents_list.pack(fill="x")
        self.recents_list.bind("<Double-Button-1>", self._connect_recent)

        dash_container = ttk.Frame(dashboard, style="PanelAlt.TFrame", padding=16)
        dash_container.pack(fill="both", expand=True)
        ttk.Label(dash_container, text="Command Preview", style="Accent.TLabel").pack(anchor="w")
        frame1, self.command_box = self._make_scrolled(dash_container, height=4, bg="#020617", fg=FG, insertbackground=FG)
        frame1.pack(fill="x", pady=(6, 14))
        self.command_box.config(state="disabled")

        ttk.Label(dash_container, text="Connection Logs", style="Accent.TLabel").pack(anchor="w")
        frame2, self.log_box = self._make_scrolled(dash_container, bg="#020617", fg="#cbd5e1", insertbackground="#cbd5e1")
        frame2.pack(fill="both", expand=True, pady=(6, 0))

        prof = ttk.Frame(profiles_tab, style="PanelAlt.TFrame", padding=16)
        prof.pack(fill="both", expand=True)
        ttk.Label(prof, text="Saved Profiles", style="Accent.TLabel").pack(anchor="w")
        self.profiles_list = tk.Listbox(prof, height=10, bg=INPUT, fg=FG, selectbackground=ACCENT, relief="flat")
        self.profiles_list.pack(fill="x", pady=(8, 12))
        self.profiles_list.bind("<Double-Button-1>", self._apply_profile)

        row = ttk.Frame(prof, style="PanelAlt.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="Save Current", style="Primary.TButton", command=self._save_profile).pack(side="left")
        ttk.Button(row, text="Apply", style="Secondary.TButton", command=self._apply_profile).pack(side="left", padx=8)
        ttk.Button(row, text="Delete", style="Secondary.TButton", command=self._delete_profile).pack(side="left")

        sett = ttk.Frame(settings_tab, style="PanelAlt.TFrame", padding=16)
        sett.pack(fill="both", expand=True)
        ttk.Label(sett, text="Settings", style="Accent.TLabel").pack(anchor="w")

        s = self.service.get_settings()
        self.autoconnect_var = tk.BooleanVar(value=s.autoconnect_last_profile)
        self.stop_on_exit_var = tk.BooleanVar(value=s.stop_vpn_on_exit)
        self.hide_logs_var = tk.BooleanVar(value=s.hide_logs_by_default)
        self.refresh_cache_var = tk.BooleanVar(value=s.refresh_cache_on_start)
        self.auto_reconnect_var = tk.BooleanVar(value=getattr(s, "auto_reconnect", True))
        self.kill_switch_var = tk.BooleanVar(value=getattr(s, "kill_switch", False))

        def dark_check(parent, text, var):
            cb = tk.Checkbutton(parent, text=text, variable=var, bg=PANEL2, fg=FG, selectcolor=INPUT, activebackground=PANEL2, activeforeground=FG, highlightthickness=0, bd=0)
            cb.pack(anchor="w", pady=6)
            return cb

        dark_check(sett, "Autoconnect last profile on startup", self.autoconnect_var)
        dark_check(sett, "Stop VPN when closing app", self.stop_on_exit_var)
        dark_check(sett, "Hide logs by default", self.hide_logs_var)
        dark_check(sett, "Refresh server cache on start", self.refresh_cache_var)
        dark_check(sett, "Auto reconnect if VPN drops", self.auto_reconnect_var)
        dark_check(sett, "Kill switch (experimental)", self.kill_switch_var)

        ttk.Label(sett, text="Default Protocol", style="Panel.TLabel").pack(anchor="w", pady=(12, 4))
        self.settings_protocol = ttk.Combobox(sett, state="readonly", values=["TCP", "UDP"])
        self.settings_protocol.pack(anchor="w")
        self.settings_protocol.set(s.default_protocol or "UDP")

        ttk.Label(sett, text="Default Service", style="Panel.TLabel").pack(anchor="w", pady=(12, 4))
        self.settings_service = ttk.Combobox(sett, state="readonly", values=["openvpn"])
        self.settings_service.pack(anchor="w")
        self.settings_service.set("openvpn")

        ttk.Label(sett, text="Default Server Type", style="Panel.TLabel").pack(anchor="w", pady=(12, 4))
        self.settings_server_type = ttk.Combobox(sett, state="readonly", values=["traffic", "streaming", "torrent"])
        self.settings_server_type.pack(anchor="w")
        self.settings_server_type.set(s.default_server_type or "traffic")

        ttk.Button(sett, text="Save Settings", style="Primary.TButton", command=self._save_settings).pack(anchor="w", pady=(14, 0))
        info = tk.Label(
            sett,
            text="System tray icon is not implemented in this build. Auto reconnect and traffic stats are included here.",
            bg=PANEL2,
            fg=MUTED,
            wraplength=720,
            justify="left"
        )
        info.pack(anchor="w", pady=(14, 0))


    def _fmt_bytes(self, value: int) -> str:
        units = ["B", "KB", "MB", "GB"]
        size = float(value)
        idx = 0
        while size >= 1024 and idx < len(units)-1:
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
        self.uptime_var.set(f"Uptime: {h:02d}:{m:02d}:{s:02d}")
        rx, tx = self.service.get_tun_stats() if secs > 0 else (0, 0)
        self.traffic_var.set(f"Traffic: down {self._fmt_bytes(rx)}  up {self._fmt_bytes(tx)}")
        self.after(1000, self._tick_connection_stats)

    def _bootstrap(self) -> None:
        ok = self.service.prepare_credentials()
        if not ok:
            self._append("Credentials not found. Expected ~/.cyberghost/config.ini with [device] token/secret.")
        self._load_profiles_ui()
        self._refresh_recents()
        self._load_countries(self.service.get_settings().refresh_cache_on_start)
        self._check_ip()
        if self.service.get_settings().autoconnect_last_profile and self.service.list_profiles():
            self.after(500, lambda: self._apply_profile(None, self.service.list_profiles()[-1].name))

    def _append(self, text: str) -> None:
        def inner() -> None:
            self.log_box.insert(tk.END, text + "\n")
            self.log_box.see(tk.END)
        self.after(0, inner)

    def _set_badge(self, state: str, detail: str) -> None:
        colors = {"ready": "#334155", "connecting": ACCENT, "connected": SUCCESS, "reconnecting": WARN, "warning": WARN, "error": ERROR}
        self.after(0, lambda: self.badge.config(text=state.upper(), bg=colors.get(state, "#334155")))
        self.after(0, lambda: self.detail_var.set(detail))

    def _set_flag(self, country_code: str) -> None:
        def worker() -> None:
            path = ensure_flag_png(self.service.paths.flags_dir, country_code)
            if not path:
                return
            def apply() -> None:
                try:
                    img = tk.PhotoImage(file=str(path))
                    self.flag_img_ref = img
                    self.flag_label.configure(image=img)
                except Exception:
                    pass
            self.after(0, apply)
        threading.Thread(target=worker, daemon=True).start()

    def _set_preview(self, text: str) -> None:
        def inner() -> None:
            self.command_box.config(state="normal")
            self.command_box.delete("1.0", tk.END)
            self.command_box.insert(tk.END, text)
            self.command_box.config(state="disabled")
        self.after(0, inner)

    def _country_display_values(self) -> list[str]:
        return [name for name in self.countries.keys()]

    def _load_countries(self, force_refresh: bool) -> None:
        self._append("Loading country list...")
        self._set_badge("connecting", "Loading countries...")
        def worker() -> None:
            try:
                self.countries = self.service.get_countries(force_refresh=force_refresh)
                self.country_code_map = dict(self.countries)
                displays = self._country_display_values()
                self.after(0, lambda: self.country_combo.set_source(displays, self.country_code_map))
                self._append("Countries loaded.")
                self._set_badge("ready", "Ready.")
            except Exception as exc:
                self._append(f"Error loading countries: {exc}")
                self._set_badge("error", "Could not load countries.")
        threading.Thread(target=worker, daemon=True).start()

    def _force_country_match(self, _event=None) -> None:
        current = self.country_combo.get().strip()
        if not current or not self.countries:
            return

        current_selected = getattr(self, "selected_country_code", "")
        matched_name = None
        matched_code = None

        # EXACT ISO match if exactly 2 letters
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

        if self.country_combo.get().strip() != matched_name:
            self.country_combo.set(matched_name)

        if matched_code != current_selected:
            self._on_country()

    def _on_country(self, _event=None) -> None:
        if self._country_loading:
            return
        name = self.country_combo.get().strip()
        if not name:
            return
        if name not in self.countries:
            self._force_country_match()
            name = self.country_combo.get().strip()
            if name not in self.countries:
                return
        new_code = self.countries[name]
        if self.selected_country_code == new_code and self.city_combo.get().strip():
            return
        self._country_loading = True
        self.selected_country_code = new_code
        self.city_combo.set("")
        self.server_combo.set("")
        self.server_var.set("Server: -")
        self.connect_btn.configure(state="disabled")
        self._set_preview("")
        self._append(f"Loading cities for {name} ({self.selected_country_code})...")
        self._set_badge("connecting", "Loading cities...")
        def worker() -> None:
            try:
                cities = self.service.get_cities(self.selected_country_code)
                def apply():
                    self.city_combo.set_source(cities)
                    if cities:
                        self.city_combo.set(cities[0])
                    self._country_loading = False
                    if cities:
                        self._on_city()
                self.after(0, apply)
                self._append(f"Cities loaded for {name}.")
                self._set_badge("ready", "Ready.")
            except Exception as exc:
                self._country_loading = False
                self._append(f"Error loading cities: {exc}")
                self._set_badge("error", "Could not load cities.")
        threading.Thread(target=worker, daemon=True).start()

    def _on_city(self, _event=None) -> None:
        if self._city_loading:
            return
        city = self.city_combo.get().strip()
        if not city or not self.selected_country_code:
            return
        current_server = self.server_combo.get().strip()
        if current_server:
            return
        self._city_loading = True
        self.server_combo.set("")
        self.connect_btn.configure(state="disabled")
        self._set_preview("")
        self._append(f"Loading servers for {city} ({self.selected_country_code})...")
        self._set_badge("connecting", "Loading servers...")
        def worker() -> None:
            try:
                servers = self.service.get_servers(self.selected_country_code, city)
                def apply():
                    self.server_combo.set_source(servers)
                    if servers:
                        self.server_combo.set(servers[0])
                        self._on_server()
                    self._city_loading = False
                self.after(0, apply)
                self._append(f"Servers loaded for {city}.")
                self._set_badge("ready", "Ready.")
            except Exception as exc:
                self._city_loading = False
                self._append(f"Error loading servers: {exc}")
                self._set_badge("error", "Could not load servers.")
        threading.Thread(target=worker, daemon=True).start()

    def _on_server(self, _event=None) -> None:
        instance = self.server_combo.get().strip()
        if not instance:
            return
        self.connect_btn.configure(state="normal")
        proto = self.protocol_combo.get() or "UDP"
        service = self.service_combo.get() or "openvpn"
        self.server_var.set(f"Server: {instance} ({proto}/{service})")
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
            self.country_combo.set(first_country_name)
            self.selected_country_code = code
            self.city_combo.set_source(cities)
            self.city_combo.set(city)
            self.server_combo.set_source(servers)
            self.server_combo.set(server)
            self._on_server()
            self._connect()
        except Exception as exc:
            self._append(f"Quick Connect failed: {exc}")
            self._set_badge("error", "Quick Connect failed.")

    def _connect(self) -> None:
        self._force_country_match()
        if self.country_combo.get().strip() and not self.server_combo.get().strip():
            try:
                self._on_country()
            except Exception:
                pass
        instance = self.server_combo.get().strip()
        protocol = self.protocol_combo.get() or "UDP"
        service = self.service_combo.get() or "openvpn"
        server_type = self.server_type_combo.get() or "traffic"
        
        if not instance:
            try:
                self._on_country()
                instance = self.server_combo.get().strip()
            except Exception:
                pass
        if not instance:
            messagebox.showerror(APP_TITLE, "Select a server first.")
            return

        self.connect_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.server_var.set(f"Server: {instance} ({protocol}/{service}/{server_type})")
        self._append(f"Connecting to {instance}.cg-dialup.net over {protocol} using {service} [{server_type}]...")
        if service == "openvpn":
            self._append("Using the built-in OpenVPN engine.")
        if protocol == "UDP":
            self._append("UDP mode selected.")
        self._set_badge("connecting", "Starting VPN engine...")

        def on_status(state: str, detail: str) -> None:
            self._set_badge(state, detail)
            if state == "connected":
                chosen_country = self.country_combo.get().strip()
                chosen_code = self.selected_country_code
                if chosen_country:
                    self.after(0, lambda: self.location_var.set(f"Location: {chosen_country}"))
                if chosen_code:
                    self.after(0, lambda: self._set_flag(chosen_code))
                self.after(300, self._check_ip)
                self._refresh_recents()

        def on_done() -> None:
            self.after(0, lambda: self.connect_btn.configure(state="normal"))
            self.after(0, self._sync_action_buttons)
            if self.service.get_settings().auto_reconnect and self.server_var.get() != "Server: -":
                if self.service.should_auto_reconnect():
                    self.after(1500, self._connect)

        country_name = self.country_combo.get().strip() or "Unknown"
        recent_label = f"{country_name} - {instance}"
        self.service.connect(instance, protocol, service, recent_label, self._append, on_status, on_done)

    def _stop(self) -> None:
        if not self.service.has_active_session():
            self._append("No active VPN session.")
            self._set_badge("ready", "Already stopped.")
            self._sync_action_buttons()
            return
        self.stop_btn.configure(state="disabled")
        self.connect_btn.configure(state="disabled")
        self._set_badge("connecting", "Stopping VPN engine...")

        def worker() -> None:
            stopped = self.service.stop(self._append)

            def finalize() -> None:
                if stopped:
                    self._set_badge("ready", "Stopped.")
                    self.server_var.set("Server: -")
                    self.location_var.set("Location: Refreshing...")
                    self.after(800, self._check_ip)
                else:
                    self._set_badge("error", "Could not stop VPN. Check permissions.")
                self._sync_action_buttons()

            self.after(0, finalize)

        threading.Thread(target=worker, daemon=True).start()

    def _sync_action_buttons(self) -> None:
        active = self.service.has_active_session()
        self.connect_btn.configure(state="normal")
        self.stop_btn.configure(state="normal" if active else "disabled")

    def _check_ip(self) -> None:
        self._append("Checking public IP...")
        def worker() -> None:
            try:
                text, info = self.service.get_ip_info_text()
                self.last_info = info
                self.after(0, lambda: self.ip_var.set(f"IP: {info['ip']}"))
                loc = f"Location: {info['city']}, {info['region']}, {info['country']}"
                self.after(0, lambda: self.location_var.set(loc))
                if info.get("country_code"):
                    self.after(0, lambda: self._set_flag(info["country_code"]))
                self._append(text)
            except Exception as exc:
                self._append(f"IP lookup error: {exc}")
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_recents(self) -> None:
        self.recents_list.delete(0, tk.END)
        for item in self.service.recents:
            self.recents_list.insert(tk.END, item)

    def _connect_recent(self, _event=None) -> None:
        sel = self.recents_list.curselection()
        if not sel:
            return
        entry = self.recents_list.get(sel[0])
        server = entry.split(" - ", 1)[-1] if " - " in entry else entry
        self.server_combo.set(server)
        self._on_server()
        self._connect()

    def _save_profile(self) -> None:
        name_only = self.country_combo.get().strip()
        if not name_only or not self.city_combo.get().strip() or not self.server_combo.get().strip():
            messagebox.showerror(APP_TITLE, "Select country, city, and server first.")
            return
        name = simpledialog.askstring(APP_TITLE, "Profile name:")
        if not name:
            return
        profile = Profile(
            name=name.strip(),
            country_name=name_only,
            country_code=self.selected_country_code,
            city=self.city_combo.get().strip(),
            server=self.server_combo.get().strip(),
            protocol=self.protocol_combo.get() or "UDP",
            service=self.service_combo.get() or "openvpn",
            server_type=self.server_type_combo.get() or "traffic",
        )
        self.service.save_profile(profile)
        self._load_profiles_ui()

    def _load_profiles_ui(self) -> None:
        self.profiles_list.delete(0, tk.END)
        for profile in self.service.list_profiles():
            self.profiles_list.insert(tk.END, f"{profile.name} [{profile.protocol}/{profile.service}/{profile.server_type}]")

    def _apply_profile(self, _event=None, forced_name: str | None = None) -> None:
        target_name = forced_name
        if target_name is None:
            sel = self.profiles_list.curselection()
            if not sel:
                return
            target_name = self.profiles_list.get(sel[0]).split(" [", 1)[0]
        profile = next((p for p in self.service.list_profiles() if p.name == target_name), None)
        if not profile:
            return
        self.country_combo.set(profile.country_name)
        self.selected_country_code = profile.country_code
        cities = self.service.get_cities(profile.country_code)
        self.city_combo.set_source(cities)
        self.city_combo.set(profile.city)
        servers = self.service.get_servers(profile.country_code, profile.city)
        self.server_combo.set_source(servers)
        self.server_combo.set(profile.server)
        self.protocol_combo.set(profile.protocol or "UDP")
        self.service_combo.set(profile.service or "openvpn")
        self.server_type_combo.set(profile.server_type or "traffic")
        self._on_server()

    def _delete_profile(self) -> None:
        sel = self.profiles_list.curselection()
        if not sel:
            return
        name = self.profiles_list.get(sel[0]).split(" [", 1)[0]
        self.service.delete_profile(name)
        self._load_profiles_ui()

    def _save_settings(self) -> None:
        settings = Settings(
            autoconnect_last_profile=self.autoconnect_var.get(),
            stop_vpn_on_exit=self.stop_on_exit_var.get(),
            hide_logs_by_default=self.hide_logs_var.get(),
            refresh_cache_on_start=self.refresh_cache_var.get(),
            default_protocol=self.settings_protocol.get() or "UDP",
            default_service=self.settings_service.get() or "openvpn",
            default_server_type=self.settings_server_type.get() or "traffic",
            auto_reconnect=self.auto_reconnect_var.get(),
            kill_switch=self.kill_switch_var.get(),
        )
        self.service.update_settings(settings)
        self.protocol_combo.set(settings.default_protocol)
        self.service_combo.set(settings.default_service)
        self.server_type_combo.set(settings.default_server_type)
        messagebox.showinfo(APP_TITLE, "Settings saved.")

    def _on_close(self) -> None:
        if self.service.get_settings().stop_vpn_on_exit:
            self.service.stop()
        self.destroy()
