import logging
from datetime import datetime
from typing import List, Dict, Set, Optional
import networkx as nx
from src.models import (
    Alarm, Incident, AlarmRole, Severity, DeviceType, EventType, AlarmStatus
)
from src.topology import NetworkTopology
from src.rca_rules import RCARuleEngine

logger = logging.getLogger("nms.correlator")


class EventCorrelator:
    """
    Graph Correlation Engine.
    Decomposes induced failure subgraph G_f into weakly connected components,
    identifies root cause nodes, enforces dual-homing redundancy checks,
    and infers silent parent monitoring gaps.
    """
    def __init__(self, topology: NetworkTopology, rca_engine: Optional[RCARuleEngine] = None):
        self.topology = topology
        self.rca_engine = rca_engine or RCARuleEngine()

    def correlate(self, active_alarms: List[Alarm]) -> List[Incident]:
        """Correlate active alarms into actionable Incidents using topology traversal."""
        if not active_alarms:
            return []

        alarm_map: Dict[str, Alarm] = {a.source_device: a for a in active_alarms if a.status == AlarmStatus.ACTIVE}
        alarmed_devices: Set[str] = set(alarm_map.keys())

        if not alarmed_devices:
            return []

        # Step B: Build failure subgraph G_f
        subgraph = self.topology.graph.subgraph(alarmed_devices).copy()
        components = list(nx.weakly_connected_components(subgraph))

        logger.info(f"Correlating {len(alarmed_devices)} active alarmed devices into {len(components)} subgraph components")

        initial_incidents: List[Incident] = []
        component_roots: List[str] = []

        for component_nodes in components:
            incident, root_dev = self._process_component(component_nodes, alarm_map, alarmed_devices)
            if incident:
                initial_incidents.append(incident)
                if root_dev:
                    component_roots.append(root_dev)

        # Step F: Silent Parent Inference across components
        # NOTE: If multiple separate components exist whose root nodes share an unalarmed parent (LCA),
        # infer that parent as an INFERRED_ROOT due to a monitoring gap.
        if len(initial_incidents) > 1 and len(component_roots) > 1:
            lca = self.topology.find_lowest_common_ancestor(component_roots)
            if lca and lca not in alarmed_devices and lca in self.topology.devices:
                logger.info(f"Inferred Silent Parent root cause: {lca} for components {component_roots}")
                all_secondary: List[Alarm] = []
                all_affected: Set[str] = set(self.topology.descendants(lca) | {lca})
                
                for inc in initial_incidents:
                    all_secondary.append(inc.primary_alarm)
                    all_secondary.extend(inc.secondary_alarms)

                primary_alarm = Alarm(
                    source_device=lca,
                    event_type=EventType.NODE_UNREACHABLE,
                    severity=Severity.CRITICAL,
                    status=AlarmStatus.ACTIVE,
                    role=AlarmRole.INFERRED_ROOT
                )

                for sa in all_secondary:
                    sa.role = AlarmRole.SECONDARY_CORRELATED
                    sa.correlated_to = primary_alarm.alarm_id

                probable_cause, recommendations = self.rca_engine.evaluate(
                    root_device=lca,
                    topology=self.topology,
                    primary_alarm=primary_alarm,
                    secondary_alarms=all_secondary,
                    is_inferred=True
                )

                alarmed_desc_cnt = len(all_affected & alarmed_devices)
                total_desc_cnt = max(1, len(self.topology.descendants(lca)))
                confidence = min(85.0, (alarmed_desc_cnt / total_desc_cnt) * 75.0 + 15.0)
                start_time = min(a.first_seen for a in all_secondary)

                inferred_incident = Incident(
                    root_cause_device=lca,
                    probable_cause=probable_cause,
                    primary_alarm=primary_alarm,
                    secondary_alarms=all_secondary,
                    severity=Severity.CRITICAL,
                    confidence=round(confidence, 1),
                    recommendations=recommendations,
                    start_time=start_time,
                    inferred_root=True,
                    affected_devices=sorted(list(all_affected))
                )
                return [inferred_incident]

        return initial_incidents

    def _process_component(
        self,
        component_nodes: Set[str],
        alarm_map: Dict[str, Alarm],
        all_alarmed_devices: Set[str]
    ) -> tuple[Optional[Incident], Optional[str]]:

        # Step C: Find root candidates in component C
        roots = []
        for node in component_nodes:
            ancestors = self.topology.ancestors(node)
            if not (ancestors & component_nodes):
                roots.append(node)

        if not roots:
            roots = sorted(list(component_nodes), key=lambda n: self.topology.depth(n))

        roots.sort(key=lambda n: self.topology.depth(n))
        root_device = roots[0]

        primary_alarm = alarm_map[root_device]
        primary_alarm.role = AlarmRole.PRIMARY_FAULT if len(component_nodes) > 1 else AlarmRole.STANDALONE

        # Step D & E: Secondary correlated vs standalone redundancy checks
        root_descendants = self.topology.descendants(root_device)
        secondary_alarms: List[Alarm] = []
        affected_devices: List[str] = sorted(list(root_descendants | {root_device}))

        for node in component_nodes:
            if node == root_device:
                continue
            
            alarm = alarm_map[node]

            # NOTE: Redundancy check - a node is secondary ONLY if all of its parents are impacted.
            # If an alternate parent path remains healthy, the device alarm is treated as standalone.
            parents = self.topology.parents(node)
            if parents:
                all_parents_affected = True
                for p in parents:
                    if p not in all_alarmed_devices and p not in root_descendants and p != root_device:
                        all_parents_affected = False
                        break
                
                if all_parents_affected:
                    alarm.role = AlarmRole.SECONDARY_CORRELATED
                    alarm.correlated_to = primary_alarm.alarm_id
                    secondary_alarms.append(alarm)
                else:
                    alarm.role = AlarmRole.STANDALONE
            else:
                alarm.role = AlarmRole.SECONDARY_CORRELATED
                alarm.correlated_to = primary_alarm.alarm_id
                secondary_alarms.append(alarm)

        # Step G: Confidence score calculation
        total_descendants = len(root_descendants)
        alarmed_descendants_count = len(root_descendants & all_alarmed_devices)

        if total_descendants > 0:
            ratio = alarmed_descendants_count / total_descendants
            base_confidence = ratio * 75.0
        else:
            base_confidence = 60.0

        confidence = min(98.0, base_confidence + 23.0)

        # Step H: Remediation and probable cause lookup
        probable_cause, recommendations = self.rca_engine.evaluate(
            root_device=root_device,
            topology=self.topology,
            primary_alarm=primary_alarm,
            secondary_alarms=secondary_alarms,
            is_inferred=False
        )

        overall_severity = primary_alarm.severity
        start_time = min([a.first_seen for a in [primary_alarm] + secondary_alarms])

        incident = Incident(
            root_cause_device=root_device,
            probable_cause=probable_cause,
            primary_alarm=primary_alarm,
            secondary_alarms=secondary_alarms,
            severity=overall_severity,
            confidence=round(confidence, 1),
            recommendations=recommendations,
            start_time=start_time,
            inferred_root=False,
            affected_devices=affected_devices
        )

        return incident, root_device
