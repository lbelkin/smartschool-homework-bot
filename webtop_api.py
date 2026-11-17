import hashlib
import os
from datetime import date, datetime, timedelta
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

    def homework(self, expected_name, weeks):
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
        student = matches[0]
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

    def close(self):
        self.session.close()


def fetch_homework():
    client = Client(os.environ['WEBTOP_WEB_TOKEN'])
    try:
        return client.homework(os.environ['WEBTOP_STUDENT'], int(os.getenv('LOOKBACK_WEEKS', '4')))
    finally:
        client.close()
