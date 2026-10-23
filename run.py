import argparse

from waitress import serve

from kjancy import create_app
from kjancy.mailer import start_worker
import os

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start the KJAncy local workspace.')
    parser.add_argument('--port', type=int, default=4200)
    args = parser.parse_args()
    # The desktop app's browser submits an opaque Origin. The exception is only
    # enabled here, on a loopback-only listener, and still requires signed CSRF.
    app = create_app({'ALLOW_OPAQUE_ORIGIN': True, 'PUBLIC_BASE_URL': os.environ.get('KJANCY_PUBLIC_BASE_URL', f'http://127.0.0.1:{args.port}')})
    start_worker(app)
    print(f'KJAncy workspace: http://127.0.0.1:{args.port}', flush=True)
    print(f'Data folder: {app.config["DATA_DIR"]}', flush=True)
    serve(app, host='127.0.0.1', port=args.port, threads=4, max_request_body_size=32768, clear_untrusted_proxy_headers=True)
