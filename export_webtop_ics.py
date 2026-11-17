import argparse
import hashlib
import os
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

from webtop_api import fetch_schedule


TZ = ZoneInfo('Asia/Jerusalem')


def calendar_bytes(lessons):
    calendar = Calendar()
    calendar.add('prodid', '-//Smart School homework bot//Webtop schedule export//EN')
    calendar.add('version', '2.0')
    calendar.add('x-wr-calname', 'Webtop schedule')
    for lesson in lessons:
        event = Event()
        identity = '|'.join((lesson['start'].isoformat(), lesson['subject'],
                             lesson['teacher'], lesson['location']))
        event.add('uid', hashlib.sha256(identity.encode()).hexdigest()[:32] + '@webtop.local')
        event.add('dtstamp', datetime.now(TZ))
        event.add('summary', lesson['subject'])
        event.add('dtstart', lesson['start'])
        event.add('dtend', lesson['end'])
        if lesson['teacher']:
            event.add('description', lesson['teacher'])
        if lesson['location']:
            event.add('location', lesson['location'])
        calendar.add_component(event)
    return calendar.to_ical()


def main():
    parser = argparse.ArgumentParser(description='Export a private Webtop timetable to an ICS file.')
    parser.add_argument('--output', required=True, help='Destination .ics file')
    parser.add_argument('--weeks-before', type=int, default=0)
    parser.add_argument('--weeks-after', type=int, default=8)
    parser.add_argument('--keychain-account', help='Read Webtop secrets from this macOS Keychain account')
    options = parser.parse_args()
    if not 0 <= options.weeks_before <= 52 or not 1 <= options.weeks_after <= 52:
        parser.error('Week ranges must be between 0 and 52')
    if options.keychain_account:
        os.environ['KEYCHAIN_ACCOUNT'] = options.keychain_account
        from run_local import keychain_value
        os.environ['WEBTOP_WEB_TOKEN'] = keychain_value('WEBTOP_WEB_TOKEN')
        os.environ['WEBTOP_STUDENT'] = keychain_value('WEBTOP_STUDENT')
    for name in ('WEBTOP_WEB_TOKEN', 'WEBTOP_STUDENT'):
        if not os.getenv(name):
            parser.error(f'{name} is required')
    now = datetime.now(TZ)
    sunday = now.date() - timedelta(days=(now.weekday() + 1) % 7)
    start = datetime.combine(sunday - timedelta(weeks=options.weeks_before), time(), TZ)
    end = datetime.combine(sunday + timedelta(weeks=options.weeks_after), time(), TZ)
    lessons = fetch_schedule(start, end)
    if not lessons:
        raise RuntimeError('Webtop returned no schedule lessons')
    output = Path(options.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + '.tmp')
    temporary.write_bytes(calendar_bytes(lessons))
    temporary.chmod(0o600)
    temporary.replace(output)
    output.chmod(0o600)
    print(f'Exported {len(lessons)} lessons to {output}')


if __name__ == '__main__':
    main()
