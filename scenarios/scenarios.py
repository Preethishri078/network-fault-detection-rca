import time
import random
import logging
from datetime import datetime
from typing import List, Set
from src.models import RawEvent, EventType
from src.topology import NetworkTopology
from src.ingest import EventQueue

logger = logging.getLogger("nms.scenarios")


class ScenarioInjector:
    """
    Fault Scenario Injector for Network Topology testing.
    Emulates realistic network failure patterns for evaluation & unit testing.
    """
    def __init__(self, topology: NetworkTopology, event_queue: EventQueue):
        self.topology = topology
        self.queue = event_queue

    def inject_core_outage(self, core_node: str = "Cisco-Nexus9K-Core1") -> List[RawEvent]:
        """
        Scenario 1: Core router power outage.
        Cisco-Nexus9K-Core1 fails. Single-homed downstream devices lose connectivity.
        Dual-homed switches (Arista-7050X-DistA) remain UP via backup Core2.
        """
        logger.info(f"Injecting Core Outage Scenario on {core_node}")
        events: List[RawEvent] = []
        now = datetime.now()

        # Primary root failure
        root_evt = RawEvent(
            timestamp=now,
            source_device=core_node,
            event_type=EventType.NODE_UNREACHABLE,
            details={"cause": "PSU Primary Feed Outage"}
        )
        events.append(root_evt)

        # Isolated nodes without path to remaining core routers
        other_cores = [n for n, dev in self.topology.devices.items() if dev.type == "CORE" and n != core_node]
        g_temp = self.topology.graph.copy()
        g_temp.remove_node(core_node)

        for node_id in self.topology.devices:
            if node_id == core_node:
                continue
            
            reachable = False
            for oc in other_cores:
                import networkx as nx
                if nx.has_path(g_temp, oc, node_id):
                    reachable = True
                    break
            
            if not reachable:
                evt = RawEvent(
                    timestamp=now,
                    source_device=node_id,
                    event_type=EventType.NODE_UNREACHABLE,
                    details={"cause": "Upstream Core Outage"}
                )
                events.append(evt)

        for e in events:
            self.queue.push(e)
        return events

    def inject_leaf_failure(self, leaf_node: str = "Juniper-EX2300-Acc1") -> List[RawEvent]:
        """Scenario 2: Access switch failure -> isolated subtree failure."""
        logger.info(f"Injecting Leaf Failure on {leaf_node}")
        events: List[RawEvent] = []
        now = datetime.now()

        root_evt = RawEvent(
            timestamp=now,
            source_device=leaf_node,
            event_type=EventType.NODE_UNREACHABLE,
            details={"cause": "ASIC Failure"}
        )
        events.append(root_evt)

        for d in self.topology.descendants(leaf_node):
            evt = RawEvent(
                timestamp=now,
                source_device=d,
                event_type=EventType.NODE_UNREACHABLE,
                details={"cause": "Uplink Down"}
            )
            events.append(evt)

        for e in events:
            self.queue.push(e)
        return events

    def inject_duplicate_storm(self, target_node: str = "Juniper-EX2300-Acc2", count: int = 100) -> List[RawEvent]:
        """Scenario 3: High-frequency alert storm -> 100 duplicate alarms."""
        logger.info(f"Injecting Duplicate Storm ({count} events) on {target_node}")
        events: List[RawEvent] = []
        now = datetime.now()

        for _ in range(count):
            evt = RawEvent(
                timestamp=now,
                source_device=target_node,
                event_type=EventType.NODE_UNREACHABLE,
                details={"cause": "SNMP Timeout Burst"}
            )
            events.append(evt)
            self.queue.push(evt)
        return events

    def inject_redundant_path_fail(self) -> List[RawEvent]:
        """Scenario 4: High Availability dual-homed protection test."""
        return self.inject_core_outage("Cisco-Nexus9K-Core1")

    def inject_double_fault(self) -> List[RawEvent]:
        """Scenario 5: Two simultaneous independent faults (Core2 & Acc3)."""
        logger.info("Injecting Simultaneous Double Fault Scenario")
        events: List[RawEvent] = []
        now = datetime.now()

        # Fault 1: Core2
        events.append(RawEvent(
            timestamp=now,
            source_device="Cisco-Nexus9K-Core2",
            event_type=EventType.NODE_UNREACHABLE,
            details={"fault_id": 1}
        ))
        for d in ["Arista-7050X-DistC", "Juniper-EX2300-Acc4", "Dell-PowerEdge-Srv07", "Dell-PowerEdge-Srv08"]:
            events.append(RawEvent(
                timestamp=now,
                source_device=d,
                event_type=EventType.NODE_UNREACHABLE,
                details={"fault_id": 1}
            ))

        # Fault 2: Acc3 (independent)
        events.append(RawEvent(
            timestamp=now,
            source_device="Juniper-EX2300-Acc3",
            event_type=EventType.NODE_UNREACHABLE,
            details={"fault_id": 2}
        ))
        for d in ["Dell-PowerEdge-Srv05", "Dell-PowerEdge-Srv06"]:
            events.append(RawEvent(
                timestamp=now,
                source_device=d,
                event_type=EventType.NODE_UNREACHABLE,
                details={"fault_id": 2}
            ))

        for e in events:
            self.queue.push(e)
        return events

    def inject_silent_parent(self) -> List[RawEvent]:
        """
        Scenario 6: Children Acc1 and Acc2 alarm, but parent DistA emits NO alarm (monitoring gap).
        RCA infers DistA as INFERRED_ROOT using Lowest Common Ancestor (LCA).
        """
        logger.info("Injecting Silent Parent Monitoring Gap Scenario")
        events: List[RawEvent] = []
        now = datetime.now()

        # Acc1 and children
        events.append(RawEvent(timestamp=now, source_device="Juniper-EX2300-Acc1", event_type=EventType.NODE_UNREACHABLE))
        events.append(RawEvent(timestamp=now, source_device="Dell-PowerEdge-Srv01", event_type=EventType.NODE_UNREACHABLE))
        events.append(RawEvent(timestamp=now, source_device="Dell-PowerEdge-Srv02", event_type=EventType.NODE_UNREACHABLE))

        # Acc2 and children
        events.append(RawEvent(timestamp=now, source_device="Juniper-EX2300-Acc2", event_type=EventType.NODE_UNREACHABLE))
        events.append(RawEvent(timestamp=now, source_device="Dell-PowerEdge-Srv03", event_type=EventType.NODE_UNREACHABLE))
        events.append(RawEvent(timestamp=now, source_device="Dell-PowerEdge-Srv04", event_type=EventType.NODE_UNREACHABLE))

        for e in events:
            self.queue.push(e)
        return events

    def inject_flapping_link(self, target_node: str = "Arista-7050X-DistB", flap_count: int = 10) -> List[RawEvent]:
        """Scenario 7: Flapping link -> repeated LINK_DOWN/LINK_UP events."""
        logger.info(f"Injecting Flapping Link Scenario on {target_node}")
        events: List[RawEvent] = []
        now = datetime.now()

        for i in range(flap_count):
            e_down = RawEvent(timestamp=now, source_device=target_node, event_type=EventType.LINK_DOWN, details={"port": "Ethernet1/1"})
            e_up = RawEvent(timestamp=now, source_device=target_node, event_type=EventType.LINK_UP, details={"port": "Ethernet1/1"})
            events.extend([e_down, e_up])
            self.queue.push(e_down)
            self.queue.push(e_up)

        return events

    def inject_recovery(self, nodes: List[str]) -> List[RawEvent]:
        """Scenario 8: Recovery -> clear active alarms."""
        logger.info(f"Injecting Recovery Events for {len(nodes)} nodes")
        events: List[RawEvent] = []
        now = datetime.now()

        for node in nodes:
            evt = RawEvent(
                timestamp=now,
                source_device=node,
                event_type=EventType.NODE_REACHABLE,
                details={"status": "Restored"}
            )
            events.append(evt)
            self.queue.push(evt)
        return events
