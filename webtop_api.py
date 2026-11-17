import hashlib
import json
import os
import re
from datetime import date, datetime, time, timedelta
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

HOST = 'https://webtopserver.smartschool.co.il'


def clean(value):
    return ' '.join(str(value or '').split())


def parse_week(days):
    if not isinstance(days, list) or not days:
        raise ValueError('Missing dated week')
    tasks, dates = [], []
    for day in days:
        day_date = date.fromisoformat(day['date'][:10])
        dates.append(day_date)
        for hour in day['hoursData'] or []:
            for entry in hour['scheduale'] or []:
                text = BeautifulSoup(entry.get('homeWork') or '', 'html.parser').get_text(' ', strip=True)
                if clean(text).strip('.!:-־') in ('', 'אין', 'אין שיעורי בית', 'אין שעורי בית', 'לא הוזן', 'ללא', 'ללא שיעורי בית'):
                    continue
                subject = clean(entry['subject_name'])
                if not subject:
                    raise ValueError('Missing subject')
                identity = '|'.join((day_date.isoformat(), subject, text))
                tasks.append(dict(id=hashlib.sha256(identity.encode()).hexdigest()[:24],
                                  subject=subject, text=text, lesson_date=day_date.isoformat(), deadline=None))
    return tasks, dates


def parse_hour_name(value):
    if not clean(value):
        return None, None
    matches = re.findall(r'(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)', clean(value))
    if not matches:
        raise ValueError('Schedule hour has no start time')
    values = [time(int(hour), int(minute)) for hour, minute in matches]
    return values[0], values[1] if len(values) > 1 else None


def cancelled(entry, hour):
    changes = list(hour.get('changes') or []) + list(entry.get('changes') or [])
    return any(change.get('isClassCancel') is True or
               clean(change.get('definition')) == 'ביטול שיעור'
               for change in changes if isinstance(change, dict))


def parse_schedule_week(days, sunday, period_times=None):
    period_times = period_times or {}
    if not isinstance(days, list):
        raise ValueError('Missing schedule week')
    lessons = []
    for day in days:
        if not isinstance(day, dict):
            raise ValueError('Invalid schedule day')
        day_index = day.get('dayIndex', day.get('day', day.get('dayId')))
        if not isinstance(day_index, int) or not 1 <= day_index <= 7:
            raise ValueError('Invalid schedule day index')
        lesson_date = sunday + timedelta(days=day_index - 1)
        for hour in day.get('hoursData') or []:
            entries = hour.get('scheduale', hour.get('schedule')) or []
            if not isinstance(entries, list):
                raise ValueError('Invalid schedule entries')
            period = hour.get('hour')
            starts_at, ends_at = parse_hour_name(hour.get('hourName'))
            if starts_at is None and str(period) in period_times:
                starts_at, ends_at = parse_hour_name(period_times[str(period)])
            time_known = starts_at is not None
            if not time_known:
                if not isinstance(period, int) or period < 1:
                    raise ValueError('Schedule entry has neither time nor lesson number')
                starts_at = time(0, min(period, 59))
            for entry in entries:
                if not isinstance(entry, dict) or cancelled(entry, hour):
                    continue
                subject = clean(entry.get('subject') or entry.get('subject_name'))
                if not subject:
                    continue
                start = datetime.combine(lesson_date, starts_at, ZoneInfo('Asia/Jerusalem'))
                end = datetime.combine(lesson_date, ends_at, ZoneInfo('Asia/Jerusalem')) if ends_at else start + timedelta(minutes=45)
                lessons.append(dict(subject=subject, start=start, end=end,
                                    period=period, time_known=time_known,
                                    teacher=clean(entry.get('teacherPrivateName')) + (' ' if entry.get('teacherPrivateName') and entry.get('teacherLastName') else '') + clean(entry.get('teacherLastName')),
                                    location=clean(entry.get('room'))))
    return lessons


