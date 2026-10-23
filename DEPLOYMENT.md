# Deployment and backup runbook

This milestone prepares the existing app for hosting. **Nothing has been published or purchased.** The local launcher and mint website remain usable at their current address. A domain and SMTP were explicitly deferred. The hosting runner deliberately refuses development email preview; use the local runner until the missing settings are available.

## Use the local app

Run `Start-KJAncy.cmd` as before. It uses loopback only and clearly labelled local email previews. The new `serve.py` is a separate hosting entry point; it does not replace the local launcher.

## Create a private backup now

Double-click `Backup-KJAncy.cmd` after the app has been set up once. Or run from the app folder:

```powershell
.venv\Scripts\python.exe backup.py create
```

The tool can back up while the app runs. It uses SQLite's online backup API, so committed WAL data is included. Each generated ZIP is checked for manifest/checksum, schema, SQLite integrity and foreign-key consistency before success is printed. Default backups are saved privately in `C:\Users\vicen\Documents\Codex\kjancy-backups`, beside the current data folder. `KJANCY_DATA_DIR` changes the data folder and its default sibling backup location.

The ZIP contains confidential customer records, account emails and password hashes. It is not encrypted. Keep it private, restrict filesystem access, and place an additional encrypted copy in storage you control. A checksum detects corruption; it does not prove a backup came from a trusted person. Signing keys, SMTP environment credentials, private email previews and mail queues are excluded. Do not put backup ZIPs in website assets, source control or a public download.

Custom private backup folder and explicit verification:

```powershell
.venv\Scripts\python.exe backup.py create --output-dir "C:\Users\vicen\Documents\Codex\private-kjancy-backups"
.venv\Scripts\python.exe backup.py verify "FULL_PATH_TO_A_PRIVATE_BACKUP.zip"
```

Current tool limit: databases up to 512 MiB. It keeps every backup; no automatic deletion, retention schedule or off-device upload is configured. A busy database aborts the snapshot after about 60 seconds rather than blocking indefinitely.

## Rehearse or perform recovery

Only restore a backup you trust. Choose a destination that does not exist and is outside the application source:

```powershell
.venv\Scripts\python.exe backup.py restore "FULL_PATH_TO_A_PRIVATE_BACKUP.zip" --destination "C:\Users\vicen\Documents\Codex\kjancy-recovered"
```

Restore never overwrites an existing directory, including an empty one. The archive is checked before creating the destination. Recovery preserves business accounts, password hashes, memberships, lead records, statuses and activity. It clears sessions and verification/reset tokens, revokes outstanding team invitations, and writes a fresh signing key. This prevents an older snapshot from reviving previously used links or sessions. Existing customer inquiry URLs remain attached to their workspaces. Users must sign in again, request fresh account links if needed, and owners must recreate outstanding invitations. Preview email files are not restored.

The command only creates a recovered directory; it does not switch the live app. For an intentional recovery, first stop the server, set `KJANCY_DATA_DIR` to that new directory, then restart and check login/inbox records. If the deployment uses `KJANCY_SECRET_KEY` from a secret store, rotate that secret separately as well; the environment value overrides the new file. Keep the original data directory until you have verified the recovery. An interrupted restore can leave a partial new directory; choose another new path for a retry rather than overwriting or deleting existing data automatically.

## Hosting configuration

The hosting entry point is `serve.py`. It expects a single TLS-terminating reverse proxy, a durable private data directory and real SMTP. Run `python serve.py --check` after setting environment variables; it validates settings without opening a listener, starting email delivery or initializing a database. A valid configuration is not proof of live HTTPS, durable storage or email deliverability.

| Variable | Requirement |
| --- | --- |
| `KJANCY_PUBLIC_BASE_URL` | Exact HTTPS origin, without path/query/user credentials; a provider-issued hostname can be used later |
| `KJANCY_DATA_DIR` | Absolute private directory outside app source, on persistent storage |
| `KJANCY_TRUSTED_PROXY` | Exact IP of the one reverse proxy as seen by the app; no wildcard |
| `KJANCY_BIND` | Listener IP, default `127.0.0.1`; container sets `0.0.0.0` internally |
| `PORT` | Internal listener port, default `8080` |
| `KJANCY_MAIL_MODE` | Must be `smtp`; preview mode is rejected |
| SMTP settings | Verified sender, host, username, private key, valid port and `ssl` or `starttls`; see `SMTP-SETUP.md` |
| `KJANCY_SECRET_KEY` | Optional strong generated secret; if omitted a random private key file persists in the data directory |

The profile forces secure cookies, strict host checking, HTTPS for application routes, email verification, disabled debug and disabled opaque-origin compatibility. Only `/health` can be checked internally over HTTP. Direct insecure form submissions are rejected before account details are processed. The proxy must preserve the original Host and supply correct `X-Forwarded-Proto` and `X-Forwarded-For`. Waitress trusts those two headers from the exact configured peer, for one proxy hop; other forwarded headers are discarded. If your provider has a different proxy layout or dynamic peer ranges, adapt and review this profile before deployment rather than using wildcard trust. TLS terminates outside Waitress; this package does not issue a certificate or configure a public proxy.

Run one app process/replica with this SQLite database and local mail queue. Do not use an ephemeral filesystem, an unvalidated network filesystem, or multiple workers sharing the SQLite/mail directory. Review database scaling/migrations, persistent-disk behavior, firewalling and provider proxy requirements before a public pilot. Health only proves the database can answer a minimal query; it does not test SMTP or backups.

On native Linux, the hosting runner sets a restrictive `077` umask before creating application data. Existing directory/file permissions are not changed: ensure only the service account can access an existing data directory. On Windows, restrict access through the folder's Security settings. The configuration check makes no filesystem changes.

## Container blueprint

`Dockerfile` uses the official Python 3.13 slim image, pinned Python package versions, an unprivileged UID/GID 10001, and an internal HTTP health check. `compose.yaml` mounts a named `/data` volume, keeps application files read-only, drops Linux capabilities, supplies temporary scratch space and publishes its port only on host loopback. It expects a separately configured HTTPS proxy. Its `127.0.0.1:4201` default mapping is not a public site. The actual proxy peer address seen inside a Docker network can differ from the host loopback address: use the observed, verified peer IP in the private environment file.

After a hosting account, verified sender and proxy are ready, copy the non-secret template to a private `deployment.env`, replace every placeholder, and run:

```powershell
docker compose --env-file deployment.env config --quiet
docker compose --env-file deployment.env build
docker compose --env-file deployment.env up -d
```

Do not launch it with example SMTP credentials. Keep `deployment.env` private; it is ignored by Git and the Docker build context. Container administrators can inspect environment secrets, so treat Docker/server administrator access as privileged. The signing key defaults to the persistent volume, not the source image. Back up the database from the volume to a separate private storage location; a container volume is not a backup. Do not remove the named volume when updating the app.

Docker Desktop's engine was stopped in this environment during preparation. Configuration parsing is checked separately; an image build and container runtime are not claimed. Once Docker and hosting are available, test the build, mounted-volume ownership/restart persistence, HTTPS proxy trust, real SMTP and restore procedures before admitting clients. The base image tag receives upstream updates; pin a tested image digest in the release pipeline after building/scanning it.

References: [SQLite backup API](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup), [Waitress proxy arguments](https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html), [Flask proxy deployment guidance](https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/).
