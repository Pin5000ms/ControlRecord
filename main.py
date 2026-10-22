from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys


def main():
    if sys.platform != "win32":
        raise SystemExit("ControlRecord 目前僅支援 Windows 10 / 11。")
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--smoke-test", action="store_true", help="Render interface then exit; no input hooks or power requests")
    args = parser.parse_args()

    from controlrecord.windows import SingleInstance, enable_dpi_awareness
    enable_dpi_awareness()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtGui import QIcon
    from controlrecord.storage import Storage
    from controlrecord.ui import MainWindow, STYLE

    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setApplicationName("ControlRecord")
    app.setOrganizationName("ControlRecord")
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "controlrecord" / "app.ico")))
    instance = None
    if not args.smoke_test:
        instance = SingleInstance()
        if instance.already_running:
            QMessageBox.information(None, "ControlRecord", "工具已在執行中，請從工作列開啟現有視窗。")
            instance.close()
            return 0
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    # The portable bundle has app/main.py and stores user data beside its launcher.
    if base.name == "app" and (base.parent / "runtime").is_dir():
        base = base.parent
    data = args.data_dir or base / "data"
    window = None
    try:
        storage = Storage(data)
        handler = RotatingFileHandler(data / "application.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")

        def report_exception(kind, value, traceback):
            logging.error("Unhandled error", exc_info=(kind, value, traceback))
            if window:
                window.emergency()
            QMessageBox.critical(window, "程式錯誤", f"{value}\n詳細資訊已記錄於 application.log。")

        sys.excepthook = report_exception
        window = MainWindow(storage, services=not args.smoke_test)
        window.show()
        if args.smoke_test:
            def snapshot():
                window.grab().save(str(data / "ui-preview.png"))
                window.close()
            QTimer.singleShot(700, snapshot)
        return app.exec()
    except Exception as exc:
        logging.exception("Startup error")
        QMessageBox.critical(None, "無法啟動", f"{exc}\n請將程式解壓至可寫入的資料夾。")
        return 1
    finally:
        if window and window.services:
            window.power.close()
        if instance:
            instance.close()


if __name__ == "__main__":
    raise SystemExit(main())

