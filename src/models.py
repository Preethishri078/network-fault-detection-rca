from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
import uuid


class DeviceType(str, Enum):
    CORE = "CORE"
    DIST = "DIST"
    ACCESS = "ACCESS"
    SERVER = "SERVER"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFO = "INFO"


class AlarmStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CLEARED = "CLEARED"


class AlarmRole(str, Enum):
    PRIMARY_FAULT = "PRIMARY_FAULT"
    SECONDARY_CORRELATED = "SECONDARY_CORRELATED"
    STANDALONE = "STANDALONE"
    FLAPPING = "FLAPPING"
    INFERRED_ROOT = "INFERRED_ROOT"


class EventType(str, Enum):
    NODE_UNREACHABLE = "NODE_UNREACHABLE"
    NODE_REACHABLE = "NODE_REACHABLE"
    LINK_DOWN = "LINK_DOWN"
    LINK_UP = "LINK_UP"
    PACKET_LOSS = "PACKET_LOSS"
    HIGH_LATENCY = "HIGH_LATENCY"


class Device(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    id: str
    type: DeviceType
    ip: str
    location: str
    role_description: Optional[str] = None


class RawEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    source_device: str
    event_type: EventType
    details: Dict[str, Any] = Field(default_factory=dict)


class Alarm(BaseModel):
    alarm_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    first_seen: datetime = Field(default_factory=datetime.now)
    last_seen: datetime = Field(default_factory=datetime.now)
    source_device: str
    event_type: EventType
    severity: Severity
    status: AlarmStatus = AlarmStatus.ACTIVE
    occurrence_count: int = 1
    role: AlarmRole = AlarmRole.STANDALONE
    correlated_to: Optional[str] = None
    is_flapping: bool = False

    def key(self) -> tuple[str, EventType]:
        return (self.source_device, self.event_type)


class Incident(BaseModel):
    incident_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    root_cause_device: str
    probable_cause: str
    primary_alarm: Alarm
    secondary_alarms: List[Alarm] = Field(default_factory=list)
    severity: Severity
    confidence: float
    recommendations: List[str] = Field(default_factory=list)
    start_time: datetime = Field(default_factory=datetime.now)
    inferred_root: bool = False
    affected_devices: List[str] = Field(default_factory=list)
