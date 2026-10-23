import argparse
import os
from pathlib import Path
import sys

from kjancy.backup import create_backup, restore_backup, verify_backup


def main():
    parser = argparse.ArgumentParser(description='Private KJAncy backup tools. Backups contain account/customer data; never publish them.')
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('create', help='Create and verify an online SQLite snapshot.')
    create.add_argument('--data-dir', default=os.environ.get('KJANCY_DATA_DIR', str(Path.home() / 'Documents/Codex/kjancy-data')))
    create.add_argument('--output-dir', help='Private folder outside the app; defaults beside its data folder.')
    verify = sub.add_parser('verify', help='Check manifest, checksum, schema and database integrity.')
    verify.add_argument('archive')
    restore = sub.add_parser('restore', help='Recover into a NEW directory; never overwrite live data.')
    restore.add_argument('archive')
    restore.add_argument('--destination', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'create':
            data = Path(args.data_dir).expanduser().resolve()
            output = args.output_dir or data.parent / 'kjancy-backups'
            archive = create_backup(data, output)
            print(f'Private backup created and verified: {archive}')
            print('Contains confidential database records. No signing key, email previews or environment secrets are included.')
        elif args.command == 'verify':
            report = verify_backup(args.archive)
            print(f'Backup verified: format {report["format"]}; {report["database_bytes"]} database bytes.')
        else:
            destination = restore_backup(args.archive, args.destination)
            print(f'Restored into new private directory: {destination}')
            print('Sessions and account links were cleared; invitations revoked; signing key rotated. Point KJANCY_DATA_DIR here to use the recovery.')
        return 0
    except (ValueError, OSError, TimeoutError) as error:
        print(f'Backup operation stopped: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
