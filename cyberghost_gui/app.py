from __future__ import annotations
from .config import build_paths
from .service import VpnService
from .ui import CyberGhostUI

def main() -> int:
    paths = build_paths()
    service = VpnService(paths=paths, logger=print)
    app = CyberGhostUI(service)
    app.mainloop()
    return 0
