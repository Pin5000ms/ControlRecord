"""Offline, reproducible folder bundle using the installed CPython runtime.

No system packages/settings are modified. Build artifacts stay under dist/.
The small Windows launcher uses the .NET Framework already included in Win10/11.
"""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controlrecord import __version__


def copy_package_files(site: Path, destination: Path):
    for distribution in ("PySide6-Essentials", "shiboken6", "pynput", "six", "imageio-ffmpeg"):
        package = importlib.metadata.distribution(distribution)
        for item in package.files or []:
            relative = Path(str(item))
            if relative.is_absolute() or ".." in relative.parts or "__pycache__" in relative.parts:
                continue
            source = Path(package.locate_file(item))
            if source.is_file():
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)


def main():
    output = ROOT / "dist" / "ControlRecord"
    if output.exists():
        # Do not delete or overwrite an earlier build/user data.
        from datetime import datetime
        output = ROOT / "dist" / ("ControlRecord_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    output.mkdir(parents=True)
    runtime = output / "runtime"
    runtime.mkdir()
    base = Path(sys.base_prefix)
    version = f"{sys.version_info.major}{sys.version_info.minor}"
    for name in ("python.exe", "pythonw.exe", f"python{version}.dll", "python3.dll", "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
        source = base / name
        if source.exists():
            shutil.copy2(source, runtime / name)
    shutil.copytree(base / "DLLs", runtime / "DLLs", ignore=shutil.ignore_patterns("__pycache__", "*.pdb"))
    exclusions = {"site-packages", "test", "tests", "__pycache__", "idlelib", "tkinter", "turtledemo", "ensurepip"}
    with zipfile.ZipFile(runtime / f"python{version}.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in (base / "Lib").rglob("*.py"):
            relative = path.relative_to(base / "Lib")
            if not any(part in exclusions for part in relative.parts):
                archive.write(path, relative.as_posix())
    site = runtime / "Lib" / "site-packages"
    site.mkdir(parents=True)
    copy_package_files(Path(sysconfig.get_paths()["purelib"]), site)
    (runtime / f"python{version}._pth").write_text(
        f"python{version}.zip\nDLLs\nLib/site-packages\n../app\nimport site\n", encoding="utf-8")
    app = output / "app"
    app.mkdir()
    shutil.copy2(ROOT / "main.py", app / "main.py")
    shutil.copytree(ROOT / "controlrecord", app / "controlrecord", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("README.md", "DEVELOPING.md", "TESTING.md", "THIRD_PARTY_NOTICES.md", "requirements.txt", "requirements-lock.txt"):
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, output / name)
    compiler = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
    command = [str(compiler), "/nologo", "/target:winexe", "/platform:x64", "/optimize+",
               "/reference:System.Windows.Forms.dll", "/out:" + str(output / "ControlRecord.exe"),
               "/win32icon:" + str(ROOT / "controlrecord/app.ico"), str(ROOT / "tools/Launcher.cs")]
    subprocess.run(command, check=True)
    (output / "build-info.json").write_text(json.dumps({
        "version": __version__, "python": sys.version,
        "packages": {name: importlib.metadata.version(name) for name in ("PySide6-Essentials", "shiboken6", "pynput", "six", "imageio-ffmpeg")},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    # Validate the portable interpreter with the development environment disabled.
    subprocess.run([str(runtime / "python.exe"), "-I", "-c",
                    "import PySide6.QtWidgets, pynput, imageio_ffmpeg, controlrecord; print('Portable imports OK')"],
                   check=True, cwd=output)
    print(str(output))


if __name__ == "__main__":
    main()

