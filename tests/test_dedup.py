import pytest
from datetime import datetime
from src.models import Alarm, EventType, Severity, AlarmRole, AlarmStatus
from src.dedup import AlarmDeduplicator


def test_alarm_deduplication():
    dedup = AlarmDeduplicator(sliding_window_seconds=30.0)
    now = datetime.now()

    alarm1 = Alarm(source_device="Juniper-EX2300-Acc2", event_type=EventType.NODE_UNREACHABLE, severity=Severity.CRITICAL, first_seen=now, last_seen=now)
    alarm2 = Alarm(source_device="Juniper-EX2300-Acc2", event_type=EventType.NODE_UNREACHABLE, severity=Severity.CRITICAL, first_seen=now, last_seen=now)

    processed1, is_new1 = dedup.process_alarm(alarm1)
    assert is_new1 is True
    assert processed1.occurrence_count == 1

    processed2, is_new2 = dedup.process_alarm(alarm2)
    assert is_new2 is False
    assert processed2.occurrence_count == 2
    assert len(dedup.get_active_alarms()) == 1


def test_flapping_detection():
    dedup = AlarmDeduplicator(sliding_window_seconds=30.0, flap_threshold_count=5)
    now = datetime.now()

    for i in range(5):
        alarm = Alarm(source_device="Arista-7050X-DistB", event_type=EventType.LINK_DOWN, severity=Severity.MAJOR, first_seen=now, last_seen=now)
        processed, _ = dedup.process_alarm(alarm)

    assert processed.is_flapping is True
    assert processed.role == AlarmRole.FLAPPING


def test_noise_reduction_metric():
    dedup = AlarmDeduplicator()
    now = datetime.now()

    for _ in range(100):
        alarm = Alarm(source_device="Juniper-EX2300-Acc1", event_type=EventType.NODE_UNREACHABLE, severity=Severity.CRITICAL, first_seen=now, last_seen=now)
        dedup.process_alarm(alarm)

    assert dedup.raw_events_count == 100
    assert dedup.unique_alarms_count == 1
    assert dedup.noise_reduction_pct == 99.0
