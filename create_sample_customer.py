"""Provision a local customer sample explicitly; never run at application startup."""
import argparse
from pathlib import Path

from kjancy import create_app
from kjancy.sample_customer import provision_sample_customer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-email',required=True,help='Existing staff owner who will manage the isolated sample workspace.')
    parser.add_argument('--credentials',required=True,help='New private JSON file outside the application source.')
    args = parser.parse_args()
    app = create_app()
    try: result = provision_sample_customer(app,args.owner_email,Path(args.credentials))
    except (ValueError,OSError) as error: parser.exit(2,str(error)+'\n')
    print('Local sample customer created. Private credentials: '+result['credentials_path'])


if __name__=='__main__': main()
