from __future__ import annotations

import json
from pathlib import Path
import uuid

from .model import Script, load_script, save_script, write_json


class Storage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.scripts = self.root / "scripts"
        self.runs = self.root / "runs"
        for path in (self.scripts, self.runs):
            path.mkdir(parents=True, exist_ok=True)

    def list_scripts(self):
        scripts, errors = [], []
        for path in self.scripts.glob("*.json"):
            try:
                scripts.append(load_script(path))
            except (OSError, ValueError) as exc:
                errors.append(f"{path.name}：{exc}")
        return sorted(scripts, key=lambda s: s.created_at, reverse=True), errors

    def save(self, script: Script):
        save_script(self.scripts / f"{script.id}.json", script)

    def import_file(self, path: Path) -> Script:
        script = load_script(path)
        script.id = uuid.uuid4().hex  # imports never overwrite existing scripts
        self.save(script)
        return script

    def delete(self, script_id: str):
        # Resolve the exact stored file; never interpret an imported ID as a path.
        for path in self.scripts.glob("*.json"):
            if path.stem == script_id:
                path.unlink()
                return
        raise FileNotFoundError("腳本已不存在，請重新整理清單。")

    def settings(self):
        try:
            value = json.loads((self.root / "settings.json").read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_settings(self, value: dict):
        write_json(self.root / "settings.json", value)

    def history(self):
        records = []
        for path in self.runs.glob("*/result.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                record["folder"] = str(path.parent)
                records.append(record)
            except (OSError, ValueError, TypeError):
                continue
        return sorted(records, key=lambda r: r.get("started_at", ""), reverse=True)

