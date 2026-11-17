import argparse
import os
import re
import subprocess
from pathlib import Path


ACCOUNT = os.getenv('KEYCHAIN_ACCOUNT', 'school-homework-bot')
KEYS = ('WEBTOP_WEB_TOKEN', 'WEBTOP_STUDENT', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID')


def keychain_value(name):
    result = subprocess.run(
        ['security', 'find-generic-password', '-a', ACCOUNT, '-s', name, '-w'],
        check=True, capture_output=True, text=True,
    )
    value = result.stdout.strip()
    if name == 'WEBTOP_STUDENT' and re.fullmatch(r'[0-9a-fA-F]+', value) and len(value) % 2 == 0:
        value = bytes.fromhex(value).decode('utf-8')
    if not value:
        raise RuntimeError(f'Missing Keychain value: {name}')
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--validate', action='store_true')
    options = parser.parse_args()
    project_dir = Path(__file__).resolve().parent
    schedule = Path(os.getenv('LOCAL_SCHEDULE', project_dir / 'data' / 'schedule.ics'))
    if not schedule.is_file():
        raise RuntimeError(f'Missing schedule file: {schedule}')
    for key in KEYS:
        os.environ[key] = keychain_value(key)
    os.environ['SCHEDULE_URI'] = str(schedule)
    os.environ.setdefault('LOOKBACK_WEEKS', '4')
    import bot
    if options.validate:
        bot.telegram = lambda message: print(
            f'Local validation passed; Telegram message length={len(message)} characters.'
        )
    bot.main()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Local homework update failed; error_type={type(error).__name__}; sensitive details suppressed.')
        raise SystemExit(1)
