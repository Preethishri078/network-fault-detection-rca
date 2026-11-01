from typing import List, Tuple
from src.models import Alarm, EventType, DeviceType
from src.topology import NetworkTopology


class RCARuleEngine:
    def evaluate(
        self,
        root_device: str,
        topology: NetworkTopology,
        primary_alarm: Alarm,
        secondary_alarms: List[Alarm],
        is_inferred: bool = False
    ) -> Tuple[str, List[str]]:
        """
        Evaluate failure pattern and return (probable_cause, recommendations).
        """
        device = topology.get_device(root_device)
        dev_type = device.type if device else DeviceType.ACCESS
        event_type = primary_alarm.event_type

        # Check if flapping
        if primary_alarm.is_flapping or any(a.is_flapping for a in secondary_alarms):
            cause = f"Flapping interface on {root_device} ({dev_type.value})"
            recs = [
                "Inspect optical SFP transceiver for optical degradation",
                "Check interface error counters (CRC, runts, giants)",
                "Verify speed/duplex negotiation settings",
                "Replace patch cable or SFP module"
            ]
            return cause, recs

        # Silent Parent Inference
        if is_inferred:
            cause = f"Unmonitored failure at parent device {root_device} ({dev_type.value}) causing downstream outages"
            recs = [
                f"Verify physical power and LED status for {root_device}",
                f"Check IP network connectivity and management plane access to {root_device}",
                "Ensure monitoring agent / SNMP polling is properly configured for this device",
                "Dispatch field technician for on-site hardware inspection"
            ]
            return cause, recs

        # Core/Dist Power or Total Node Failure
        if event_type == EventType.NODE_UNREACHABLE:
            if dev_type in (DeviceType.CORE, DeviceType.DIST):
                cause = f"Power grid, PSU, or total hardware failure on {dev_type.value} node {root_device}"
                recs = [
                    f"Check primary and redundant Power Supply Units (PSUs) on {root_device}",
                    "Inspect core power distribution unit (PDU) feeds",
                    "Attempt serial console connection or out-of-band management access",
                    "Verify upstream router/switch link state"
                ]
            else:
                cause = f"Access switch or server power loss on node {root_device}"
                recs = [
                    f"Check rack PDU and power cables for {root_device}",
                    "Verify local UPS battery status",
                    "Inspect local Ethernet uplink connection"
                ]
            return cause, recs

        # Link Down
        if event_type == EventType.LINK_DOWN:
            cause = f"Physical link failure / fiber cut on uplink connected to {root_device}"
            recs = [
                f"Check physical cable connection on {root_device}",
                "Inspect SFP transceiver light levels (Rx/Tx power)",
                "Verify interface admin status (`show interface`)",
                "Perform OTDR fiber line test if long-haul fiber"
            ]
            return cause, recs

        # Performance Degradation (Latency / Packet Loss)
        if event_type in (EventType.HIGH_LATENCY, EventType.PACKET_LOSS):
            cause = f"Network congestion, buffer exhaustion, or Spanning Tree (STP) topology recalculation at {root_device}"
            recs = [
                f"Check CPU and memory utilization on {root_device}",
                "Inspect interface bandwidth utilization and drop counters",
                "Check for broadcast storms or STP topology change notifications (TCNs)",
                "Verify QoS queue configurations and shaping policies"
            ]
            return cause, recs

        # Generic fallback
        cause = f"Unclassified fault event '{event_type.value}' on {root_device}"
        recs = [
            f"Review detailed syslog logs for device {root_device}",
            "Check recent configuration changes on the network",
            "Perform manual diagnostic ping/traceroute"
        ]
        return cause, recs
