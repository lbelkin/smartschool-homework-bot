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

### Important Webtop token limitation

`WEBTOP_WEB_TOKEN` is a temporary authenticated browser-session cookie, not a durable API key. Smart School does not provide this project with a supported refresh-token flow, an expiry timestamp, or a non-interactive login API. The token can therefore stop working without advance notice and the next run will fail with an authentication error (typically HTTP 401).

Renewal is deliberately manual: sign in through a normal browser, obtain the new `webToken` from your own authenticated session, and replace the stored secret. Headless browser login may be rejected by Cloudflare, and this project neither bypasses that protection nor stores the Webtop password. Cron, `launchd`, Cloud Run, and geographic hosting do not remove this limitation. Monitor failures and plan for periodic manual token replacement.

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

## Linux/Unix cron option

The repository includes `run_cron.sh` for systems without macOS `launchd`. It resolves the project directory dynamically, so it contains no machine-specific path. Create a private configuration outside the repository:

```bash
install -m 600 config.example.env "$HOME/.config/school-homework-bot.env"
# Edit the copied file locally and fill every required value.
```

Use an absolute private path for `SCHEDULE_URI`. Keep the ICS and environment file out of the repository. Test the same command cron will execute:

```bash
BOT_ENV_FILE="$HOME/.config/school-homework-bot.env" ./run_cron.sh
```

Then run `crontab -e` and add the following, replacing both example paths with paths on that machine:

```cron
CRON_TZ=Asia/Jerusalem
0 16 * * * BOT_ENV_FILE=/home/your-user/.config/school-homework-bot.env /opt/school-homework-bot/run_cron.sh >> /home/your-user/.local/state/school-homework-bot.log 2>&1
```

This runs daily at 16:00 Jerusalem time on cron implementations that support `CRON_TZ` (such as Cronie). Otherwise configure the host timezone to `Asia/Jerusalem` or convert the schedule carefully; daylight-saving changes make a fixed UTC time unsafe. Ensure the log directory exists and only its owner can read it. The host must be on and online at the scheduled time; classic cron does not catch up missed runs.

`BOT_PYTHON` may point to another virtual-environment Python executable. The helper refuses a secrets file whose mode is not exactly `600`.

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
