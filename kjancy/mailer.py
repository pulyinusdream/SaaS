"""Private durable mail queue; preview never contacts an email provider."""
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
import os
import secrets
import smtplib
import ssl
import threading
import time
from urllib.parse import urlsplit

from .validation import email as valid_email


def init_app(app):
    mode = app.config['MAIL_MODE']
    origin = urlsplit(app.config['PUBLIC_BASE_URL'])
    local = origin.hostname in {'127.0.0.1', 'localhost', '::1'}
    if (mode not in {'preview', 'smtp'} or origin.scheme not in {'http', 'https'} or not origin.hostname
            or origin.username or origin.password or origin.query or origin.fragment or origin.path not in {'', '/'}
            or (origin.scheme != 'https' and not local) or (mode == 'preview' and not local)):
        raise ValueError('Use a loopback URL for preview, or an HTTPS base URL and SMTP for hosting.')
    app.config['PUBLIC_BASE_URL'] = app.config['PUBLIC_BASE_URL'].rstrip('/')
    app.config['REQUIRE_EMAIL_VERIFICATION'] = mode == 'smtp' or app.config.get('REQUIRE_EMAIL_VERIFICATION', False)
    if mode == 'smtp':
        if (not all(app.config.get(key) for key in ('SMTP_HOST', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'MAIL_FROM'))
                or not valid_email(app.config['MAIL_FROM']) or app.config['SMTP_SECURITY'] not in {'starttls', 'ssl'}):
            raise ValueError('SMTP requires a host, username, password, sender and STARTTLS or SSL.')
        if not 1 <= int(app.config['SMTP_PORT']) <= 65535:
            raise ValueError('SMTP port must be between 1 and 65535.')
    outbox = Path(app.config['DATA_DIR']).resolve() / 'mail-outbox'
    if outbox.is_relative_to(Path(app.root_path).parent):
        raise ValueError('Email previews must be stored outside published application source.')
    outbox.mkdir(mode=0o700, exist_ok=True)
    app.config['MAIL_OUTBOX'] = str(outbox)


def queue_email(app, address, subject, body, purpose, expires):
    outbox = Path(app.config['MAIL_OUTBOX'])
    purge_expired(outbox)
    if len(list(outbox.glob('*.eml'))) >= 200:
        raise OSError('Local mail queue is full')
    message = EmailMessage()
    message['From'] = app.config.get('MAIL_FROM') or 'no-reply@kjancy.local'
    message['To'] = address
    message['Subject'] = subject
    message['X-KJAncy-Purpose'] = purpose
    message['X-KJAncy-Expires'] = str(expires)
    message.set_content(body)
    destination = outbox / (f'{time.time_ns()}-{secrets.token_hex(8)}.eml')
    temporary = destination.with_suffix('.tmp')
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as file:
            file.write(message.as_bytes())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def purge_expired(outbox):
    for file in [*outbox.glob('*.eml'), *outbox.glob('*.failed')]:
        try:
            message = BytesParser(policy=policy.default).parsebytes(file.read_bytes())
            if int(message.get('X-KJAncy-Expires', '0')) <= int(time.time()):
                file.unlink(missing_ok=True)
        except (ValueError, OSError):
            continue


def deliver_pending(app):
    """One runner thread owns delivery. Failed files remain for a later retry."""
    if app.config['MAIL_MODE'] != 'smtp':
        return
    outbox = Path(app.config['MAIL_OUTBOX'])
    purge_expired(outbox)
    # Oldest *attempt* first. Retained recipient failures move behind newer mail,
    # so a full failing batch cannot starve a healthy recipient indefinitely.
    candidates = []
    for file in outbox.glob('*.eml'):
        try:
            candidates.append((file.stat().st_mtime_ns, file))
        except FileNotFoundError:
            continue  # Concurrent expiry cleanup may already have removed it.
    for _, file in sorted(candidates)[:20]:
        try:
            message = BytesParser(policy=policy.default).parsebytes(file.read_bytes())
            context = ssl.create_default_context()
            if app.config['SMTP_SECURITY'] == 'ssl':
                connection = smtplib.SMTP_SSL(app.config['SMTP_HOST'], int(app.config['SMTP_PORT']), timeout=10, context=context)
            else:
                connection = smtplib.SMTP(app.config['SMTP_HOST'], int(app.config['SMTP_PORT']), timeout=10)
            with connection as smtp:
                if app.config['SMTP_SECURITY'] == 'starttls':
                    smtp.ehlo()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                smtp.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
                # Internal queue metadata is not part of the delivered email.
                del message['X-KJAncy-Purpose']
                del message['X-KJAncy-Expires']
                refused = smtp.send_message(message)
                if refused:
                    raise smtplib.SMTPRecipientsRefused(refused)
            file.unlink(missing_ok=True)
        except smtplib.SMTPRecipientsRefused as error:
            if all(details[0] >= 500 for details in error.recipients.values()):
                quarantine(file)
                app.logger.warning('Account email recipient permanently rejected; message quarantined.')
            else:
                retry_later(file)
                app.logger.warning('Account email recipient temporarily unavailable; message retained.')
            # Recipient failures must not block unrelated account messages.
            continue
        except smtplib.SMTPDataError as error:
            if error.smtp_code >= 500:
                quarantine(file)
                app.logger.warning('Account email message permanently rejected; message quarantined.')
                continue
            app.logger.warning('Account email message temporarily rejected; retained for retry.')
            retry_later(file)
            continue
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            app.logger.warning('Account email delivery failed; private queued message retained for retry.')
            break


def quarantine(file):
    try:
        file.replace(file.with_suffix('.failed'))
    except FileNotFoundError:
        pass


def retry_later(file):
    try:
        os.utime(file, None)  # Do not recreate a file removed by expiry cleanup.
    except FileNotFoundError:
        pass


def start_worker(app):
    if app.config['MAIL_MODE'] != 'smtp':
        return
    def work():
        while True:
            try:
                deliver_pending(app)
            except OSError:
                app.logger.warning('Account mail queue temporarily unavailable; delivery will retry.')
            time.sleep(30)
    threading.Thread(target=work, name='kjancy-account-mail', daemon=True).start()
