from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from controlrecord.schedules import Schedules, next_weekly


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Schedules(self.root)
        self.now = datetime(2026, 10, 22, 12)  # Thursday
        self.script = Mock(id='abc', name='Script A')
        self.script.name = 'Script A'

    def tearDown(self):
        self.temp.cleanup()

    def add(self, kind='once', days=None):
        self.store.add(self.script, kind, self.now + timedelta(minutes=1), days or [3], '12:01', False, self.now)

    def test_two_one_shots_same_script_fire_once_each(self):
        self.add()
        self.store.add(self.script, 'once', self.now + timedelta(minutes=2), [], '12:02', True, self.now)
        launch = Mock(return_value='已啟動')
        self.store.poll(self.now + timedelta(minutes=1), launch)
        self.store.poll(self.now + timedelta(minutes=1, seconds=1), launch)
        self.assertEqual(launch.call_count, 1)
        self.store.poll(self.now + timedelta(minutes=2), launch)
        self.assertEqual(launch.call_count, 2)
        self.assertFalse(self.store.items[0]['video'])
        self.assertTrue(self.store.items[1]['video'])

    def test_weekdays_and_week_rollover(self):
        self.assertEqual(next_weekly([0, 3, 6], '11:00', self.now), datetime(2026, 10, 25, 11))
        self.assertEqual(next_weekly([3], '12:00', self.now), datetime(2026, 10, 29, 12))
        with self.assertRaises(ValueError):
            next_weekly([], '12:00', self.now)

    def test_restart_skips_overdue_and_advances_weekly(self):
        self.add()
        self.add('weekly')
        store = Schedules(self.root)
        launch = Mock()
        store.poll(self.now + timedelta(minutes=2), launch, startup=True)
        launch.assert_not_called()
        self.assertFalse(store.items[0]['enabled'])
        self.assertTrue(store.items[1]['enabled'])
        self.assertEqual(store.items[1]['next'], '2026-10-29T12:01:00')

    def test_busy_and_failure_are_consumed(self):
        self.add()
        self.add('weekly')
        launch = Mock(side_effect=['略過：程式忙碌', RuntimeError('locked')])
        self.store.poll(self.now + timedelta(minutes=1), launch)
        self.assertIn('忙碌', self.store.items[0]['status'])
        self.assertIn('locked', self.store.items[1]['status'])
        self.store.poll(self.now + timedelta(minutes=1, seconds=1), launch)
        self.assertEqual(launch.call_count, 2)

    def test_disk_failure_never_launches(self):
        self.add()
        launch = Mock()
        with patch.object(self.store, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.poll(self.now + timedelta(minutes=1), launch)
        launch.assert_not_called()

    def test_sleep_gap_skips_missed_occurrence(self):
        self.add()
        launch = Mock()
        self.store.poll(self.now + timedelta(hours=1), launch)
        launch.assert_not_called()
