from pathlib import Path
from typing import Dict, Any, Optional, Union
import yaml
from src.models import RawEvent, Alarm, Severity, EventType, AlarmStatus, DeviceType, AlarmRole
from src.topology import NetworkTopology


class ClassifierError(Exception):
    pass


class EventClassifier:
    def __init__(self, rules_path: Optional[Union[str, Path]] = None, topology: Optional[NetworkTopology] = None):
        self.topology = topology
        self.rules: Dict[str, Any] = {}
        if rules_path:
            self.load_rules(rules_path)

    def load_rules(self, rules_path: Union[str, Path]) -> None:
        path = Path(rules_path)
        if not path.exists():
            raise FileNotFoundError(f"Rules file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            self.rules = yaml.safe_load(f)

    def classify(self, raw_event: RawEvent) -> Optional[Alarm]:
        """Classify a RawEvent into a standardized Alarm, applying thresholds and escalation."""
        event_rules = self.rules.get("event_rules", {})
        device_escalation = self.rules.get("device_type_escalation", {})

        rule = event_rules.get(raw_event.event_type.value, {})
        if not rule:
            # Fallback default severity
            base_severity = Severity.MINOR
        else:
            base_severity = Severity(rule.get("base_severity", "MINOR"))

        # Check thresholds for PACKET_LOSS or HIGH_LATENCY
        if raw_event.event_type == EventType.PACKET_LOSS:
            loss_pct = raw_event.details.get("loss_pct", 0.0)
            high_thresh = rule.get("high_threshold_pct", 10.0)
            if loss_pct >= high_thresh:
                base_severity = Severity(rule.get("high_threshold_severity", "MAJOR"))

        elif raw_event.event_type == EventType.HIGH_LATENCY:
            latency_ms = raw_event.details.get("latency_ms", 0.0)
            sustained = raw_event.details.get("sustained", False)
            thresh_ms = rule.get("sustained_threshold_ms", 200.0)
            if latency_ms >= thresh_ms or sustained:
                base_severity = Severity(rule.get("sustained_threshold_severity", "MAJOR"))

        # Check recovery events (LINK_UP / NODE_REACHABLE)
        if raw_event.event_type in (EventType.LINK_UP, EventType.NODE_REACHABLE):
            cleared_type_str = rule.get("clears_alarm")
            cleared_type = EventType(cleared_type_str) if cleared_type_str else None
            return Alarm(
                source_device=raw_event.source_device,
                event_type=cleared_type if cleared_type else raw_event.event_type,
                severity=Severity.INFO,
                status=AlarmStatus.CLEARED,
                first_seen=raw_event.timestamp,
                last_seen=raw_event.timestamp
            )

        # Apply device type escalation if topology is available
        final_severity = base_severity
        if self.topology:
            device = self.topology.get_device(raw_event.source_device)
            if device:
                esc_rules = device_escalation.get(device.type.value, {})
                if base_severity.value in esc_rules:
                    final_severity = Severity(esc_rules[base_severity.value])

        return Alarm(
            source_device=raw_event.source_device,
            event_type=raw_event.event_type,
            severity=final_severity,
            status=AlarmStatus.ACTIVE,
            first_seen=raw_event.timestamp,
            last_seen=raw_event.timestamp,
            role=AlarmRole.STANDALONE
        )
