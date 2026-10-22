"""Synchronize reviewed app sources/docs and create a portable ZIP + SHA256."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controlrecord import __version__
bundle = ROOT / "dist" / "ControlRecord"
# Only update application files and documentation. Never touch user data.
shutil.copy2(ROOT / "main.py", bundle / "app/main.py")
for source in (ROOT / "controlrecord").iterdir():
    if source.is_file() and source.suffix in (".py", ".ico"):
        shutil.copy2(source, bundle / "app/controlrecord" / source.name)
for name in ("README.md", "DEVELOPING.md", "TESTING.md", "THIRD_PARTY_NOTICES.md", "requirements.txt", "requirements-lock.txt"):
    shutil.copy2(ROOT / name, bundle / name)

build_info_path = bundle / "build-info.json"
if build_info_path.exists():
    build_info = json.loads(build_info_path.read_text(encoding="utf-8"))
    build_info["version"] = __version__
    build_info_path.write_text(json.dumps(build_info, ensure_ascii=False, indent=2), encoding="utf-8")

destination = ROOT / "dist" / f"ControlRecord-{__version__}-win64.zip"
with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in bundle.rglob("*"):
        relative = path.relative_to(bundle)
        if path.is_file() and "__pycache__" not in relative.parts and relative.parts[0] != "data":
            archive.write(path, "ControlRecord/" + relative.as_posix())
digest = hashlib.sha256(destination.read_bytes()).hexdigest()
destination.with_suffix(".zip.sha256").write_text(f"{digest}  {destination.name}\n", encoding="ascii")
print(f"{destination} ({destination.stat().st_size / 1024 / 1024:.1f} MiB)")
print(digest)

