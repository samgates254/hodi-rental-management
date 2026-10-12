"""Run authenticated browser flows against the real app with a disposable DB."""
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def available(port):
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def wait_http(url, process, label):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{label} stopped before becoming ready.")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {label}.")


def run(command, *, cwd, env):
    result = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode:
        if "playwright" in str(command[0]).lower() or "playwright" in " ".join(map(str, command)).lower():
            print(result.stdout, file=sys.stderr)
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(map(str, command))}")
    return result.stdout


def main():
    if os.environ.get("DJANGO_ENV", "development").strip().lower() == "production":
        raise SystemExit("Refusing to run local E2E seeding while DJANGO_ENV=production.")
    if not available(8765) or not available(8766):
        raise SystemExit("Ports 8765 and 8766 must be free for the isolated E2E app.")

    temp = Path(tempfile.mkdtemp(prefix="hodi-e2e-"))
    temp.chmod(0o700)
    media = temp / "media"
    media.mkdir(mode=0o700)
    password = secrets.token_urlsafe(24)
    env = os.environ.copy()
    env.update({
        "DJANGO_ENV": "development",
        "DB_NAME": str(temp / "db.sqlite3"),
        "DJANGO_MEDIA_ROOT": str(media),
        "DATABASE_URL": "",
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "HODI_E2E_PASSWORD": password,
        "HODI_E2E_CREDENTIAL_FILE": str(temp / "credentials.json"),
        "HODI_E2E_BASE_URL": "http://127.0.0.1:8766",
        "PLAYWRIGHT_OUTPUT_DIR": str(temp / "playwright-results"),
        "API_PROXY_TARGET": "http://127.0.0.1:8765",
        "NEXT_PUBLIC_API_BASE_URL": "",
    })
    env.pop("DB_PASSWORD", None)
    env.pop("DATABASE_PASSWORD", None)
    processes = []
    try:
        manage = [str(BACKEND / ".venv/bin/python"), "manage.py"]
        run([*manage, "migrate", "--noinput"], cwd=BACKEND, env=env)
        run([*manage, "check"], cwd=BACKEND, env=env)
        run([*manage, "makemigrations", "--check", "--dry-run"], cwd=BACKEND, env=env)
        seed = "import runpy; runpy.run_path('tests/e2e/seed_local.py')"
        run([*manage, "shell", "-c", seed], cwd=BACKEND, env=env)

        backend_log = open(temp / "django.log", "w", encoding="utf8")
        processes.append(subprocess.Popen([*manage, "runserver", "127.0.0.1:8765", "--noreload"], cwd=BACKEND, env=env, stdout=backend_log, stderr=subprocess.STDOUT))
        wait_http("http://127.0.0.1:8765/api/v1/health/", processes[-1], "Django")

        frontend_env = env.copy()
        frontend_log = open(temp / "next.log", "w", encoding="utf8")
        processes.append(subprocess.Popen(["npm", "run", "dev", "--", "--hostname", "127.0.0.1", "--port", "8766"], cwd=FRONTEND, env=frontend_env, stdout=frontend_log, stderr=subprocess.STDOUT))
        wait_http("http://127.0.0.1:8766/signin", processes[-1], "Next.js")

        browser_output = run(["npm", "exec", "playwright", "test", "--", "--config=playwright.config.ts"], cwd=FRONTEND, env=env)
        print(browser_output.strip())
        print("Authenticated browser workflows passed against isolated SQLite and real Django/Next.js servers.")
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"E2E runner failed: {error}", file=sys.stderr)
        sys.exit(1)
