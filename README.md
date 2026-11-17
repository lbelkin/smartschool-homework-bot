# Smart School homework bot

A Python service that combines a private Smart School Webtop account with an exported iCalendar (`.ics`) timetable and sends a Hebrew homework summary to Telegram.

At 16:00 it reads tomorrow's lessons, looks up Webtop homework recorded since the previous matching lesson, and includes only lessons for which homework exists. If none is found, it sends `אין שיעורי בית למחר.` The next lesson is used for matching, not invented as an official deadline.

## Features

- Handles recurring ICS lessons and exceptions (`RRULE`, `RDATE`, `EXDATE`, `RECURRENCE-ID`).
- Checks the interval since the previous lesson, including assignments entered on another day.
- Deduplicates assignments and groups repeated lessons of one subject.
- Sends Hebrew messages with subject, next lesson time, Webtop lesson date and assignment text.
- Supports local macOS Keychain + `launchd`, with optional GCP deployment code.
- Stops on unexpected API/calendar formats instead of guessing dates.

## Privacy and security

This repository contains no Webtop session, student name, Telegram token/chat ID, timetable, logs or cloud identifiers. Keep the ICS file private because it can reveal a child's schedule.

Required secrets are `WEBTOP_WEB_TOKEN`, `WEBTOP_STUDENT`, `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Never commit them. `.gitignore` excludes `.env`, `data/`, token files, logs and virtual environments. Webtop sessions expire and must be replaced manually; this project does not bypass CAPTCHA or Cloudflare.

## Local macOS setup

Requires Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p data
cp /path/to/private-export.ics data/schedule.ics
```

Store secrets in macOS Keychain under account `school-homework-bot`:

```bash
security add-generic-password -U -a school-homework-bot -s WEBTOP_WEB_TOKEN -w
security add-generic-password -U -a school-homework-bot -s WEBTOP_STUDENT -w
security add-generic-password -U -a school-homework-bot -s TELEGRAM_BOT_TOKEN -w
security add-generic-password -U -a school-homework-bot -s TELEGRAM_CHAT_ID -w
```

Each command securely prompts for its value. Do not put values directly in shell history.

```bash
# Validate without sending Telegram
.venv/bin/python run_local.py --validate

# Send the real summary
.venv/bin/python run_local.py
```

For daily execution, copy `com.example.school-homework.plist`, replace the `REPLACE_WITH_...` placeholders with absolute paths, save it under `~/Library/LaunchAgents/`, then run `launchctl bootstrap gui/$(id -u) FILE.plist`. The template runs daily at 16:00 in the Mac's local timezone. The Mac must be on and online.

Set `LOCAL_SCHEDULE` or `KEYCHAIN_ACCOUNT` to override the default file or Keychain account.

## Optional GCP deployment

`config.example.env` contains placeholders only. Cloud deployment expects the four secrets in Secret Manager and a private `gs://` ICS object. Review `deploy.py` before `--apply`; it creates billable resources.

```bash
python deploy.py --project your-project-id \
  --schedule-uri gs://your-private-bucket/schedule.ics --apply
```

`connect_api.py` validates a manually supplied Webtop token and updates Secret Manager. It requires `GOOGLE_CLOUD_PROJECT` and never asks for the Webtop password.

## Matching model and limitations

- Webtop exposes a lesson date, not a trustworthy publication timestamp or deadline. The bot invents neither.
- Matching is exact after normalization. Confirmed aliases can be supplied through `SUBJECT_ALIASES` as JSON.
- `LOOKBACK_WEEKS` defaults to four weeks; older homework is not checked.
- Schedule changes apply only after replacing the private ICS export.
- Every run may send a new message; exactly-once delivery is not guaranteed.
- The adapter follows the API structure documented by the open-source `smartschool-webtop` project but runs no third-party project code.

## Testing

```bash
python -m compileall -q .
.venv/bin/python run_local.py --validate
```

Validation contacts configured private services and processes school data locally, but does not send Telegram with `--validate`.

## License

MIT
