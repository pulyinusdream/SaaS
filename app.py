
import os
from kjancy import create_app

app = create_app({
    "DATA_DIR": "/tmp/kjancy-data",
    "SESSION_COOKIE_SECURE": True,
})

trusted_hosts = [
    "localhost",
    "127.0.0.1",
    "[::1]",
    "kjancy.vercel.app",
    "kjancy-gilt.vercel.app",
]

for key in (
    "VERCEL_URL",
    "VERCEL_BRANCH_URL",
    "VERCEL_PROJECT_PRODUCTION_URL",
):
    if os.environ.get(key):
        trusted_hosts.append(os.environ[key])

app.config["TRUSTED_HOSTS"] = list(
    dict.fromkeys(trusted_hosts)
)
