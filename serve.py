"""Separate fail-closed hosting runner; run.py remains the local preview."""
import argparse
import os
import sys

from kjancy.deployment import production_settings


def main():
    parser = argparse.ArgumentParser(description='KJAncy hosting runner. Requires configured HTTPS proxy, private storage and SMTP.')
    parser.add_argument('--check', action='store_true', help='Validate configuration without opening a listener or changing data.')
    args = parser.parse_args()
    try:
        config, server = production_settings()
    except (ValueError, OSError) as error:
        print(f'Hosting configuration is incomplete: {error}', file=sys.stderr)
        return 2
    if args.check:
        print('Hosting configuration is valid. TLS, SMTP delivery and persistent-volume operation still require live verification.')
        return 0
    if os.name == 'posix':
        os.umask(0o077)
    from kjancy import create_app
    from kjancy.mailer import start_worker
    from waitress import serve
    app = create_app(config)
    start_worker(app)
    print('KJAncy hosting runner started behind the configured HTTPS proxy.', flush=True)
    serve(app, **server)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
