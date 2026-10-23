"""Private online backups and non-destructive recovery into a new directory."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import tempfile
import time
import zipfile

MAX_DATABASE_BYTES = 512 * 1024 * 1024
APP_ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    'users': {'id', 'email', 'password_hash'}, 'workspaces': {'id', 'public_id'},
    'memberships': {'workspace_id', 'user_id', 'role'}, 'leads': {'id', 'workspace_id', 'customer_name'},
    'lead_events': {'lead_id', 'workspace_id'}, 'sessions': {'digest', 'user_id'},
    'account_tokens': {'digest', 'user_id', 'used'}, 'invitations': {'id', 'used'},
    'rate_limits': {'bucket', 'expires'},
}


def private_path(path):
    path = Path(path).expanduser().resolve()
    if path == Path(path.anchor) or path.is_relative_to(APP_ROOT):
        raise ValueError('Use a private directory outside the application source and published assets.')
    return path


def readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=10)


def validate_database(path):
    try:
        with closing(readonly(path)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('SQLite integrity check failed.')
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('The backup contains inconsistent references.')
            for table, columns in REQUIRED.items():
                actual = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
                if not columns <= actual:
                    raise ValueError('The backup is missing required application tables or columns.')
    except sqlite3.DatabaseError as error:
        raise ValueError('The snapshot is not a valid KJAncy database.') from error


def checksum(path):
    with Path(path).open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


@contextmanager
def unpack_verified(archive):
    archive = private_path(archive)
    try:
        with zipfile.ZipFile(archive) as bundle:
            entries = bundle.infolist()
            if len(entries) != 2 or {item.filename for item in entries} != {'manifest.json', 'kjancy.sqlite3'}:
                raise ValueError('Unexpected backup members. No files were restored.')
            if any(item.flag_bits & 1 for item in entries):
                raise ValueError('Encrypted ZIPs are not supported by this backup format.')
            info = bundle.getinfo('kjancy.sqlite3')
            if not 4096 <= info.file_size <= MAX_DATABASE_BYTES or bundle.getinfo('manifest.json').file_size > 16384:
                raise ValueError('The backup exceeds the supported size limits.')
            manifest = json.loads(bundle.read('manifest.json'))
            if (not isinstance(manifest, dict) or type(manifest.get('format')) is not int or manifest['format'] != 1
                    or manifest.get('database_bytes') != info.file_size or not isinstance(manifest.get('sha256'), str)):
                raise ValueError('The backup manifest is invalid or unsupported.')
            with tempfile.TemporaryDirectory(prefix='.verify-', dir=archive.parent) as directory:
                snapshot = Path(directory) / 'kjancy.sqlite3'
                with bundle.open('kjancy.sqlite3') as source, snapshot.open('xb') as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                if checksum(snapshot) != manifest['sha256']:
                    raise ValueError('Backup checksum does not match. Nothing was restored.')
                validate_database(snapshot)
                yield snapshot, manifest
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError, UnicodeError, NotImplementedError) as error:
        raise ValueError('The backup archive is invalid or damaged.') from error


def create_backup(data_dir, output_dir):
    data_dir, output_dir = private_path(data_dir), private_path(output_dir)
    source = data_dir / 'kjancy.sqlite3'
    if not source.is_file():
        raise ValueError('No existing KJAncy database was found. Start the app first.')
    output_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    created = datetime.now(timezone.utc)
    archive = output_dir / (created.strftime('kjancy-%Y%m%dT%H%M%SZ-') + secrets.token_hex(6) + '.zip')
    owned = False
    try:
        with tempfile.TemporaryDirectory(prefix='.snapshot-', dir=output_dir) as directory:
            snapshot = Path(directory) / 'kjancy.sqlite3'
            deadline = time.monotonic() + 60
            def progress(_status, _remaining, _total):
                if time.monotonic() > deadline:
                    raise TimeoutError('Database remained busy. Retry the backup later.')
            with closing(readonly(source)) as live, closing(sqlite3.connect(snapshot)) as target:
                live.backup(target, pages=128, progress=progress, sleep=0.05)
            validate_database(snapshot)
            size = snapshot.stat().st_size
            if size > MAX_DATABASE_BYTES:
                raise ValueError('This local backup tool supports databases up to 512 MiB.')
            manifest = {'format': 1, 'created_utc': created.isoformat(), 'database_bytes': size, 'sha256': checksum(snapshot)}
            with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as bundle:
                owned = True
                os.chmod(archive, 0o600)
                bundle.write(snapshot, 'kjancy.sqlite3')
                bundle.writestr('manifest.json', json.dumps(manifest, indent=2))
        verify_backup(archive)
        return archive
    except Exception:
        if owned:
            archive.unlink(missing_ok=True)
        raise


def verify_backup(archive):
    with unpack_verified(archive) as (_snapshot, manifest):
        return manifest


def restore_backup(archive, destination):
    destination = private_path(destination)
    if destination.exists():
        raise ValueError('Restore requires a new directory. Existing data is never overwritten.')
    with unpack_verified(archive) as (snapshot, _manifest):
        with closing(sqlite3.connect(snapshot)) as db, db:
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('DELETE FROM sessions')
            db.execute('DELETE FROM account_tokens')
            db.execute('UPDATE invitations SET used=1')
        validate_database(snapshot)
        # The exclusive directory claim occurs only after full verification.
        # No replace/delete operation is ever issued against an existing target.
        destination.mkdir(parents=True, mode=0o700, exist_ok=False)
        with snapshot.open('rb') as source, (destination / 'kjancy.sqlite3').open('xb') as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
        os.chmod(destination / 'kjancy.sqlite3', 0o600)
        descriptor = os.open(destination / 'session.key', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as file:
            file.write(secrets.token_bytes(48))
    return destination
