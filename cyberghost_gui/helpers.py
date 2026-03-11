from __future__ import annotations

def filter_matches(values: list[str], text: str, code_map: dict[str, str] | None = None) -> list[str]:
    query = (text or "").strip().lower()
    if not query:
        return values
    out = []
    for value in values:
        code = (code_map or {}).get(value, "").lower()
        if query in value.lower() or query == code or code.startswith(query):
            out.append(value)
    return out or values
