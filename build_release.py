"""Builds the two downloads from this one folder:
    build/wisp-<version>-windows.zip   and   build/wisp-<version>-mac.zip
Run by the GitHub Action on every release; you can also run it yourself: python build_release.py v1.0.0
"""
import stat
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "build"

# Never shipped: personal data, build junk, dev files
EXCLUDE_DIRS = {".git", ".github", "build", "__pycache__", ".ruff_cache", ".venv", "jobs", "backups"}
EXCLUDE_FILES = {"config.json", "secrets.bin", "telemetry.json", "state.json", "timers.json", "focus.json",
                 "phone.json", "routines.json", "wisp.log", "sidekick.log", "build_release.py"}
EXCLUDE_PATHS = {"workspace/MEMORY.md", "workspace/mcp.json", "workspace/PLATFORM.md"}
EXCLUDE_TREES = {"workspace/output", "workspace/projects"}

WINDOWS_ONLY = {".bat", ".ps1"}
MAC_ONLY_SUFFIX = {".command", ".sh"}
MAC_ONLY_FILES = {"requirements-mac.txt"}
WINDOWS_ONLY_FILES = {"requirements.txt"}


def files_for(platform):
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT).as_posix()
        if path.is_dir() or any(part in EXCLUDE_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.name in EXCLUDE_FILES or rel in EXCLUDE_PATHS or any(rel.startswith(t + "/") for t in EXCLUDE_TREES):
            continue
        if path.suffix == ".zip":
            continue
        if platform == "mac" and (path.suffix in WINDOWS_ONLY or path.name in WINDOWS_ONLY_FILES):
            continue
        if platform == "windows" and (path.suffix in MAC_ONLY_SUFFIX or path.name in MAC_ONLY_FILES):
            continue
        yield path, rel


def build(version):
    version = version if version.startswith("v") else f"v{version}"
    OUT.mkdir(exist_ok=True)
    made = []
    for platform in ("windows", "mac"):
        target = OUT / f"wisp-{version}-{platform}.zip"
        target.unlink(missing_ok=True)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            for path, rel in files_for(platform):
                info = zipfile.ZipInfo.from_file(path, f"wisp/{rel}")
                mode = 0o755 if path.suffix in (".command", ".sh") else 0o644
                info.external_attr = (stat.S_IFREG | mode) << 16  # keep Mac scripts double-clickable
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, path.read_bytes())
        made.append(target)
        print(f"built {target.relative_to(ROOT)} ({target.stat().st_size // 1024} KB)")
    return made


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else __import__("app_info").VERSION)
