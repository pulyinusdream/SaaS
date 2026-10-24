
import os

from kjancy import create_app
from werkzeug.middleware.proxy_fix import ProxyFix


# -----------------------------------------
# Trusted hosts
# -----------------------------------------

trusted_hosts = [
    "localhost",
    "127.0.0.1",
    "[::1]",
    "kjancy-gilt.vercel.app",
    "kjancy.vercel.app",
]

# Include Vercel-generated deployment domains.
for name in (
    "VERCEL_URL",
    "VERCEL_BRANCH_URL",
    "VERCEL_PROJECT_PRODUCTION_URL",
):
    host = os.environ.get(name, "")

    if host:
        host = (
            host.removeprefix("https://")
                .removeprefix("http://")
                .split("/")[0]
        )
        trusted_hosts.append(host)


# -----------------------------------------
# Create Flask application
# -----------------------------------------

app = create_app({
    "DATA_DIR": "/tmp/kjancy-data",
    "TRUSTED_HOSTS": list(
        dict.fromkeys(trusted_hosts)
    ),
    "SESSION_COOKIE_SECURE": True,
    "PUBLIC_BASE_URL":
        "https://kjancy-gilt.vercel.app",
})


# -----------------------------------------
# Fix HTTPS behind Vercel
# -----------------------------------------

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_proto=1,
)
