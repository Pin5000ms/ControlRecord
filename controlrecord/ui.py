from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
import threading
import time
import uuid

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal, QSize
from PySide6.QtGui import QCloseEvent, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .capture import Hotkeys, MouseRecorder
from . import __version__
from .model import Script, save_script
from .storage import Storage
from .windows import PowerGuard, desktop_available, screen_info
from .worker import RunWorker
from .overlay import RecordingOverlay, play_start_sound


STYLE = """
QWidget { font-family: 'Microsoft JhengHei UI', 'Segoe UI'; font-size: 14px; color: #203044; }
QMainWindow { background: #f3f5f8; }
QMessageBox { background-color: #f3f5f8; color: #203044; }
QMessageBox QLabel { background-color: transparent; color: #203044; }
QMessageBox QDialogButtonBox { background-color: transparent; }
QMessageBox QPushButton { background-color: white; color: #203044; }
QMessageBox QPushButton:focus { border: 2px solid #087f73; }
QMessageBox QPushButton:hover { background-color: #edf3f7; }
QWidget#workspace, QWidget#dashboard, QWidget#history, QScrollArea#dashboardScroll,
QWidget#dashboardViewport { background: #f3f5f8; }
QLabel { background: transparent; }
QWidget#scriptRow { background: transparent; }
QPushButton#deleteScript { color: #b43c3c; padding: 5px 7px; }
QFrame#header { background: #14283b; border-radius: 14px; }
QLabel#brand { color: white; font-size: 28px; font-weight: 700; letter-spacing: 2px; }
QLabel#subtitle { color: #afc8d9; font-size: 13px; }
QLabel#badge { background: #254457; color: #a1e6db; border-radius: 12px; padding: 7px 12px; }
QFrame#card { background: white; border: 1px solid #dfe5ed; border-radius: 12px; }
QLabel#section { font-size: 17px; font-weight: 700; }
QLabel#muted { color: #65768a; font-size: 13px; }
QLabel#status { font-size: 21px; font-weight: 700; color: #086d64; }
QLabel#notice { background: #eaf4f2; color: #32615a; border-radius: 8px; padding: 12px; }
QPushButton { background: white; border: 1px solid #cbd5e0; border-radius: 7px; padding: 9px 15px; }
QPushButton:hover { background: #edf3f7; border-color: #8b9cae; }
QPushButton:disabled { color: #a4afbb; background: #f2f4f6; border-color: #e4e8ed; }
QPushButton#primary { background: #087f73; border-color: #087f73; color: white; font-weight: 700; }
QPushButton#primary:hover { background: #066b62; }
QPushButton#primary:disabled { background: #b1cbc6; border-color: #b1cbc6; }
QPushButton#stop { color: #b43c3c; border-color: #e2bbbb; background: #fff6f6; }
QPushButton#stop:disabled { color: #bbb; border-color: #ddd; background: #f7f7f7; }
QLineEdit, QSpinBox { background: white; padding: 8px; border: 1px solid #cbd5e0; border-radius: 6px; }
QSpinBox { min-height: 26px; padding: 4px 22px 4px 8px; }
QSpinBox QLineEdit { padding: 0; border: none; background: transparent; }
QLineEdit:focus, QSpinBox:focus { border-color: #087f73; }
QListWidget { background: white; border: none; outline: 0; }
QListWidget::item { padding: 13px 9px; border-bottom: 1px solid #edf0f4; }
QListWidget::item:selected { background: #e6f4f0; color: #075d54; border-radius: 7px; }
QTabWidget::pane { border: none; background: #f3f5f8; }
QTabBar::tab { padding: 10px 18px; border-bottom: 3px solid transparent; }
QTabBar::tab:selected { border-bottom-color: #087f73; color: #087f73; font-weight: 700; }
QTableWidget { background: white; border: 1px solid #dfe5ed; border-radius: 8px; gridline-color: #edf0f4; }
QHeaderView::section { background: #eaf0f5; border: none; padding: 10px; font-weight: 700; }
QProgressBar { border: none; border-radius: 4px; background: #e8eef2; min-height: 8px; max-height: 8px; }
QProgressBar::chunk { background: #0b9b8a; border-radius: 4px; }
QCheckBox { spacing: 8px; }
"""


def label(text, name=None, wrap=False):
    result = QLabel(text)
    if name:
        result.setObjectName(name)
    result.setWordWrap(wrap)
    return result


def card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    return frame, layout


