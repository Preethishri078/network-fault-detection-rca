import pytest
from pathlib import Path
from src.models import RawEvent, EventType, Severity, AlarmStatus
from src.topology import NetworkTopology
from src.classifier import EventClassifier

BASE_DIR = Path(__file__).resolve().parent.parent
TOPOLOGY_FILE = BASE_DIR / "data" / "topology.json"
RULES_FILE = BASE_DIR / "data" / "rules.yaml"


def test_classifier_base_and_escalation():
    topology = NetworkTopology(TOPOLOGY_FILE)
    classifier = EventClassifier(RULES_FILE, topology)

    # Core node escalation: LINK_DOWN on Core1 (base MAJOR -> escalated to CRITICAL)
    evt_core = RawEvent(source_device="Cisco-Nexus9K-Core1", event_type=EventType.LINK_DOWN)
    alarm_core = classifier.classify(evt_core)
    assert alarm_core is not None
    assert alarm_core.severity == Severity.CRITICAL

    # Access node: LINK_DOWN on Acc1 (base MAJOR -> remains MAJOR)
    evt_acc = RawEvent(source_device="Juniper-EX2300-Acc1", event_type=EventType.LINK_DOWN)
    alarm_acc = classifier.classify(evt_acc)
    assert alarm_acc is not None
    assert alarm_acc.severity == Severity.MAJOR


def test_classifier_thresholds():
    classifier = EventClassifier(RULES_FILE)

    evt_low = RawEvent(source_device="Dell-PowerEdge-Srv01", event_type=EventType.PACKET_LOSS, details={"loss_pct": 5.0})
    alarm_low = classifier.classify(evt_low)
    assert alarm_low.severity == Severity.MINOR

    evt_high = RawEvent(source_device="Dell-PowerEdge-Srv01", event_type=EventType.PACKET_LOSS, details={"loss_pct": 15.0})
    alarm_high = classifier.classify(evt_high)
    assert alarm_high.severity == Severity.MAJOR


def test_classifier_clearing_events():
    classifier = EventClassifier(RULES_FILE)

    evt_up = RawEvent(source_device="Juniper-EX2300-Acc1", event_type=EventType.LINK_UP)
    alarm_up = classifier.classify(evt_up)
    assert alarm_up.status == AlarmStatus.CLEARED
    assert alarm_up.event_type == EventType.LINK_DOWN
