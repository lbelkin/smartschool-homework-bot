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
            print('Вставьте новый webToken в webtop-token.txt, заменив весь текст, и сохраните файл.')
            raise ValueError('Token file not filled')
        if any(character.isspace() for character in token):
            raise ValueError('Token must be on one line')
        print('Токен прочитан из локального файла. После успешного сохранения в GCP файл будет удалён.')
    else:
        print('В обычном Chrome войдите в Webtop самостоятельно.')
        print('DevTools → Application → Cookies → smartschool.co.il → webToken.')
        print('Нажмите ⌘V, затем Enter. При вставке символы и звёздочки не отображаются.')
        token = getpass.getpass('webToken (не пароль): ')
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
    print(f'API проверен за четыре недели. Найдено заданий: {len(tasks)}. Сессия сохранена в Secret Manager.')
    print('Срок действия сессии и доступ из GCP ещё нужно проверить.')


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt):
        print('Подключение не завершено. API или проверка структуры данных не прошли; токен не выведен.')
        raise SystemExit(1)
