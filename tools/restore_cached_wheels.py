"""Recover complete cached wheels for an offline build, without changing cache."""
import hashlib
from pathlib import Path
import shutil
import zipfile

WANTED = {"pynput", "imageio_ffmpeg", "pyside6_essentials", "shiboken6", "six"}
EXPECTED = {
    "pynput-1.8.1": "42dfcf27404459ca16ca889c8fb8ffe42a9fe54f722fd1a3e130728e59e768d2",
    "imageio_ffmpeg-0.6.0": "02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a",
}
destination = Path(__file__).resolve().parents[1] / "artifacts" / "wheels"
destination.mkdir(parents=True, exist_ok=True)
for path in (Path.home() / "AppData/Local/pip/cache/http-v2").rglob("*.body"):
    if not zipfile.is_zipfile(path):
        continue
    with zipfile.ZipFile(path) as archive:
        info = next((n for n in archive.namelist() if n.endswith(".dist-info/WHEEL")), None)
        if not info:
            continue
        stem = info.split("/")[0].removesuffix(".dist-info")
        if stem.split("-")[0].lower() not in WANTED:
            continue
        tags = [line[5:].strip() for line in archive.read(info).decode().splitlines() if line.startswith("Tag: ")]
        if not tags:
            continue
        if stem in EXPECTED and hashlib.sha256(path.read_bytes()).hexdigest() != EXPECTED[stem]:
            raise RuntimeError(f"Cached wheel checksum mismatch: {stem}")
        # A wheel may have multiple compatible tags. The first is sufficient.
        tag = next((t for t in tags if t.startswith("py3-")), tags[0])
        target = destination / f"{stem}-{tag}.whl"
        shutil.copy2(path, target)
        print(target.name)

