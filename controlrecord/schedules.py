"""Persistent, at-most-once local schedules. Missed occurrences are not replayed."""
from datetime import datetime, timedelta
import json
import uuid

from .model import write_json


def next_weekly(days, clock, after):
    hour, minute = map(int, clock.split(':'))
    for offset in range(8):
        candidate = (after + timedelta(days=offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate.weekday() in days and candidate > after:
            return candidate
    raise ValueError('請至少選擇一個星期幾。')


class Schedules:
    def __init__(self, root):
        self.path = root / 'schedules.json'
        self.items = []
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, list):
                raise ValueError('排程檔案格式錯誤')
            for item in data:
                if not isinstance(item, dict) or any(not isinstance(item.get(key), str) for key in ('id', 'script_id', 'name', 'kind', 'next', 'clock', 'status')):
                    raise ValueError('排程欄位格式錯誤')
                if not isinstance(item.get('video'), bool) or not isinstance(item.get('enabled'), bool):
                    raise ValueError('排程開關格式錯誤')
                if not isinstance(item.get('days'), list) or any(type(day) is not int or day not in range(7) for day in item['days']):
                    raise ValueError('排程星期格式錯誤')
                datetime.fromisoformat(item['next'])
                if item['kind'] not in ('once', 'weekly') or not isinstance(item['enabled'], bool):
                    raise ValueError('排程格式錯誤')
                if item['kind'] == 'weekly':
                    next_weekly(item['days'], item['clock'], datetime.now())
            self.items = data

    def save(self):
        write_json(self.path, self.items)

    def add(self, script, kind, when, days, clock, video, now):
        due = next_weekly(days, clock, now) if kind == 'weekly' else when
        if due <= now:
            raise ValueError('請選擇未來的日期時間。')
        item = dict(id=uuid.uuid4().hex, script_id=script.id, name=script.name,
                    kind=kind, days=days, clock=clock, next=due.isoformat(),
                    video=video, enabled=True, status='等待執行')
        self.items.append(item)
        try:
            self.save()
        except Exception:
            self.items.remove(item)
            raise

    def poll(self, now, launch, startup=False):
        changed = False
        for item in sorted(self.items, key=lambda item: item['next']):
            if not item['enabled']:
                continue
            due = datetime.fromisoformat(item['next'])
            if due > now:
                continue
            changed = True
            # Persist consumption BEFORE any mouse input, including failed launches.
            item['status'] = '已領取執行；若程式中斷請查看執行紀錄'
            if item['kind'] == 'weekly':
                item['next'] = next_weekly(item['days'], item['clock'], now).isoformat()
            else:
                item['enabled'] = False
            self.save()
            if startup or (now - due).total_seconds() > 60:
                result = '略過：錯過執行時間'
            else:
                try:
                    result = launch(item)
                except Exception as exc:
                    result = f'失敗：{exc}'
            item['status'] = f'{now:%m-%d %H:%M} {result}'
            self.save()
        return changed
