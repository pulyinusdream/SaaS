"""One-command local setup and launch. Never changes global Python packages."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    environment = ROOT / '.venv'
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    setup_temp = ROOT / '.setup-tmp'
    setup_temp.mkdir(exist_ok=True)
    child_env = os.environ.copy()
    child_env.update(TEMP=str(setup_temp), TMP=str(setup_temp))
    if not python.exists():
        print('Creating an isolated Python environment...', flush=True)
        subprocess.run([sys.executable, '-m', 'venv', str(environment)], check=True, env=child_env)
    requirements = ROOT / 'requirements.txt'
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = environment / '.kjancy-requirements'
    if not marker.exists() or marker.read_text() != fingerprint:
        print('Installing the pinned app dependencies. Internet is needed for first setup.', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(requirements)], check=True, env=child_env)
        marker.write_text(fingerprint)
    return subprocess.call([str(python), str(ROOT / 'run.py'), *sys.argv[1:]], cwd=ROOT, env=child_env)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        print(f'Setup could not finish (exit {error.returncode}). Check your Python installation and internet connection.', file=sys.stderr)
        raise SystemExit(error.returncode)
    except KeyboardInterrupt:
        print('\nKJAncy stopped. Saved accounts and leads remain in the data folder.')
