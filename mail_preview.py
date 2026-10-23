"""Local-only email preview helper; no network and no web endpoint."""
import argparse
from email import policy
from email.parser import BytesParser
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Read private local KJAncy email previews. Never share these files or links.')
    parser.add_argument('--read', metavar='FILENAME', help='Read one listed .eml file; prints its private account link.')
    args = parser.parse_args()
    if os.environ.get('KJANCY_MAIL_MODE', 'preview') != 'preview':
        parser.error('This helper is for local preview mode. SMTP messages are delivered by the app worker.')
    outbox = Path(os.environ.get('KJANCY_DATA_DIR', str(Path.home() / 'Documents/Codex/kjancy-data'))) / 'mail-outbox'
    outbox = outbox.resolve()
    if args.read:
        file = (outbox / args.read).resolve()
        if file.parent != outbox or file.suffix != '.eml' or not file.is_file():
            parser.error('Choose one .eml filename from this local outbox.')
        message = BytesParser(policy=policy.default).parsebytes(file.read_bytes())
        print(f'LOCAL PREVIEW - no email has been sent\nTo: {message["To"]}\nSubject: {message["Subject"]}\n\n{message.get_content()}')
    else:
        files = sorted(outbox.glob('*.eml'), reverse=True)[:20] if outbox.exists() else []
        print('LOCAL EMAIL PREVIEW - messages contain private account links.\nNo SMTP delivery is configured in preview mode.\n')
        if not files:
            print('No previews yet. Request a verification or password reset in the app first.')
        for file in files:
            message = BytesParser(policy=policy.default).parsebytes(file.read_bytes())
            print(f'{file.name}\n  {message["Subject"]} | To: {message["To"]}\n')
        if files:
            choice = input('Enter a listed filename to read it, or press Enter to close: ').strip()
            if choice:
                file = (outbox / choice).resolve()
                if file.parent != outbox or file.suffix != '.eml' or not file.is_file():
                    parser.error('Choose one listed .eml filename.')
                message = BytesParser(policy=policy.default).parsebytes(file.read_bytes())
                print(message.get_content())
                input('\nCopy the private link into your browser. Press Enter to close: ')


if __name__ == '__main__':
    main()
