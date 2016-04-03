from datetime import datetime
import json

from basecase import RedBeatCase

from redbeat import RedBeatSchedulerEntry
from redbeat.decoder import RedBeatJSONDecoder, RedBeatJSONEncoder


class test_RedBeatEntry(RedBeatCase):

    def test_basic_save(self):
        e = self.create_entry()
        e.save()

        expected = {
            'name': 'test',
            'task': 'tasks.test',
            'schedule': e.schedule,
            'args': None,
            'kwargs': None,
            'options': {},
            'enabled': True,
        }

        redis = self.app.redbeat_redis
        value = redis.hget(self.app.conf.REDBEAT_KEY_PREFIX + 'test', 'definition')
        self.assertEqual(expected, json.loads(value, cls=RedBeatJSONDecoder))
        self.assertEqual(redis.zrank(self.app.conf.REDBEAT_SCHEDULE_KEY, e.key), 0)
        self.assertEqual(redis.zscore(self.app.conf.REDBEAT_SCHEDULE_KEY, e.key), e.score)

    def test_load_meta_nonexistent_key(self):
        meta = RedBeatSchedulerEntry.load_meta('doesntexist', self.app)
        self.assertEqual(meta, {'last_run_at': datetime.min})

    def test_load_definition_nonexistent_key(self):
        with self.assertRaises(KeyError):
            RedBeatSchedulerEntry.load_definition('doesntexist', self.app)

    def test_from_key_nonexistent_key(self):
        with self.assertRaises(KeyError):
            RedBeatSchedulerEntry.from_key('doesntexist', self.app)

    def test_next(self):
        initial = self.create_entry()
        now = self.app.now()

        n = initial.next(last_run_at=now)

        # new entry has updated run info
        self.assertNotEqual(initial, n)
        self.assertEqual(n.last_run_at, now)
        self.assertEqual(initial.total_run_count + 1, n.total_run_count)

        # updated meta was stored into redis
        meta = RedBeatSchedulerEntry.load_meta(initial.key, app=self.app)
        self.assertEqual(meta['last_run_at'], now)
        self.assertEqual(meta['total_run_count'], initial.total_run_count + 1)

        # new entry updated the schedule
        redis = self.app.redbeat_redis
        self.assertEqual(redis.zscore(self.app.conf.REDBEAT_SCHEDULE_KEY, n.key), n.score)

    def test_next_only_update_last_run_at(self):
        initial = self.create_entry()

        n = initial.next(only_update_last_run_at=True)
        self.assertGreater(n.last_run_at, initial.last_run_at)
        self.assertEqual(n.total_run_count, initial.total_run_count)

    def test_delete(self):
        initial = self.create_entry()
        initial.save()

        e = RedBeatSchedulerEntry.from_key(initial.key, app=self.app)
        e.delete()

        exists = self.app.redbeat_redis.exists(initial.key)
        self.assertFalse(exists)

        score = self.app.redbeat_redis.zrank(self.app.conf.REDBEAT_SCHEDULE_KEY, initial.key)
        self.assertIsNone(score)