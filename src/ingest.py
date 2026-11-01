import queue
import time
import socket
import csv
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union
from src.models import RawEvent, EventType

logger = logging.getLogger("nms.ingest")


class EventQueue:
    """Thread-safe event ingestion queue."""
    def __init__(self):
        self._queue: queue.Queue[RawEvent] = queue.Queue()

    def push(self, event: RawEvent) -> None:
        self._queue.put(event)

    def pop(self, block: bool = True, timeout: Optional[float] = None) -> Optional[RawEvent]:
        try:
            return self._queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def pop_all(self) -> List[RawEvent]:
        events = []
        while not self._queue.empty():
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    def empty(self) -> bool:
        return self._queue.empty()

    def size(self) -> int:
        return self._queue.qsize()


def load_events_from_csv(csv_path: Union[str, Path]) -> List[RawEvent]:
    """
    Ingest raw telemetry log events from an offline CSV file.
    CSV Schema: timestamp, source_device, event_type, details
    """
    path = Path(csv_path)
    if not path.exists():
        logger.error(f"Log file not found: {path}")
        return []

    events: List[RawEvent] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                event_type = EventType(row["event_type"])
                ts = datetime.fromisoformat(row["timestamp"]) if row.get("timestamp") else datetime.now()
                details = eval(row["details"]) if row.get("details") else {}
                
                evt = RawEvent(
                    timestamp=ts,
                    source_device=row["source_device"],
                    event_type=event_type,
                    details=details
                )
                events.append(evt)
            except Exception as e:
                logger.warning(f"Skipping malformed CSV log line: {row} - Error: {e}")

    logger.info(f"Loaded {len(events)} events from CSV: {path}")
    return events


class RealProbeWorker(threading.Thread):
    """
    Background worker thread running periodic socket/ping probes against mapped target nodes.
    Pushes NODE_UNREACHABLE or HIGH_LATENCY events to EventQueue.
    """
    def __init__(
        self,
        event_queue: EventQueue,
        target_map: Optional[dict[str, tuple[str, int]]] = None,
        interval_seconds: float = 10.0
    ):
        super().__init__(daemon=True)
        self.event_queue = event_queue
        # Default target mapping: node_id -> (host, port)
        self.target_map = target_map or {
            "Fortinet-FW-CloudGW": ("8.8.8.8", 53),
            "Cisco-Nexus9K-Core1": ("127.0.0.1", 80),
            "Cisco-Nexus9K-Core2": ("127.0.0.1", 443)
        }
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.info("RealProbeWorker started background TCP probe loop")
        while not self._stop_event.is_set():
            for node_id, (host, port) in self.target_map.items():
                if self._stop_event.is_set():
                    break
                
                start_t = time.time()
                is_up = False
                latency_ms = 0.0

                try:
                    sock = socket.create_connection((host, port), timeout=2.0)
                    sock.close()
                    is_up = True
                    latency_ms = (time.time() - start_t) * 1000.0
                except (socket.timeout, ConnectionRefusedError, OSError):
                    is_up = False

                if not is_up:
                    event = RawEvent(
                        source_device=node_id,
                        event_type=EventType.NODE_UNREACHABLE,
                        details={"target_host": host, "port": port, "reason": "TCP Connection Timeout"}
                    )
                    self.event_queue.push(event)
                elif latency_ms > 150.0:
                    event = RawEvent(
                        source_device=node_id,
                        event_type=EventType.HIGH_LATENCY,
                        details={"latency_ms": latency_ms, "target_host": host}
                    )
                    self.event_queue.push(event)

            self._stop_event.wait(self.interval_seconds)
