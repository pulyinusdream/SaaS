
import os

from kjancy import create_app
from werkzeug.middleware.proxy_fix import ProxyFix


# ------------------------------------------
# KJAncy - Vercel Configuration
# ------------------------------------------

PRODUCTION_DOMAIN = "kjancy-gilt.vercel.app"

PUBLIC_BASE_URL = os.environ.get(
    "KJANCY_PUBLIC_BASE_URL",
    f"https://{PRODUCTION_DOMAIN}"
)


# ------------------------------------------
# Trusted Hosts
# ------------------------------------------

trusted_hosts = [
    "localhost",
    "127.0.0.1",
    "[::1]",
    "kjancy.vercel.app",
    "kjancy-gilt.vercel.app",
]

# Include deployment-specific Vercel domains.
for variable in (
    "VERCEL_URL",
    "VERCEL_BRANCH_URL",
    "VERCEL_PROJECT_PRODUCTION_URL",
):
    hostname = os.environ.get(variable)

    if hostname:
        hostname = (
            hostname
            .replace("https://", "")
            .replace("http://", "")
            .split("/")[0]
        )
        trusted_hosts.append(hostname)

trusted_hosts = list(dict.fromkeys(trusted_hosts))


# ------------------------------------------
# Flask Application
# ------------------------------------------

app = create_app({
    # Temporary SQLite storage for testing.
    # Not suitable for production customer data.
    "DATA_DIR": "/tmp/kjancy-data",

    # Validate legitimate website hostnames.
    "TRUSTED_HOSTS": trusted_hosts,

    # Production website address.
    "PUBLIC_BASE_URL": PUBLIC_BASE_URL,

    # HTTPS-only session cookies.
    "SESSION_COOKIE_SECURE": True,
    "SESSION_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SAMESITE": "Lax",

    # Require HTTPS for application requests.
    "ENFORCE_HTTPS": True,

    # Keep Origin and CSRF security enabled.
    "ALLOW_OPAQUE_ORIGIN": False,
})


# ------------------------------------------
# Vercel Reverse Proxy Fix
# ------------------------------------------

# Vercel terminates HTTPS before forwarding
# requests to the Python application.
#
# Trust one forwarded protocol header so Flask
# correctly recognizes HTTPS requests.
#
# Do not trust forwarded host or client IP
# headers unnecessarily.

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=0,
    x_proto=1,
    x_host=0,
    x_port=0,
    x_prefix=0,
)


# ------------------------------------------
# Vercel Flask Entry Point
# ------------------------------------------

# Vercel automatically discovers the Flask
# application through the "app" variable.
