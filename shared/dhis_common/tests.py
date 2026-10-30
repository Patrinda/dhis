import datetime
import time
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from . import clients, events
from .models import OutboxEvent
from .utils import hash_identifier, mask_identifier


@override_settings(CIRCUIT_FAILURES=3, CIRCUIT_RESET_SECONDS=1, CIRCUIT_SUCCESSES=2)
class CircuitBreakerTests(SimpleTestCase):
    def test_opens_after_repeated_failures_then_recovers(self):
        breaker = clients.CircuitBreaker("svc")
        for _ in range(3):
            self.assertTrue(breaker.allow())
            breaker.record_failure()
        self.assertEqual(breaker.state, "OPEN")
        self.assertFalse(breaker.allow())           # calls fail fast while open
        time.sleep(1.1)
        self.assertTrue(breaker.allow())            # one probe is allowed
        self.assertEqual(breaker.state, "HALF_OPEN")
        breaker.record_success()
        breaker.record_success()
        self.assertEqual(breaker.state, "CLOSED")   # closes after enough successes

    def test_failed_probe_reopens(self):
        breaker = clients.CircuitBreaker("svc2")
        breaker.state = "HALF_OPEN"
        breaker.record_failure()
        self.assertEqual(breaker.state, "OPEN")


class UtilsTests(SimpleTestCase):
    def test_hash_is_stable_and_hides_the_number(self):
        self.assertEqual(hash_identifier("1199880012345678"), hash_identifier("1199880012345678"))
        self.assertNotIn("1199880012345678", hash_identifier("1199880012345678"))
        self.assertNotEqual(hash_identifier("1199880012345678"), hash_identifier("1199880012345679"))

    def test_mask(self):
        self.assertEqual(mask_identifier("1199880012345678"), "1************678")


@override_settings(EVENT_SUBSCRIBERS=["http://127.0.0.1:1"], EVENT_MAX_ATTEMPTS=3, RABBITMQ_URL="")
class OutboxTests(TestCase):
    def test_failed_delivery_backs_off_then_goes_dead(self):
        event = events.publish("test.event", {"a": 1})
        for expected in (1, 2, 3):
            OutboxEvent.objects.filter(pk=event.pk).update(next_attempt_at=timezone.now() - datetime.timedelta(seconds=1))
            events.dispatch_once()
            event.refresh_from_db()
            self.assertEqual(event.attempts, expected)
        self.assertEqual(event.status, OutboxEvent.DEAD)

    def test_successful_delivery_marks_sent(self):
        event = events.publish("test.event", {"a": 1})
        with mock.patch.object(events, "_send") as send:
            self.assertEqual(events.dispatch_once(), 1)
            send.assert_called_once()
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxEvent.SENT)

    def test_duplicate_message_is_processed_once(self):
        seen = []
        env = {"message_id": "6f1d7b0e-2f0a-4d2a-9d0b-111111111111", "type": "x"}
        self.assertTrue(events.process_once(env, seen.append))
        self.assertFalse(events.process_once(env, seen.append))
        self.assertEqual(len(seen), 1)
