from datetime import datetime

from PySide6.QtCore import QDateTime, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QDateTimeEdit, QTimeEdit, QPushButton, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView)

from .schedules import Schedules


class SchedulePage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName('workspace')
        self.store = None
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        self.notice = QLabel('依本機日期時間執行，每次 1 輪。程式需開啟、桌面需解鎖。\n忙碌或錯過時間會略過；每週排程繼續等待下次執行。')
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.script = QComboBox()
        layout.addWidget(QLabel('腳本'))
        layout.addWidget(self.script)
        self.mode = QComboBox()
        self.mode.addItems(['指定日期時間（一次）', '每週重複'])
        layout.addWidget(self.mode)
        self.date = QDateTimeEdit(QDateTime.currentDateTime().addSecs(300))
        self.date.setDisplayFormat('yyyy/MM/dd HH:mm')
        self.date.setCalendarPopup(True)
        layout.addWidget(self.date)
        self.week = QWidget()
        row = QHBoxLayout(self.week)
        row.setContentsMargins(0, 0, 0, 0)
        self.days = []
        for day in '一二三四五六日':
            button = QPushButton(day)
            button.setCheckable(True)
            button.setObjectName('weekday')
            row.addWidget(button)
            self.days.append(button)
        self.clock = QTimeEdit()
        self.clock.setDisplayFormat('HH:mm')
        row.addWidget(self.clock)
        layout.addWidget(self.week)
        self.mode.currentIndexChanged.connect(self.change_mode)
        self.change_mode()
        self.video = QCheckBox('執行時錄影')
        self.video.setChecked(True)
        layout.addWidget(self.video)
        self.add = QPushButton('新增排程')
        self.add.clicked.connect(self.add_schedule)
        layout.addWidget(self.add)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['腳本／規則', '下次時間', '錄影', '狀態', '操作'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        try:
            self.store = Schedules(window.storage.root)
            self.store.poll(datetime.now(), lambda _: '', startup=True)
        except Exception as exc:
            self.notice.setText(f'排程載入失敗，已停止排程功能：{exc}')
            self.store = None
            self.add.setEnabled(False)
        self.refresh_scripts()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(1000)

    def change_mode(self):
        weekly = self.mode.currentIndex() == 1
        self.week.setVisible(weekly)
        self.date.setVisible(not weekly)

    def refresh_scripts(self):
        selected = self.script.currentData()
        self.script.clear()
        for script in self.window.storage.list_scripts()[0]:
            self.script.addItem(script.name, script.id)
        index = self.script.findData(selected)
        if index >= 0:
            self.script.setCurrentIndex(index)

    def add_schedule(self):
        if not self.store:
            return
        try:
            script = next((s for s in self.window.storage.list_scripts()[0] if s.id == self.script.currentData()), None)
            if script is None:
                raise ValueError('請先錄製或匯入腳本。')
            self.store.add(script, 'weekly' if self.mode.currentIndex() else 'once',
                self.date.dateTime().toPython().replace(second=0, microsecond=0),
                [i for i, button in enumerate(self.days) if button.isChecked()],
                self.clock.time().toString('HH:mm'), self.video.isChecked(), datetime.now())
            self.refresh()
        except Exception as exc:
            self.window.error(exc)

    def remove(self, item):
        old = list(self.store.items)
        self.store.items.remove(item)
        try:
            self.store.save()
            self.refresh()
        except Exception as exc:
            self.store.items = old
            self.window.error(exc)

    def cancel_script(self, script_id):
        if not self.store:
            return
        for item in self.store.items:
            if item['script_id'] == script_id and item['enabled']:
                item['enabled'] = False
                item['status'] = '已取消：腳本已刪除'
        try:
            self.store.save()
        except OSError as exc:
            self.timer.stop()
            self.add.setEnabled(False)
            self.notice.setText(f'排程保存失敗，已停止排程功能：{exc}')
        self.refresh()

    def refresh(self):
        items = self.store.items if self.store else []
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            rule = '單次' if item['kind'] == 'once' else '每週' + '、'.join('一二三四五六日'[i] for i in item['days']) + ' ' + item['clock']
            values = [item['name'] + '\n' + rule,
                      item['next'].replace('T', ' ')[:16] if item['enabled'] else '—',
                      '是' if item['video'] else '否', item['status']]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                self.table.setItem(row, column, cell)
            button = QPushButton('取消' if item['enabled'] else '移除')
            button.clicked.connect(lambda checked=False, item=item: self.remove(item))
            self.table.setCellWidget(row, 4, button)
            self.table.setRowHeight(row, 64)

    def poll(self):
        if not self.store:
            return
        try:
            if self.store.poll(datetime.now(), self.window.launch_schedule):
                self.refresh()
        except Exception as exc:
            self.timer.stop()
            self.notice.setText(f'排程儲存失敗，已停止排程功能：{exc}')
            self.add.setEnabled(False)
