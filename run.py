#!/usr/bin/env python3
"""Start the backend API, merchant web app, and government web dashboard."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
WEBAPP_DIR = ROOT_DIR / "webapp"
WEB_DIR = ROOT_DIR / "web"


def _python_executable() -> str:
    root_venv_python = ROOT_DIR / ".venv" / "bin" / "python"
    if root_venv_python.exists():
        return str(root_venv_python)
    backend_venv_python = BACKEND_DIR / ".venv" / "bin" / "python"
    if backend_venv_python.exists():
        return str(backend_venv_python)
    return sys.executable


def _npm_executable() -> str | None:
    return shutil.which("npm")


def _ensure_backend_exists() -> bool:
    app_path = BACKEND_DIR / "app" / "main.py"
    if app_path.exists():
        return True
    print(f"Cannot find backend app at {app_path}", file=sys.stderr)
    return False


def _ensure_webapp_exists() -> bool:
    package_path = WEBAPP_DIR / "package.json"
    if package_path.exists():
        return True
    print(f"Cannot find web app package at {package_path}", file=sys.stderr)
    return False


def _ensure_web_exists() -> bool:
    package_path = WEB_DIR / "package.json"
    if package_path.exists():
        return True
    print(f"Cannot find government web package at {package_path}", file=sys.stderr)
    return False


def _install_webapp_dependencies(env: dict[str, str], skip_install: bool) -> int:
    if (WEBAPP_DIR / "node_modules").exists():
        return 0
    if skip_install:
        print("webapp/node_modules is missing. Run npm install in webapp/ or omit --skip-webapp-install.", file=sys.stderr)
        return 1

    npm = _npm_executable()
    if npm is None:
        print("Cannot find npm. Install Node.js/npm before starting the web app.", file=sys.stderr)
        return 1

    command = [npm, "ci"] if (WEBAPP_DIR / "package-lock.json").exists() else [npm, "install"]
    print(f"Installing web app dependencies with {' '.join(command)}")
    return subprocess.run(command, cwd=WEBAPP_DIR, env=env).returncode


def _install_web_dependencies(env: dict[str, str], skip_install: bool) -> int:
    if (WEB_DIR / "node_modules").exists():
        return 0
    if skip_install:
        print("web/node_modules is missing. Run npm install in web/ or omit --skip-web-install.", file=sys.stderr)
        return 1

    npm = _npm_executable()
    if npm is None:
        print("Cannot find npm. Install Node.js/npm before starting the government web.", file=sys.stderr)
        return 1

    command = [npm, "ci"] if (WEB_DIR / "package-lock.json").exists() else [npm, "install"]
    print(f"Installing government web dependencies with {' '.join(command)}")
    return subprocess.run(command, cwd=WEB_DIR, env=env).returncode


def _backend_command(python: str, host: str, port: str, reload: bool) -> list[str]:
    command = [
        python,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        command.append("--reload")
    return command


def _webapp_command(host: str, port: str) -> list[str]:
    npm = _npm_executable()
    if npm is None:
        return []
    command = [
        npm,
        "run",
        "dev",
        "--",
        "--port",
        str(port),
    ]
    if host != "127.0.0.1":
        command.extend(["--host", host])
    return command


def _web_command(host: str, port: str) -> list[str]:
    npm = _npm_executable()
    if npm is None:
        return []
    command = [
        npm,
        "run",
        "dev",
        "--",
        "--port",
        str(port),
    ]
    if host != "127.0.0.1":
        command.extend(["--host", host])
    return command


def _start_process(name: str, command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen:
    print(f"Starting {name}: {' '.join(command)}")
    print(f"{name} working directory: {cwd}")
    return subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True)


def _healthcheck_host(host: str) -> str:
    if host in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return host


def _wait_for_backend_ready(host: str, port: str, process: subprocess.Popen, timeout_seconds: float = 20) -> bool:
    url = f"http://{_healthcheck_host(host)}:{port}/health"
    print(f"Waiting for backend health: {url}")
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        code = process.poll()
        if code is not None:
            print(f"backend exited before becoming healthy with status {code}", file=sys.stderr)
            return False

        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except (OSError, URLError):
            pass

        time.sleep(0.25)

    print(f"Backend did not become healthy within {timeout_seconds:.0f} seconds.", file=sys.stderr)
    return False


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (AttributeError, ProcessLookupError):
        process.terminate()


def _stop_processes(processes: list[tuple[str, subprocess.Popen]]) -> None:
    for _, process in processes:
        _terminate_process(process)
    for name, process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"Force stopping {name}")
            process.kill()


def _wait_for_processes(processes: list[tuple[str, subprocess.Popen]]) -> int:
    try:
        while True:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    print(f"{name} exited with status {code}")
                    _stop_processes([(other_name, other) for other_name, other in processes if other is not process])
                    return code
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Stopping services...")
        _stop_processes(processes)
        return 130


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the reusable-container backend, merchant web app, and government web dashboard."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--backend-only", action="store_true", help="Start only the backend API.")
    mode.add_argument("--webapp-only", action="store_true", help="Start only the merchant web app.")
    mode.add_argument("--web-only", action="store_true", help="Start only the government web dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Backend host to bind. Default: 127.0.0.1")
    parser.add_argument("--port", default="8000", help="Backend port to bind. Default: 8000")
    parser.add_argument("--webapp-host", default="127.0.0.1", help="Web app host to bind. Default: 127.0.0.1")
    parser.add_argument("--webapp-port", default="5173", help="Web app port to bind. Default: 5173")
    parser.add_argument("--web-host", default="127.0.0.1", help="Government web host to bind. Default: 127.0.0.1")
    parser.add_argument("--web-port", default="5174", help="Government web port to bind. Default: 5174")
    parser.add_argument("--no-reload", action="store_true", help="Disable uvicorn auto reload.")
    parser.add_argument("--seed", action="store_true", help="Seed demo stores and users before starting.")
    parser.add_argument("--no-seed", action="store_true", help="Skip seeding demo stores and users before starting.")
    parser.add_argument(
        "--skip-webapp-install",
        action="store_true",
        help="Do not run npm install/npm ci when webapp/node_modules is missing.",
    )
    parser.add_argument(
        "--skip-web-install",
        action="store_true",
        help="Do not run npm install/npm ci when web/node_modules is missing.",
    )
    args = parser.parse_args()

    start_backend = not args.webapp_only and not args.web_only
    start_webapp = not args.backend_only and not args.web_only
    start_web = not args.backend_only and not args.webapp_only

    if start_backend and not _ensure_backend_exists():
        return 1
    if start_webapp and not _ensure_webapp_exists():
        return 1
    if start_web and not _ensure_web_exists():
        return 1

    python = _python_executable()
    env = os.environ.copy()

    should_seed = start_backend and not args.no_seed
    if should_seed:
        seed_result = subprocess.run([python, "-m", "app.seed"], cwd=BACKEND_DIR, env=env)
        if seed_result.returncode != 0:
            return seed_result.returncode

    if start_webapp or start_web:
        env["VITE_API_BASE_URL"] = f"http://{_healthcheck_host(args.host)}:{args.port}"

    if start_webapp:
        install_result = _install_webapp_dependencies(env, args.skip_webapp_install)
        if install_result != 0:
            return install_result
        if _npm_executable() is None:
            print("Cannot find npm. Install Node.js/npm before starting the web app.", file=sys.stderr)
            return 1
    if start_web:
        install_result = _install_web_dependencies(env, args.skip_web_install)
        if install_result != 0:
            return install_result
        if _npm_executable() is None:
            print("Cannot find npm. Install Node.js/npm before starting the government web.", file=sys.stderr)
            return 1

    processes: list[tuple[str, subprocess.Popen]] = []
    if start_backend:
        print(f"Backend URL: http://{args.host}:{args.port}")
        backend_process = _start_process(
            "backend",
            _backend_command(python, args.host, args.port, not args.no_reload),
            BACKEND_DIR,
            env,
        )
        processes.append(
            (
                "backend",
                backend_process,
            )
        )
        if not _wait_for_backend_ready(args.host, args.port, backend_process):
            _stop_processes(processes)
            return 1
    if start_webapp:
        print(f"Web app URL: http://{args.webapp_host}:{args.webapp_port}")
        print(f"Web app API base: {env['VITE_API_BASE_URL']}")
        processes.append(
            (
                "webapp",
                _start_process(
                    "webapp",
                    _webapp_command(args.webapp_host, args.webapp_port),
                    WEBAPP_DIR,
                    env,
                ),
            )
        )
    if start_web:
        print(f"Government web URL: http://{args.web_host}:{args.web_port}")
        print(f"Government web API base: {env['VITE_API_BASE_URL']}")
        processes.append(
            (
                "web",
                _start_process(
                    "web",
                    _web_command(args.web_host, args.web_port),
                    WEB_DIR,
                    env,
                ),
            )
        )

    return _wait_for_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
