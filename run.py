# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""One command to run Sketchmaker, on Windows, Linux and macOS:

    uv run run.py
    uv run run.py --preflight   do everything except start the server

Environment: SKIP_FRONTEND_BUILD=1 keeps whatever is in frontend/dist.
SKETCHMAKER_ENV_FILE points at a different .env (default backend/.env).

Standard library only: this runs before the app's dependencies exist.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
WINDOWS = os.name == "nt"
PYTHON = BACKEND / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")

FFMPEG_HELP = {
    "nt": "winget install Gyan.FFmpeg",
    "posix": "sudo apt install ffmpeg (Linux), or brew install ffmpeg (macOS)",
}


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    # uv run may point this at its own environment; the backend has its own.
    env.pop("VIRTUAL_ENV", None)
    # Windows would otherwise read and print text in its legacy code page.
    env["PYTHONUTF8"] = "1"
    return env


def run(args: list, cwd: Path, **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run([str(a) for a in args], cwd=cwd, env=child_env(), check=True, **kwargs)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode or 1) from None
    except OSError as exc:
        fail(f"could not run {args[0]}: {exc}")


def needs_build() -> bool:
    built = FRONTEND / "dist" / "index.html"
    if not built.is_file():
        return True
    newest_allowed = built.stat().st_mtime
    sources = [FRONTEND / "index.html", FRONTEND / "package.json"]
    for folder in (FRONTEND / "src", FRONTEND / "public"):
        sources.extend(p for p in folder.rglob("*") if p.is_file())
    return any(p.stat().st_mtime > newest_allowed for p in sources if p.exists())


def build_frontend() -> None:
    if os.environ.get("SKIP_FRONTEND_BUILD") == "1":
        print("Skipping the frontend build (SKIP_FRONTEND_BUILD=1).")
        return
    if not needs_build():
        return
    npm = shutil.which("npm")
    if npm is None:
        fail("Node.js is not installed, and the frontend needs building. Get it from https://nodejs.org/")
    print("Building the frontend...")
    if not (FRONTEND / "node_modules").is_dir():
        run([npm, "ci"], FRONTEND)
    run([npm, "run", "build"], FRONTEND)


def read_config() -> dict:
    """A bad .env stops here with a clear message from the app."""
    script = ("import json; from app.config import settings as s; "
              "print(json.dumps({'host': s.HOST, 'port': s.PORT, 'proxies': s.TRUSTED_PROXIES}))")
    result = run([PYTHON, "-c", script], BACKEND, stdout=subprocess.PIPE, text=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def serve(config: dict) -> None:
    args = [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", config["host"], "--port", str(config["port"]),
            "--workers", "1", "--no-server-header"]
    if config["proxies"]:
        args += ["--proxy-headers", "--forwarded-allow-ips", config["proxies"]]
    else:
        args += ["--no-proxy-headers"]

    if WINDOWS:
        # Windows has no real exec: this process stays and hands on Ctrl+C.
        try:
            raise SystemExit(subprocess.call(args, cwd=BACKEND, env=child_env()))
        except KeyboardInterrupt:
            raise SystemExit(0) from None
    os.chdir(BACKEND)
    os.execve(args[0], args, child_env())


def main() -> None:
    preflight = "--preflight" in sys.argv[1:]

    uv = os.environ.get("UV") or shutil.which("uv")
    if uv is None:
        fail("uv is not installed. See https://docs.astral.sh/uv/getting-started/installation/")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("warning: ffmpeg and ffprobe were not found, so video tools and renders will fail until they are "
              f"installed: {FFMPEG_HELP.get(os.name, 'see https://ffmpeg.org/download.html')}", file=sys.stderr)

    run([uv, "sync", "--frozen", "--quiet"], BACKEND)

    override = os.environ.get("SKETCHMAKER_ENV_FILE")
    env_file = Path(override).expanduser() if override else BACKEND / ".env"
    if not env_file.exists():
        run([PYTHON, "-m", "app.cli", "init"], BACKEND)

    config = read_config()
    build_frontend()
    run([PYTHON, "-m", "app.cli", "migrate"], BACKEND)

    if preflight:
        print(f"Preflight passed. Would serve on {config['host']}:{config['port']}.")
        return
    serve(config)


if __name__ == "__main__":
    main()