class Client:
    def __init__(self, token):
        self.session = requests.Session()
        token = unquote(token.strip())
        if not token or any(character in token for character in '\r\n'):
            raise ValueError('Invalid session token')
        self.session.cookies.set('webToken', token, domain='webtopserver.smartschool.co.il', secure=True)
        self.session.headers.update({'Origin': 'https://webtop.smartschool.co.il', 'language': 'he'})

    def post(self, route, payload):
        response = self.session.post(HOST + '/server/api/' + route, json=payload, timeout=30, allow_redirects=False)
        if response.status_code != 200:
            raise RuntimeError('Webtop request rejected; HTTP ' + str(response.status_code))
        body = response.json()
        if not isinstance(body, dict) or body.get('status') is not True:
            raise RuntimeError('Webtop session or request rejected')
        return body['data']

    def student(self, expected_name):
        dashboard = self.post('dashboard/InitDashboard', {})
        students = dashboard if isinstance(dashboard, list) else dashboard['childrens']
        matches = []
        for student in students:
            names = [student.get('studentName'), student.get('name'),
                     clean(student.get('firstName')) + ' ' + clean(student.get('lastName')),
                     clean(student.get('lastName')) + ' ' + clean(student.get('firstName'))]
            if clean(expected_name) in [clean(name) for name in names if name]:
                matches.append(student)
        if len(matches) != 1:
            raise ValueError('Cannot uniquely identify requested student')
        return matches[0]

    def homework(self, expected_name, weeks):
        student = self.student(expected_name)
        params = dict(studentID=student['id'], classCode=student['classCode'],
                      studyYear=student.get('studyYear'), studentName=expected_name, moduleID=11, viewType=0)
        if any(params[key] is None for key in ('studentID', 'classCode')):
            raise ValueError('Missing current student parameters')
        today = datetime.now(ZoneInfo('Asia/Jerusalem')).date()
        sunday = today - timedelta(days=(today.weekday() + 1) % 7)
        tasks = {}
        for week in range(weeks):
            data = self.post('PupilCard/GetPupilLessonsAndHomework', dict(params, weekIndex=-week))
            parsed, dates = parse_week(data)
            beginning = sunday - timedelta(weeks=week)
            if any(not beginning <= value < beginning + timedelta(days=7) for value in dates):
                raise ValueError('API week does not match requested coverage')
            tasks.update((task['id'], task) for task in parsed)
        return list(tasks.values())

    def schedule(self, expected_name, start, end):
        student = self.student(expected_name)
        required = ('id', 'classCode')
        if any(student.get(key) is None for key in required):
            raise ValueError('Missing current student schedule parameters')
        today = datetime.now(ZoneInfo('Asia/Jerusalem')).date()
        study_year = student.get('studyYear') or os.getenv('WEBTOP_STUDY_YEAR')
        if study_year is None:
            study_year = today.year if today.month >= 8 else today.year - 1
        study_year = int(study_year)
        if not 2000 <= study_year <= 2100:
            raise ValueError('Invalid Webtop study year')
        current_sunday = today - timedelta(days=(today.weekday() + 1) % 7)
        first_sunday = start.date() - timedelta(days=(start.date().weekday() + 1) % 7)
        last_date = (end - timedelta(microseconds=1)).date()
        last_sunday = last_date - timedelta(days=(last_date.weekday() + 1) % 7)
        lessons = {}
        period_times = json.loads(os.getenv('WEBTOP_PERIOD_TIMES', '{}'))
        if not isinstance(period_times, dict):
            raise ValueError('WEBTOP_PERIOD_TIMES must be a JSON object')
        sunday = first_sunday
        while sunday <= last_sunday:
            week_index = (sunday - current_sunday).days // 7
            payload = dict(weekIndex=week_index, viewType=0, studyYear=study_year,
                           studentID=student['id'], classCode=student['classCode'], moduleID=10)
            data = self.post('PupilCard/GetPupilScheduale', payload)
            for lesson in parse_schedule_week(data, sunday, period_times):
                if start <= lesson['start'] < end:
                    key = (lesson['start'], lesson['subject'], lesson['teacher'], lesson['location'])
                    lessons[key] = lesson
            sunday += timedelta(days=7)
        return sorted(lessons.values(), key=lambda item: item['start'])

    def close(self):
        self.session.close()


def fetch_homework():
    client = Client(os.environ['WEBTOP_WEB_TOKEN'])
    try:
        return client.homework(os.environ['WEBTOP_STUDENT'], int(os.getenv('LOOKBACK_WEEKS', '4')))
    finally:
        client.close()


def fetch_schedule(start, end):
    client = Client(os.environ['WEBTOP_WEB_TOKEN'])
    try:
        return client.schedule(os.environ['WEBTOP_STUDENT'], start, end)
    finally:
        client.close()
