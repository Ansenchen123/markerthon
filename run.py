#!/usr/bin/env python3
"""Start the backend API from the repository root."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"


def _python_executable() -> str:
    root_venv_python = ROOT_DIR / ".venv" / "bin" / "python"
    if root_venv_python.exists():
        return str(root_venv_python)
    backend_venv_python = BACKEND_DIR / ".venv" / "bin" / "python"
    if backend_venv_python.exists():
        return str(backend_venv_python)
    return sys.executable


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the reusable-container backend API.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind. Default: 127.0.0.1")
    parser.add_argument("--port", default="8000", help="Port to bind. Default: 8000")
    parser.add_argument("--no-reload", action="store_true", help="Disable uvicorn auto reload.")
    parser.add_argument("--seed", action="store_true", help="Seed demo stores and users before starting.")
    args = parser.parse_args()

    if not (BACKEND_DIR / "app" / "main.py").exists():
        print(f"Cannot find backend app at {BACKEND_DIR / 'app' / 'main.py'}", file=sys.stderr)
        return 1

    python = _python_executable()
    env = os.environ.copy()

    if args.seed:
        seed_result = subprocess.run([python, "-m", "app.seed"], cwd=BACKEND_DIR, env=env)
        if seed_result.returncode != 0:
            return seed_result.returncode

    command = [
        python,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if not args.no_reload:
        command.append("--reload")

    print(f"Starting backend at http://{args.host}:{args.port}")
    print(f"Working directory: {BACKEND_DIR}")
    try:
        return subprocess.call(command, cwd=BACKEND_DIR, env=env)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
