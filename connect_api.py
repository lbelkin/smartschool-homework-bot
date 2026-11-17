import getpass
import os
import subprocess
from pathlib import Path

from webtop_api import Client


def main():
    project = os.environ.get('GOOGLE_CLOUD_PROJECT')
    if not project:
        raise RuntimeError('Set GOOGLE_CLOUD_PROJECT before connecting Webtop')
    token_file = Path(__file__).resolve().with_name('webtop-token.txt')
    if token_file.exists():
        token_file.chmod(0o600)
        if token_file.stat().st_size > 20000:
            raise ValueError('Token file too large')
        token = token_file.read_text(encoding='utf-8-sig').strip()
        if not token or token == 'PASTE_NEW_WEBTOP_TOKEN_HERE':
            print('Paste the new webToken into webtop-token.txt, replace all existing text, and save the file.')
            raise ValueError('Token file not filled')
        if any(character.isspace() for character in token):
            raise ValueError('Token must be on one line')
        print('The token was read from a local file. It will be deleted after it is saved successfully in GCP.')
    else:
        print('Sign in to Webtop yourself in a normal Chrome window.')
        print('DevTools → Application → Cookies → smartschool.co.il → webToken.')
        print('Press Command-V, then Enter. Pasted characters and asterisks are not displayed.')
        token = getpass.getpass('webToken (not your password): ')
    student = subprocess.run(['gcloud', 'secrets', 'versions', 'access', 'latest',
                              '--secret=WEBTOP_STUDENT', f'--project={project}'],
                             check=True, capture_output=True, text=True).stdout.strip()
    client = Client(token)
    try:
        tasks = client.homework(student, 4)
    finally:
        client.close()
    subprocess.run(['gcloud', 'secrets', 'versions', 'add', 'WEBTOP_WEB_TOKEN',
                    f'--project={project}', '--data-file=-', '--quiet'],
                   input=token, text=True, check=True, capture_output=True)
    if token_file.exists() and token_file.read_text(encoding='utf-8-sig').strip() == token:
        token_file.unlink()
    print(f'The API was validated over four weeks. Assignments found: {len(tasks)}. The session was saved in Secret Manager.')
    print('The session lifetime and access from GCP still need to be verified.')


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt):
        print('Connection did not complete. The API or data-structure check failed; the token was not printed.')
        raise SystemExit(1)