def duration_text(seconds):
    total = max(0, int(seconds))
    return f"{total // 3600:02}:{total // 60 % 60:02}:{total % 60:02}"


class HotkeySignals(QObject):
    finish = Signal()
    emergency = Signal()


class MainWindow(QMainWindow):
    def __init__(self, storage: Storage, services=True):
        super().__init__()
        self.storage = storage
        self.services = services
        self.state = "idle"
        self.recorder = None
        self.worker = None
        self.pending_script = None
        self.pending_repeats = 1
        self.pending_name = ""
        self.cancel = threading.Event()
        self.deadline = 0.0
        self.close_pending = False
        self.history_records = []
        self.power = PowerGuard()
        self.hotkeys = None
        self.hotkeys_ok = not services
        self.last_result = None
        self.recording_overlay = RecordingOverlay()
        self.setWindowTitle("ControlRecord · 滑鼠錄製工具")
        self.setMinimumSize(900, 700)
        self.resize(1080, 840)
        self.setStyleSheet(STYLE)
        self._build()
        self.bridge = HotkeySignals()
        self.bridge.finish.connect(self.finish_recording)
        self.bridge.emergency.connect(self.stop)
        if services:
            try:
                self.hotkeys = Hotkeys(self.bridge.finish.emit, self.emergency)
                self.hotkeys.start()
                self.hotkeys_ok = True
            except Exception as exc:
                self.message.setText(f"快捷鍵無法啟動：{exc}")
            self.update_power()
        self.refresh_scripts()
        self.refresh_history()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        self._controls()

    def _build(self):
        root = QWidget()
        root.setObjectName("workspace")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 22, 24, 18)
        outer.setSpacing(18)
        header = QFrame()
        header.setObjectName("header")
        head = QHBoxLayout(header)
        head.setContentsMargins(24, 20, 24, 20)
        brand = QVBoxLayout()
        brand.addWidget(label("CONTROL RECORD", "brand"))
        head.addLayout(brand)
        head.addStretch()
        head.addWidget(label(f"v{__version__}", "badge"))
        outer.addWidget(header)
        body = QHBoxLayout()
        body.setSpacing(18)
        outer.addLayout(body, 1)

        sidebar, side = card()
        sidebar.setFixedWidth(290)
        side.addWidget(label("我的腳本", "section"))
        self.script_list = QListWidget()
        self.script_list.currentItemChanged.connect(self.selection_changed)
        side.addWidget(self.script_list, 1)
        self.empty_label = label("尚無腳本\n在右側錄製第一個操作流程。", "muted", True)
        side.addWidget(self.empty_label)
        buttons = QHBoxLayout()
        self.import_button = QPushButton("匯入")
        self.export_button = QPushButton("匯出")
        self.import_button.clicked.connect(self.import_script)
        self.export_button.clicked.connect(self.export_script)
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.export_button)
        side.addLayout(buttons)
        self.folder_button = QPushButton("開啟資料夾")
        self.folder_button.clicked.connect(lambda: self.open_path(self.storage.root))
        side.addWidget(self.folder_button)
        body.addWidget(sidebar)

        self.tabs = QTabWidget()
        body.addWidget(self.tabs, 1)
        dashboard = QWidget()
        dashboard.setObjectName("dashboard")
        dash = QVBoxLayout(dashboard)
        dash.setContentsMargins(0, 12, 0, 0)
        dash.setSpacing(14)
        dashboard_scroll = QScrollArea()
        dashboard_scroll.setObjectName("dashboardScroll")
        dashboard_scroll.viewport().setObjectName("dashboardViewport")
        dashboard_scroll.setWidgetResizable(True)
        dashboard_scroll.setFrameShape(QFrame.Shape.NoFrame)
        dashboard_scroll.setWidget(dashboard)
        self.tabs.addTab(dashboard_scroll, "操作台")

        record_card, record_layout = card()
        record_layout.addWidget(label("01  錄製操作", "section"))
        row = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("新腳本名稱，例如：每日操作")
        self.name_edit.setMaxLength(100)
        self.record_button = QPushButton("開始錄製")
        self.record_button.clicked.connect(self.prepare_recording)
        row.addWidget(self.name_edit, 1)
        row.addWidget(self.record_button)
        record_layout.addLayout(row)
        record_layout.addWidget(label("準備 3 秒後開始；按 F8 結束並自動儲存。", "muted", True))
        self.start_sound = QCheckBox("錄製開始時播放提示音")
        self.start_sound.setChecked(True)
        record_layout.addWidget(self.start_sound)
        dash.addWidget(record_card)

        run_card, run_layout = card()
        run_layout.addWidget(label("02  執行腳本", "section"))
        self.script_info = label("請先從左側選擇腳本。", "muted", True)
        run_layout.addWidget(self.script_info)
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(12)
        form.addWidget(label("重複次數"), 0, 0)
        self.repeat = QSpinBox()
        self.repeat.setRange(1, 9999)
        self.repeat.setSuffix(" 次")
        self.repeat.setFixedHeight(38)
        form.addWidget(self.repeat, 0, 1, 1, 3)
        form.addWidget(label("延遲執行"), 1, 0)
        self.hours = QSpinBox()
        self.hours.setRange(0, 168)
        self.hours.setSuffix(" 時")
        self.minutes = QSpinBox()
        self.minutes.setRange(0, 59)
        self.minutes.setSuffix(" 分")
        self.seconds = QSpinBox()
        self.seconds.setRange(0, 59)
        self.seconds.setSuffix(" 秒")
        self.seconds.setValue(3)
        for column, widget in enumerate((self.hours, self.minutes, self.seconds), 1):
            widget.setFixedHeight(38)
            form.addWidget(widget, 1, column)
        run_layout.addLayout(form)
        self.record_video = QCheckBox("執行時錄製螢幕影片")
        self.record_video.setChecked(True)
        run_layout.addWidget(self.record_video)
        self.run_button = QPushButton("執行腳本")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.prepare_run)
        run_layout.addWidget(self.run_button)
        run_layout.addWidget(label("單螢幕 · 含游標 · 無聲音 · 20 FPS · 每次任務一個 MP4", "muted", True))
        dash.addWidget(run_card)

        state_card, state_layout = card()
        self.status_label = label("準備就緒", "status", True)
        state_layout.addWidget(self.status_label)
        self.message = label("錄製與重播時，請維持目標程式視窗的位置與大小。", "muted", True)
        state_layout.addWidget(self.message)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        state_layout.addWidget(self.progress)
        self.stop_button = QPushButton("停止  F12")
        self.stop_button.setObjectName("stop")
        self.stop_button.clicked.connect(self.stop)
        state_layout.addWidget(self.stop_button)
        dash.addWidget(state_card)
        dash.addStretch()

        history = QWidget()
        history.setObjectName("history")
        hist = QVBoxLayout(history)
        hist.setContentsMargins(0, 12, 0, 0)
        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(["開始時間", "腳本", "狀態", "完成次數"])
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.verticalHeader().hide()
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.itemSelectionChanged.connect(self.history_selected)
        self.history_table.cellDoubleClicked.connect(lambda *_: self.play_video())
        hist.addWidget(self.history_table, 1)
        self.history_detail = label("每次執行的影片與結果會顯示在這裡。", "muted", True)
        hist.addWidget(self.history_detail)
        actions = QHBoxLayout()
        self.video_button = QPushButton("播放影片")
        self.video_button.clicked.connect(self.play_video)
        self.log_button = QPushButton("開啟執行資料夾")
        self.log_button.clicked.connect(self.open_run_folder)
        actions.addWidget(self.video_button)
        actions.addWidget(self.log_button)
        hist.addLayout(actions)
        self.tabs.addTab(history, "執行紀錄")

        footer = QHBoxLayout()
        self.power_label = label("防休眠未啟用", "muted")
        footer.addWidget(self.power_label)
        footer.addStretch()
        self.keep_display = QCheckBox("保持螢幕亮起")
        self.keep_display.setChecked(bool(self.storage.settings().get("keep_display", True)))
        self.keep_display.toggled.connect(self.update_power)
        footer.addWidget(self.keep_display)
        outer.addLayout(footer)

    def update_power(self):
        if not self.services:
            return
        try:
            self.power.set(self.keep_display.isChecked())
            self.power_label.setText("● 防休眠已啟用 · 關閉程式後解除")
            self.storage.save_settings({"keep_display": self.keep_display.isChecked()})
        except OSError as exc:
            self.power_label.setText(f"防休眠設定失敗：{exc}")

    def selected_script(self) -> Script | None:
        item = self.script_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def refresh_scripts(self, select_id=None):
        current = self.selected_script()
        select_id = select_id or (current.id if current else None)
        scripts, errors = self.storage.list_scripts()
        self.script_list.clear()
        for script in scripts:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, script)
            item.setSizeHint(QSize(230, 76))
            self.script_list.addItem(item)
            row = QWidget()
            row.setObjectName("scriptRow")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 6, 8, 6)
            details = label(f"{script.name}\n{duration_text(script.duration)} · {len(script.events):,} 個事件")
            details.setTextFormat(Qt.TextFormat.PlainText)
            details.setMinimumWidth(0)
            details.setToolTip(script.name)
            details.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(details, 1)
            delete = QPushButton("刪除")
            delete.setObjectName("deleteScript")
            delete.setToolTip(f"刪除腳本：{script.name}")
            delete.clicked.connect(lambda checked=False, script=script: self.delete_script(script))
            layout.addWidget(delete)
            self.script_list.setItemWidget(item, row)
            if script.id == select_id:
                self.script_list.setCurrentItem(item)
        if self.script_list.currentRow() < 0 and scripts:
            self.script_list.setCurrentRow(0)
        self.empty_label.setVisible(not scripts)
        if errors:
            self.message.setText("部分腳本無法讀取：" + "；".join(errors[:3]))
        self._controls()

    def selection_changed(self, *_):
        script = self.selected_script()
        if script:
            self.script_info.setText(f"{script.name}  ·  {duration_text(script.duration)}\n"
                                     f"錄製環境：{script.screen.width} × {script.screen.height} / "
                                     f"縮放 {script.screen.dpi / 96:.0%}")
        else:
            self.script_info.setText("請先從左側選擇腳本。")
        self._controls()

    def _controls(self):
        if not hasattr(self, "run_button"):
            return
        idle = self.state == "idle"
        usable = idle and self.hotkeys_ok
        self.record_button.setEnabled(usable)
        self.run_button.setEnabled(usable and self.selected_script() is not None)
        self.stop_button.setEnabled(not idle and self.state != "stopping")
        self.export_button.setEnabled(idle and self.selected_script() is not None)
        self.import_button.setEnabled(idle)
        self.folder_button.setEnabled(idle)
        self.script_list.setEnabled(idle)
        for widget in (self.name_edit, self.repeat, self.hours, self.minutes, self.seconds, self.record_video, self.start_sound):
            widget.setEnabled(idle)
        self.tabs.setTabEnabled(1, idle)

    def error(self, message):
        self.message.setText(str(message))
        QMessageBox.warning(self, "無法完成操作", str(message))

    def preflight(self):
        if self.services:
            self.hotkeys.check()
            if not desktop_available():
                raise RuntimeError("請在已解鎖的 Windows 桌面操作。")
        screen = screen_info()
        if screen.monitors != 1:
            raise RuntimeError("此初版僅支援單螢幕，請先切換成單螢幕。")
        return screen

    def prepare_recording(self):
        if self.state != "idle":
            return
        try:
            self.preflight()
            self.pending_name = self.name_edit.text().strip() or datetime.now().strftime("操作 %m-%d %H-%M-%S")
            self.cancel.clear()
            self.state = "prepare_record"
            self.deadline = time.perf_counter() + 3
            self.status_label.setText("準備錄製 · 3 秒")
            self.recording_overlay.countdown(3)
            self.message.setText("請將游標移至目標程式。開始後視窗會自動縮小，按 F8 儲存。")
            self.progress.setValue(0)
            self._controls()
        except Exception as exc:
            self.error(exc)

    def begin_recording(self):
        try:
            screen = self.preflight()
            self.showMinimized()
            self.recorder = MouseRecorder(self.pending_name, screen)
            self.recorder.start()
            self.state = "recording"
            self.recording_overlay.recording(0, 0)
            if self.start_sound.isChecked():
                play_start_sound()
            self.status_label.setText("正在錄製 · F8 結束")
            self._controls()
        except Exception as exc:
            self.state = "idle"
            self.recording_overlay.hide()
            self.recorder = None
            logging.exception("Recording startup failed")
            self.showNormal()
            self._controls()
            self.error(exc)

    def finish_recording(self, reason="按下 F8", interrupted=False):
        if self.state != "recording":
            return
        recorder = self.recorder
        self.recording_overlay.hide()
        self.recorder = None
        try:
            script = recorder.stop()
            self.storage.save(script)
            logging.info("Recording saved: id=%s reason=%r interrupted=%s", script.id, reason, interrupted)
            self.status_label.setText("錄製已中斷，腳本已儲存" if interrupted else "腳本已儲存")
            summary = f"{script.name} · {duration_text(script.duration)} · {len(script.events):,} 個事件"
            self.message.setText(summary + (f"\n停止原因：{reason}" if interrupted else ""))
            self.state = "idle"
            self.refresh_scripts(script.id)
            return True
        except Exception as exc:
            logging.exception("Recording could not be saved: reason=%r", reason)
            self.state = "idle"
            self.error(exc)
            return False
        finally:
            self.showNormal()
            self.raise_()
            self._controls()

    def prepare_run(self):
        if self.state != "idle":
            return
        script = self.selected_script()
        if not script:
            return
        try:
            script.validate()
            current = self.preflight()
            if current != script.screen:
                raise RuntimeError("目前螢幕解析度或縮放與錄製時不同。請還原原始設定或重新錄製。")
            self.pending_script = script
            self.pending_repeats = self.repeat.value()
            self.cancel.clear()
            delay = self.hours.value() * 3600 + self.minutes.value() * 60 + self.seconds.value()
            self.deadline = time.perf_counter() + delay
            self.state = "countdown"
            self.status_label.setText("等待執行")
            self.message.setText("請將目標程式切換到錄製時的起始畫面；倒數結束後本視窗會縮小。")
            self.progress.setValue(0)
            self.last_result = None
            self._controls()
        except Exception as exc:
            self.error(exc)

    def begin_run(self):
        try:
            if self.preflight() != self.pending_script.screen:
                raise RuntimeError("倒數期間螢幕設定改變，已取消執行。")
            self.showMinimized()
            self.state = "running"
            folder = self.storage.runs / (datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8])
            self.worker = RunWorker(self.pending_script, self.pending_repeats, folder,
                                    self.cancel, self.hotkeys.check if self.services else lambda: None, self,
                                    record_video=self.record_video.isChecked())
            self.worker.stage.connect(self.run_stage)
            self.worker.progress.connect(self.run_progress)
            self.worker.result.connect(self.run_result)
            self.worker.finished.connect(self.run_finished)
            self.worker.start()
            self._controls()
        except Exception as exc:
            self.state = "idle"
            self.showNormal()
            self._controls()
            self.error(exc)

    def run_stage(self, message):
        self.status_label.setText(message)
        if "保存影片" in message or "保存執行紀錄" in message:
            self.state = "stopping"
            self._controls()

    def run_progress(self, completed, total):
        self.progress.setValue(round(completed / total * 100))
        self.message.setText(f"已完成 {completed} / {total} 次" + (" · 正在錄影" if self.record_video.isChecked() else ""))

    def run_result(self, record):
        self.last_result = record
        self.refresh_history()

    def run_finished(self):
        self.state = "idle"
        record = self.last_result or {"status": "failed", "error": "未收到執行結果"}
        text = {"completed": "執行完成", "stopped": "已停止執行", "failed": "執行未完成"}
        self.status_label.setText(text.get(record["status"], "已結束"))
        detail = f"完成 {record.get('completed', 0)} / {record.get('repeats', self.pending_repeats)} 次。"
        if record.get("video"):
            detail += " 影片已保存，可至「執行紀錄」查看。"
        self.message.setText(" ".join(filter(None, [detail, record.get("error"), record.get("warning")])))
        self.worker.deleteLater()
        self.worker = None
        self.showNormal()
        self._controls()
        if self.close_pending:
            self.close()

    def emergency(self):
        self.cancel.set()
        self.bridge.emergency.emit()

    def stop(self):
        if self.state == "idle":
            return
        self.cancel.set()
        if self.state == "recording":
            self.finish_recording(reason="按下 F12 或停止按鈕")
        elif self.state in ("prepare_record", "countdown"):
            self.recording_overlay.hide()
            self.state = "idle"
            self.status_label.setText("已取消倒數")
            self.message.setText("尚未開始操作。")
        else:
            self.state = "stopping"
            self.status_label.setText("已要求停止，正在保存執行結果…")
        self._controls()

    def tick(self):
        try:
            if self.services and self.hotkeys_ok:
                self.hotkeys.check()
            if self.state in ("prepare_record", "countdown"):
                if self.cancel.is_set():
                    self.stop()
                    return
                remaining = max(0, self.deadline - time.perf_counter())
                if self.state == "prepare_record":
                    self.recording_overlay.countdown(remaining)
                self.status_label.setText(("準備錄製" if self.state == "prepare_record" else "距離執行") + f" · {duration_text(remaining + 0.999)}")
                if remaining <= 0:
                    if self.state == "prepare_record":
                        self.begin_recording()
                    else:
                        self.begin_run()
            elif self.state == "recording":
                self.recorder.check()
                if screen_info() != self.recorder.screen:
                    raise RuntimeError("螢幕解析度、縮放或螢幕數量已改變，錄製已停止。")
                if not desktop_available():
                    raise RuntimeError("Windows 桌面已鎖定或切換，錄製已停止。")
                elapsed = time.perf_counter() - self.recorder.started
                self.recording_overlay.recording(elapsed, self.recorder.count())
                self.message.setText(f"{duration_text(elapsed)} · {self.recorder.count():,} 個事件 · F8 儲存")
        except Exception as exc:
            was_recording = self.state == "recording"
            logging.exception("Automatic stop: state=%s reason=%s", self.state, exc)
            saved = False
            if was_recording:
                saved = self.finish_recording(reason=str(exc), interrupted=True)
            else:
                self.stop()
            if self.hotkeys and not self.hotkeys.listener.is_alive():
                self.hotkeys_ok = False
            if not was_recording:
                self.message.setText(str(exc))
            self._controls()
            if was_recording:
                note = "已保存中斷前的錄製內容。" if saved else "錄製內容未能保存，請查看程式日誌。"
                QMessageBox.warning(self, "錄製自動停止", f"{exc}\n\n{note}\n詳細原因已寫入 data/application.log。")

    def delete_script(self, script):
        if self.state != "idle":
            return
        answer = QMessageBox.question(self, "刪除腳本", f"確定刪除「{script.name}」？\n已保存的執行紀錄與影片會保留。",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.storage.delete(script.id)
            self.refresh_scripts()
            self.status_label.setText("腳本已刪除")
        except OSError as exc:
            self.error(exc)

    def import_script(self):
        path, _ = QFileDialog.getOpenFileName(self, "匯入腳本", "", "ControlRecord 腳本 (*.json)")
        if path:
            try:
                script = self.storage.import_file(Path(path))
                self.refresh_scripts(script.id)
                self.status_label.setText("腳本已匯入")
            except Exception as exc:
                self.error(exc)

    def export_script(self):
        script = self.selected_script()
        if not script:
            return
        path, _ = QFileDialog.getSaveFileName(self, "匯出腳本", "script.json", "ControlRecord 腳本 (*.json)")
        if path:
            try:
                save_script(Path(path), script)
                self.status_label.setText("腳本已匯出")
            except Exception as exc:
                self.error(exc)

    def refresh_history(self):
        self.history_records = self.storage.history()
        self.history_table.setRowCount(len(self.history_records))
        states = {"completed": "已完成", "stopped": "已中止", "failed": "失敗", "running": "未正常結束"}
        for row, record in enumerate(self.history_records):
            values = [record.get("started_at", "").replace("T", " ")[:19], record.get("script_name", ""),
                      states.get(record.get("status"), "未知"), f"{record.get('completed', 0)} / {record.get('repeats', 0)}"]
            for column, text in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(text))
        if self.history_records:
            self.history_table.selectRow(0)
        self.history_selected()

    def selected_history(self):
        row = self.history_table.currentRow()
        return self.history_records[row] if 0 <= row < len(self.history_records) else None

    def history_selected(self):
        record = self.selected_history()
        self.video_button.setEnabled(bool(record and record.get("video")))
        self.log_button.setEnabled(bool(record))
        if record:
            self.history_detail.setText("\n".join(filter(None, ["本次執行未啟用錄影" if record.get("record_video") is False else "", record.get("error"), record.get("warning"), record.get("folder")])))

    def play_video(self):
        record = self.selected_history()
        if record and record.get("video"):
            path = Path(record["folder"]) / record["video"]
            if path.is_file():
                self.open_path(path)
            else:
                self.error("影片檔案已被移動或刪除。")

    def open_run_folder(self):
        record = self.selected_history()
        if record:
            self.open_path(Path(record["folder"]))

    @staticmethod
    def open_path(path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def closeEvent(self, event: QCloseEvent):
        if self.worker and self.worker.isRunning():
            self.close_pending = True
            self.stop()
            event.ignore()
            return
        if self.state == "recording":
            self.finish_recording(reason="關閉程式視窗")
        self.timer.stop()
        self.recording_overlay.close()
        self.recording_overlay.deleteLater()
        if self.hotkeys:
            self.hotkeys.close()
        if self.services:
            self.power.close()
        event.accept()

