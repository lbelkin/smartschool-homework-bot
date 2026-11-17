import hashlib
import json
import os
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Jerusalem')
URL = 'https://webtop.smartschool.co.il/Student_Card/11'


def normalize(value):
    return re.sub(r'[\s\u2066-\u2069\u200e\u200f]+', ' ', value).strip()


def parse_tables(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    tasks = []
    tables = soup.find_all('table')
    if not tables:
        raise ValueError('Homework tables missing')
    for table in tables:
        heading = table.find_previous(re.compile('^h[1-6]$'))
        match = re.search(r'\d{2}/\d{2}/\d{4}', table.get('aria-label', '') or (heading.get_text() if heading else ''))
        if not match:
            raise ValueError('Lesson date missing')
        lesson_date = datetime.strptime(match[0], '%d/%m/%Y').date().isoformat()
        for row in table.select('tr'):
            text = row.get_text(' ', strip=True)
            if 'שיעורי בית:' not in text:
                continue
            subject = re.search(r'מקצוע:\s*(.*?)\s*מורה:', text)
            period = re.search(r'שיעור\s+(\d+)', text)
            homework = text.split('שיעורי בית:', 1)[1].strip()
            if not subject or not period or not homework:
                raise ValueError('Unrecognized homework row')
            subject_name = normalize(subject[1])
            key = f'{lesson_date}|{subject_name}|{period[1]}'
            tasks.append(dict(id=hashlib.sha256(key.encode()).hexdigest()[:24], subject=subject_name,
                              lesson_date=lesson_date, text=homework, deadline=None))
    return tasks


from webtop_api import fetch_homework, fetch_schedule


def parse_lessons(payload, start, end):
    from icalendar import Calendar
    import recurring_ical_events
    document = Calendar.from_ical(payload)
    if document.name != 'VCALENDAR' or not document.walk('VEVENT'):
        raise ValueError('Calendar has no events')
    lessons = []
    for event in recurring_ical_events.of(document).between(start, end):
        starts = event.decoded('DTSTART')
        if not isinstance(starts, datetime) or str(event.get('STATUS', '')) == 'CANCELLED':
            continue
        if starts.tzinfo is None:
            starts = starts.replace(tzinfo=TZ)
        lessons.append(dict(subject=normalize(str(event.get('SUMMARY', ''))),
                            start=starts.astimezone(TZ), event=event))
    return sorted(lessons, key=lambda lesson: lesson['start'])


def fetch_ics_lessons(start, end):
    from pathlib import Path
    source = os.environ['SCHEDULE_URI']
    if source.startswith('gs://'):
        from google.cloud import storage
        bucket, name = source[5:].split('/', 1)
        blob = storage.Client().bucket(bucket).get_blob(name)
        if blob is None or blob.size > 5_000_000:
            raise ValueError('Missing or oversized schedule')
        payload = blob.download_as_bytes(if_generation_match=blob.generation)
        version = str(blob.generation)
        updated = blob.updated.astimezone(TZ).strftime('%d.%m.%Y')
    else:
        path = Path(source)
        if path.stat().st_size > 5_000_000:
            raise ValueError('Oversized schedule')
        payload = path.read_bytes()
        version = hashlib.sha256(payload).hexdigest()[:12]
        updated = datetime.fromtimestamp(path.stat().st_mtime, TZ).strftime('%d.%m.%Y')
    return parse_lessons(payload, start, end), f'מערכת שעות: קובץ שהועלה ב־{updated}, גרסה {version}. שינויים נכללים לאחר העלאת קובץ חדש.'


def fetch_lessons(start, end):
    source = os.getenv('SCHEDULE_SOURCE', 'auto').lower()
    if source not in ('auto', 'webtop', 'ics'):
        raise ValueError('SCHEDULE_SOURCE must be auto, webtop, or ics')
    if source in ('auto', 'webtop'):
        try:
            lessons = fetch_schedule(start, end)
            if not lessons:
                raise ValueError('Webtop schedule is empty')
            return lessons, 'מערכת שעות: נטענה ישירות מ־Webtop.'
        except Exception:
            if source == 'webtop':
                raise
    if not os.getenv('SCHEDULE_URI'):
        raise RuntimeError('ICS fallback requires SCHEDULE_URI')
    lessons, information = fetch_ics_lessons(start, end)
    return lessons, information + ' המקור החלופי הופעל לאחר כשל ב־Webtop.' if source == 'auto' else information


def tomorrow_agenda(tasks, lessons, tomorrow, coverage_start):
    aliases = json.loads(os.getenv('SUBJECT_ALIASES', '{}'))
    subjects = {}
    for lesson in sorted(lessons, key=lambda item: item['start']):
        if lesson['start'].date() == tomorrow:
            subjects.setdefault(lesson['subject'], []).append(lesson)
    agenda = []
    for subject, scheduled in subjects.items():
        earlier = [lesson['start'].date() for lesson in lessons
                   if lesson['subject'] == subject and lesson['start'].date() < tomorrow]
        previous = max(earlier) if earlier else None
        lower = max(previous, coverage_start) if previous else coverage_start
        selected = {}
        for task in tasks:
            task_subject = normalize(aliases.get(task['subject'], task['subject']))
            if task_subject == subject and lower <= date.fromisoformat(task['lesson_date']) < tomorrow:
                selected[task['id']] = task
        agenda.append(dict(subject=subject, lessons=scheduled, previous=previous,
                           incomplete=previous is None or previous < coverage_start,
                           tasks=sorted(selected.values(), key=lambda task: (task['lesson_date'], task['id']))))
    return agenda


def report(agenda, tomorrow, coverage_start):
    lines = [f"שיעורי בית למחר · {tomorrow.strftime('%d.%m.%Y')}"]
    with_homework = [item for item in agenda if item['tasks']]
    for item in with_homework:
        hours = ', '.join(lesson['start'].strftime('%H:%M') if lesson.get('time_known', True)
                          else f"שיעור {lesson['period']}" for lesson in item['lessons'])
        lines.append(f"\n{item['subject']} · {hours}")
        if item['previous']:
            lines.append(f"השיעור הקודם לפי המערכת: {item['previous']:%d.%m.%Y}")
        if item['incomplete']:
            lines.append('⚠️ לא ניתן לאמת את כל התקופה מאז השיעור הקודם.')
        for task in item['tasks']:
            given = date.fromisoformat(task['lesson_date'])
            lines.append(f"• {task['text']}\nתאריך השיעור ב־Webtop: {given:%d.%m.%Y}")
    if not with_homework:
        lines.append('אין שיעורי בית למחר.')
    lines.append(f'\nנבדקו רישומי Webtop מתאריך {coverage_start:%d.%m.%Y}. מועד השיעור הבא אינו מועד הגשה מאושר.')
    return '\n'.join(lines)


def telegram(message):
    import requests
    endpoint = 'https://api.telegram.org/bot' + os.environ['TELEGRAM_BOT_TOKEN'] + '/sendMessage'
    for offset in range(0, len(message), 3000):
        response = requests.post(endpoint, json={'chat_id': os.environ['TELEGRAM_CHAT_ID'],
                                 'text': message[offset:offset + 3000]}, timeout=30)
        if response.status_code != 200 or not response.json().get('ok'):
            raise RuntimeError('Telegram delivery failed')


def main():
    global CURRENT_STAGE
    now = datetime.now(TZ)
    weeks = int(os.getenv('LOOKBACK_WEEKS', '4'))
    if not 1 <= weeks <= 52:
        raise ValueError('Invalid lookback')
    sunday = now.date() - timedelta(days=(now.weekday() + 1) % 7)
    coverage_start = sunday - timedelta(weeks=weeks - 1)
    CURRENT_STAGE = 'webtop'
    tasks = fetch_homework()
    start = datetime.combine(coverage_start, time(), TZ)
    CURRENT_STAGE = 'schedule'
    lessons, schedule_info = fetch_lessons(start, now + timedelta(days=35))
    tomorrow = now.date() + timedelta(days=1)
    agenda = tomorrow_agenda(tasks, lessons, tomorrow, coverage_start)
    message = report(agenda, tomorrow, coverage_start) + '\n\n' + schedule_info
    if os.getenv('DRY_RUN', 'false').lower() == 'true':
        print(message)
    else:
        CURRENT_STAGE = 'telegram'
        telegram(message)
    CURRENT_STAGE = 'complete'


CURRENT_STAGE = 'startup'


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        try:
            if os.getenv('DRY_RUN', 'false').lower() != 'true':
                telegram('עדכון שיעורי הבית נכשל. לא נוצר סיכום עדכני. יש לבדוק את ההתחברות ל־Webtop, את קובץ מערכת השעות ואת הגדרות השירות.')
        except Exception:
            pass
        print(f'Homework update failed at stage={CURRENT_STAGE}; error_type={type(error).__name__}; sensitive details suppressed.')
        raise SystemExit(1)
