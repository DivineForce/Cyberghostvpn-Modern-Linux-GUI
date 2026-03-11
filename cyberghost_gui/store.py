from __future__ import annotations
import json
from dataclasses import asdict
from .models import CacheData, Profile, Settings, Paths, RecentEntry, ActiveSession

def load_cache(paths: Paths) -> CacheData:
    if not paths.cache_file.exists():
        return CacheData()
    try:
        payload = json.loads(paths.cache_file.read_text(encoding="utf-8"))
        return CacheData(
            countries=payload.get("countries", {}),
            cities_by_country=payload.get("cities_by_country", {}),
            servers_by_city=payload.get("servers_by_city", {}),
        )
    except Exception:
        return CacheData()

def save_cache(paths: Paths, cache: CacheData) -> None:
    paths.cache_file.parent.mkdir(parents=True, exist_ok=True)
    paths.cache_file.write_text(json.dumps(asdict(cache), indent=2, sort_keys=True), encoding="utf-8")

def load_profiles(paths: Paths) -> list[Profile]:
    if not paths.profiles_file.exists():
        return []
    try:
        payload = json.loads(paths.profiles_file.read_text(encoding="utf-8"))
        return [Profile(**item) for item in payload]
    except Exception:
        return []

def save_profiles(paths: Paths, profiles: list[Profile]) -> None:
    paths.profiles_file.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(p) for p in profiles]
    paths.profiles_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

def load_settings(paths: Paths) -> Settings:
    if not paths.settings_file.exists():
        return Settings()
    try:
        payload = json.loads(paths.settings_file.read_text(encoding="utf-8"))
        return Settings(**payload)
    except Exception:
        return Settings()

def save_settings(paths: Paths, settings: Settings) -> None:
    paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
    paths.settings_file.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")


def load_recents(paths: Paths) -> list[RecentEntry]:
    if not paths.recents_file.exists():
        return []
    try:
        payload = json.loads(paths.recents_file.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return []
        out: list[RecentEntry] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            out.append(RecentEntry(**item))
        return out
    except Exception:
        return []


def save_recents(paths: Paths, recents: list[RecentEntry]) -> None:
    paths.recents_file.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(r) for r in recents]
    paths.recents_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_active_session(paths: Paths) -> ActiveSession | None:
    if not paths.session_file.exists():
        return None
    try:
        payload = json.loads(paths.session_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        return ActiveSession(**payload)
    except Exception:
        return None


def save_active_session(paths: Paths, session: ActiveSession) -> None:
    paths.session_file.parent.mkdir(parents=True, exist_ok=True)
    paths.session_file.write_text(json.dumps(asdict(session), indent=2), encoding="utf-8")


def clear_active_session(paths: Paths) -> None:
    try:
        paths.session_file.unlink(missing_ok=True)
    except Exception:
        pass
