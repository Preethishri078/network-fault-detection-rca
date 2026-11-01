from datetime import datetime, timedelta
from typing import Dict, Tuple, List, Optional
from src.models import Alarm, AlarmStatus, AlarmRole, EventType


class AlarmDeduplicator:
    def __init__(self, sliding_window_seconds: float = 30.0, flap_threshold_count: int = 5, flap_window_seconds: float = 30.0):
        self.sliding_window = timedelta(seconds=sliding_window_seconds)
        self.flap_threshold_count = flap_threshold_count
        self.flap_window = timedelta(seconds=flap_window_seconds)
        
        # Key: (source_device, event_type) -> Alarm
        self.active_alarms: Dict[Tuple[str, EventType], Alarm] = {}
        # Key: (source_device, event_type) -> List[datetime] timestamps for flap detection
        self.event_timestamps: Dict[Tuple[str, EventType], List[datetime]] = {}
        
        # Metrics
        self.raw_events_count: int = 0
        self.unique_alarms_count: int = 0

    def process_alarm(self, alarm: Alarm) -> Tuple[Optional[Alarm], bool]:
        """
        Process an incoming alarm.
        Returns:
            (alarm_object, is_new)
            - If it's a clearing alarm, removes/clears active alarm and returns it.
            - If duplicate within sliding window, updates active alarm and returns it (is_new=False).
            - If new alarm, adds to active_alarms and returns it (is_new=True).
        """
        self.raw_events_count += 1
        key = alarm.key()
        now = alarm.last_seen

        # Track timestamp for flapping detection
        if key not in self.event_timestamps:
            self.event_timestamps[key] = []
        self.event_timestamps[key].append(now)
        # Prune old timestamps outside flap window
        cutoff = now - self.flap_window
        self.event_timestamps[key] = [ts for ts in self.event_timestamps[key] if ts >= cutoff]

        is_flapping = len(self.event_timestamps[key]) >= self.flap_threshold_count

        # Handle CLEARED alarms
        if alarm.status == AlarmStatus.CLEARED:
            if key in self.active_alarms:
                existing = self.active_alarms[key]
                existing.status = AlarmStatus.CLEARED
                existing.last_seen = now
                del self.active_alarms[key]
                return existing, False
            return alarm, False

        # Handle active alarm deduplication
        if key in self.active_alarms:
            existing = self.active_alarms[key]
            # Check if existing alarm is still within sliding window
            if (now - existing.last_seen) <= self.sliding_window:
                existing.occurrence_count += 1
                existing.last_seen = now
                if is_flapping:
                    existing.is_flapping = True
                    existing.role = AlarmRole.FLAPPING
                return existing, False
            else:
                # Expired existing alarm; treat new arrival as fresh alarm
                pass

        # Create new active alarm entry
        alarm.is_flapping = is_flapping
        if is_flapping:
            alarm.role = AlarmRole.FLAPPING

        self.active_alarms[key] = alarm
        self.unique_alarms_count += 1
        return alarm, True

    def sweep_expired(self, current_time: Optional[datetime] = None) -> List[Alarm]:
        """Sweep and expire active alarms older than the sliding window."""
        now = current_time or datetime.now()
        expired: List[Alarm] = []
        keys_to_remove = []

        for key, alarm in self.active_alarms.items():
            if (now - alarm.last_seen) > self.sliding_window:
                alarm.status = AlarmStatus.CLEARED
                expired.append(alarm)
                keys_to_remove.append(key)

        for k in keys_to_remove:
            del self.active_alarms[k]

        return expired

    def get_active_alarms(self) -> List[Alarm]:
        return list(self.active_alarms.values())

    @property
    def noise_reduction_pct(self) -> float:
        if self.raw_events_count == 0:
            return 0.0
        return ((self.raw_events_count - self.unique_alarms_count) / self.raw_events_count) * 100.0
