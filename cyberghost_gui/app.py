from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication
from .config import build_paths
from .service import VpnService
from .ui import CyberGhostUI

def main() -> int:
    paths = build_paths()
    service = VpnService(paths=paths, logger=print)
    qt_app = QApplication(sys.argv)
    window = CyberGhostUI(service)
    window.run()
    return qt_app.exec()
