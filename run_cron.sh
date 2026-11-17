#!/bin/sh
set -eu
umask 077

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
env_file=${BOT_ENV_FILE:-}

if [ -z "$env_file" ] || [ ! -f "$env_file" ]; then
  echo 'BOT_ENV_FILE must point to a private environment file' >&2
  exit 1
fi

# GNU stat is standard on the Linux systems targeted by this cron helper.
mode=$(stat -c '%a' "$env_file")
if [ "$mode" != '600' ]; then
  echo 'The environment file must have mode 600' >&2
  exit 1
fi

set -a
# The file is user-controlled and must contain shell-compatible KEY='value' lines.
. "$env_file"
set +a

: "${WEBTOP_WEB_TOKEN:?missing WEBTOP_WEB_TOKEN}"
: "${WEBTOP_STUDENT:?missing WEBTOP_STUDENT}"
: "${TELEGRAM_BOT_TOKEN:?missing TELEGRAM_BOT_TOKEN}"
: "${TELEGRAM_CHAT_ID:?missing TELEGRAM_CHAT_ID}"
: "${SCHEDULE_URI:?missing SCHEDULE_URI}"

python_bin=${BOT_PYTHON:-"$project_dir/.venv/bin/python"}
exec "$python_bin" "$project_dir/bot.py"
