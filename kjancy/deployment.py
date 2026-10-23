"""Validate hosting settings without touching data or opening a listener."""
import ipaddress
import os
from pathlib import Path
from urllib.parse import urlsplit

from .validation import email as valid_email


def production_settings(environ=None):
    env = os.environ if environ is None else environ
    app_root = Path(__file__).resolve().parents[1]
    origin = env.get('KJANCY_PUBLIC_BASE_URL', '').strip()
    parsed = urlsplit(origin)
    try:
        parsed.port
    except ValueError as error:
        raise ValueError('KJANCY_PUBLIC_BASE_URL has an invalid port.') from error
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {'', '/'} or parsed.query or parsed.fragment
            or any(ord(ch) < 33 for ch in origin) or '*' in parsed.hostname
            or any(not label for label in parsed.hostname.split('.'))):
        raise ValueError('KJANCY_PUBLIC_BASE_URL must be a single HTTPS origin without credentials, paths or wildcards.')
    raw_data = env.get('KJANCY_DATA_DIR', '')
    data = Path(raw_data).expanduser()
    if not raw_data or not data.is_absolute() or data.resolve().is_relative_to(app_root) or data == Path(data.anchor):
        raise ValueError('KJANCY_DATA_DIR must be an absolute private data directory outside source.')
    if env.get('KJANCY_MAIL_MODE') != 'smtp':
        raise ValueError('Hosting requires SMTP mode. Local email preview cannot be deployed.')
    required = ('KJANCY_SMTP_HOST', 'KJANCY_SMTP_USERNAME', 'KJANCY_SMTP_PASSWORD', 'KJANCY_MAIL_FROM')
    if not all(env.get(name, '').strip() for name in required) or not valid_email(env['KJANCY_MAIL_FROM']):
        raise ValueError('Configure the SMTP host, username, password and verified sender before hosting.')
    security = env.get('KJANCY_SMTP_SECURITY', 'starttls')
    if security not in {'ssl', 'starttls'}:
        raise ValueError('SMTP security must be ssl or starttls.')
    try:
        proxy = ipaddress.ip_address(env.get('KJANCY_TRUSTED_PROXY', ''))
        bind = ipaddress.ip_address(env.get('KJANCY_BIND', '127.0.0.1'))
        port = int(env.get('PORT', '8080'))
        smtp_port = int(env.get('KJANCY_SMTP_PORT', '587'))
        if proxy.is_unspecified or proxy.is_multicast or not 1 <= port <= 65535 or not 1 <= smtp_port <= 65535:
            raise ValueError()
    except ValueError as error:
        raise ValueError('Set one exact trusted proxy IP, a valid bind IP and ports between 1 and 65535.') from error
    secret = env.get('KJANCY_SECRET_KEY')
    if secret is not None and (len(secret) < 48 or len(set(secret)) < 16):
        raise ValueError('Use a generated strong signing secret, or omit it to use the private persistent key file.')
    key_file = data / 'session.key'
    if secret is None and key_file.exists() and len(key_file.read_bytes()) < 48:
        raise ValueError('The persistent signing key is too short. Review it before hosting.')
    config = {
        'DATA_DIR': str(data.resolve()), 'PUBLIC_BASE_URL': origin.rstrip('/'), 'SECRET_KEY': secret,
        'TRUSTED_HOSTS': [parsed.hostname], 'SESSION_COOKIE_SECURE': True, 'ALLOW_OPAQUE_ORIGIN': False,
        'ENFORCE_HTTPS': True, 'DEBUG': False, 'MAIL_MODE': 'smtp', 'REQUIRE_EMAIL_VERIFICATION': True,
        'MAIL_FROM': env['KJANCY_MAIL_FROM'], 'SMTP_HOST': env['KJANCY_SMTP_HOST'],
        'SMTP_USERNAME': env['KJANCY_SMTP_USERNAME'], 'SMTP_PASSWORD': env['KJANCY_SMTP_PASSWORD'],
        'SMTP_PORT': smtp_port, 'SMTP_SECURITY': security,
    }
    server = {
        'host': str(bind), 'port': port, 'threads': 4, 'max_request_body_size': 32768,
        'trusted_proxy': str(proxy), 'trusted_proxy_count': 1,
        'trusted_proxy_headers': {'x-forwarded-for', 'x-forwarded-proto'}, 'clear_untrusted_proxy_headers': True,
    }
    return config, server
