import unittest
from datetime import date
from unittest.mock import patch

from icalendar import Calendar

from export_webtop_ics import calendar_bytes
import bot
from webtop_api import parse_schedule_week


class ScheduleTest(unittest.TestCase):
    def test_parse_and_export(self):
        payload = [
            {
                'dayIndex': 1,
                'hoursData': [
                    {
                        'hour': 1,
                        'hourName': '08:00 - 08:45',
                        'scheduale': [
                            {'subject': 'מתמטיקה', 'teacherPrivateName': 'Dana',
                             'teacherLastName': 'Cohen', 'room': '12'},
                        ],
                    },
                    {
                        'hour': 2,
                        'hourName': '08:50 - 09:35',
                        'scheduale': [
                            {'subject': 'עברית', 'changes': [{'definition': 'ביטול שיעור'}]},
                        ],
                    },
                ],
            },
        ]
        lessons = parse_schedule_week(payload, date(2026, 11, 15))
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]['subject'], 'מתמטיקה')
        self.assertEqual(lessons[0]['start'].strftime('%Y-%m-%d %H:%M'), '2026-11-15 08:00')
        self.assertEqual(lessons[0]['end'].strftime('%H:%M'), '08:45')
        self.assertEqual(lessons[0]['teacher'], 'Dana Cohen')
        self.assertEqual(lessons[0]['location'], '12')
        calendar = Calendar.from_ical(calendar_bytes(lessons))
        events = calendar.walk('VEVENT')
        self.assertEqual(len(events), 1)
        self.assertEqual(str(events[0]['SUMMARY']), 'מתמטיקה')

    def test_missing_clock_time_becomes_all_day_ics(self):
        payload = [{'dayIndex': 2, 'hoursData': [
            {'hour': 3, 'hourName': None, 'scheduale': [{'subject': 'Science'}]},
        ]}]
        lessons = parse_schedule_week(payload, date(2026, 11, 15))
        self.assertFalse(lessons[0]['time_known'])
        self.assertEqual(lessons[0]['period'], 3)
        event = Calendar.from_ical(calendar_bytes(lessons)).walk('VEVENT')[0]
        self.assertIsInstance(event.decoded('DTSTART'), date)
        self.assertNotIsInstance(event.decoded('DTSTART'), __import__('datetime').datetime)

    @patch.dict('os.environ', {'SCHEDULE_SOURCE': 'auto', 'SCHEDULE_URI': '/private/fallback.ics'})
    @patch.object(bot, 'fetch_ics_lessons', return_value=([{'subject': 'fallback'}], 'ICS'))
    @patch.object(bot, 'fetch_schedule', side_effect=RuntimeError('unavailable'))
    def test_auto_source_uses_ics_fallback(self, _webtop, _ics):
        lessons, information = bot.fetch_lessons(None, None)
        self.assertEqual(lessons, [{'subject': 'fallback'}])
        self.assertIn('ICS', information)

    @patch.dict('os.environ', {'SCHEDULE_SOURCE': 'webtop'})
    @patch.object(bot, 'fetch_schedule', return_value=[{'subject': 'live'}])
    def test_webtop_source_is_preferred(self, _webtop):
        lessons, information = bot.fetch_lessons(None, None)
        self.assertEqual(lessons, [{'subject': 'live'}])
        self.assertIn('Webtop', information)


if __name__ == '__main__':
    unittest.main()
