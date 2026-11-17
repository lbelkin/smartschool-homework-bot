#!/bin/zsh
set -eu
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
print 'Webtop connector v2 — API only. This launcher does not open Chromium.'
webtop_project_dir="${0:A:h}"
if [[ ! -f "$webtop_project_dir/connect_api.py" || ! -f "$webtop_project_dir/webtop_api.py" ]]; then
  print -u2 'Не найдены файлы проекта Webtop. Откройте исходную папку проекта.'
  exit 1
fi
if [[ "${1:-}" == '--check' ]]; then
  print -r -- "$webtop_project_dir/connect_api.py"
  exit 0
fi
cd "$webtop_project_dir"
python3 -m venv "$webtop_project_dir/.login-venv"
"$webtop_project_dir/.login-venv/bin/pip" -q install 'requests>=2.32,<3' 'beautifulsoup4>=4.12,<5'
if ! "$webtop_project_dir/.login-venv/bin/python" "$webtop_project_dir/connect_api.py"; then
  read '?Подключение не завершено. Нажмите Enter, чтобы закрыть окно.'
  exit 1
fi
read '?Нажмите Enter, чтобы закрыть окно.'
