# Account email setup

The app currently uses **local preview mode** because no SMTP service is configured. It creates real, expiring verification/reset links but does not send email. No public hosting or DNS setup is claimed.

## Try the local flow

1. Start the app with `Start-KJAncy.cmd`.
2. In the workspace, open **Email verification**, then **Create verification preview**. For recovery, choose **Forgot your password?** on the sign-in page and submit your account email.
3. Double-click `Read-EmailPreview.cmd` in the app folder. It lists the latest local messages. Enter a listed filename to read the message, copy its link into the browser, and complete the confirmation yourself. The browser should use the same running local app/port.
4. Verification requires an explicit confirmation. Password recovery requires choosing and saving a new password; it signs all previous sessions out and then asks you to sign in. Never share preview files or account links.

Private messages are stored in `C:\Users\vicen\Documents\Codex\kjancy-data\mail-outbox`, outside the published application. The directory follows `KJANCY_DATA_DIR` if overridden. No web route lists or serves these messages. Expired files are removed when the queue is next used; SMTP mode also checks expiry while delivering. Protect this folder with your Windows account permissions. Preview mode is a developer/operator convenience, not proof of ownership of a real mailbox: a local operator who can read the outbox can open its links. SMTP mode requires actual verification before workspace access.

## Connect SMTP later

Choose an email provider, verify its sender/domain, then configure these environment variables on the server. Do not put SMTP passwords in HTML, source files, this chat, or a source ZIP. The app does not automatically load `.env` files.

| Variable | Value |
| --- | --- |
| `KJANCY_MAIL_MODE` | `smtp` |
| `KJANCY_MAIL_FROM` | Your provider-verified sender email |
| `KJANCY_SMTP_HOST` | Provider's SMTP hostname |
| `KJANCY_SMTP_PORT` | Provider's TLS port, usually 587 with STARTTLS or 465 with SSL |
| `KJANCY_SMTP_SECURITY` | `starttls` or `ssl`; plaintext is rejected |
| `KJANCY_SMTP_USERNAME` | Provider's SMTP username |
| `KJANCY_SMTP_PASSWORD` | Provider's SMTP credential, set privately |
| `KJANCY_PUBLIC_BASE_URL` | Canonical app origin; use HTTPS for any non-loopback host |

Restart with `Start-KJAncy.cmd`. In SMTP mode the runner starts one background delivery worker. The request path queues messages durably and returns without contacting a provider, so account lookup does not wait for SMTP. Invalid configuration fails startup. Public origins cannot use preview mode. No mail-provider credential is configured in this delivery and no real SMTP or mailbox test was performed.

Successful messages are removed from the queue after provider acceptance; acceptance does not guarantee inbox placement. Temporary recipient failures rotate behind newer messages for retry. Permanent recipient/message rejections are quarantined as private `.failed` files, which expire like queued messages. Authentication, TLS or provider failures retain pending mail and log a generic operator warning without credentials, recipients or private links. Retries run about every 30 seconds in batches of at most 20. The queue is capped near 200 pending messages; review provider settings and monitor delivery before opening a public pilot. Run only one app process against this local queue. At-least-once delivery can send the same message again if a process stops after provider acceptance but before removing the file; the account link itself remains single-use.

The current runner still binds only to loopback. Public hosting additionally needs HTTPS, secure-cookie/trusted-host configuration, backups, monitoring and deployment review. Do not treat adding SMTP settings as public deployment.

## Safeguards and scope

- Verification links expire after 24 hours. Resending supersedes previous links.
- Reset links expire after 30 minutes. A short resend cooldown prevents duplicate reset mail; repeated attempts are rate limited. Existing and unknown addresses receive the same receipt, with a 250 ms minimum processing window and no provider call in the request path.
- Link GETs do not consume tokens. Confirmation/reset writes require CSRF. Password validation errors leave the token usable. Tokens are bound to purpose, email and the current credential version, and the database stores their digests.
- A password reset changes the scrypt hash, revokes all sessions and invalidates outstanding account tokens in one transaction. Conditional session insertion also rejects a stale password check racing a reset. The reset does not sign the browser in or silently mark an unverified email as verified.
- Old accounts are preserved and remain unverified until confirmed. Local preview explicitly allows workspace access; SMTP mode enforces verification on private workspace and invitation acceptance routes.

References: [OWASP forgot-password guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html), [Python SMTP and TLS APIs](https://docs.python.org/3/library/smtplib.html).
