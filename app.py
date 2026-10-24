
import os
from kjancy import create_app

app = create_app()

# Allow local development and the production domain
trusted_hosts = [
    "127.0.0.1",
    "localhost",
    "[::1]",
    "kjancy.vercel.app",
]

# Allow this project's Vercel deployment URLs
for variable in (
    "VERCEL_URL",
    "VERCEL_BRANCH_URL",
    "VERCEL_PROJECT_PRODUCTION_URL",
):
    host = os.environ.get(variable)
    if host:
        trusted_hosts.append(host)

app.config["TRUSTED_HOSTS"] = list(
    dict.fromkeys(trusted_hosts)
)
