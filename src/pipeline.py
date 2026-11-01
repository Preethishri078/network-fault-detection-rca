import argparse
import logging
from pathlib import Path
from typing import List, Dict, Optional, Union, Any
from src.topology import NetworkTopology
from src.classifier import EventClassifier
from src.dedup import AlarmDeduplicator
from src.correlator import EventCorrelator
from src.ingest import EventQueue, load_events_from_csv
from src.models import RawEvent, Alarm, Incident
from scenarios.scenarios import ScenarioInjector

# Configure standard Python logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("nms.pipeline")


class Pipeline:
    """
    Main Orchestration Pipeline for NMS Fault Detection & Root Cause Analysis.
    Wires EventQueue -> Classifier -> Deduplicator -> Correlator -> Incident Store.
    """
    def __init__(
        self,
        topology_path: Optional[Union[str, Path]] = None,
        rules_path: Optional[Union[str, Path]] = None
    ):
        base_dir = Path(__file__).resolve().parent.parent
        t_path = topology_path or (base_dir / "data" / "topology.json")
        r_path = rules_path or (base_dir / "data" / "rules.yaml")

        self.topology = NetworkTopology(t_path)
        self.classifier = EventClassifier(r_path, self.topology)
        self.deduplicator = AlarmDeduplicator()
        self.correlator = EventCorrelator(self.topology)
        self.event_queue = EventQueue()
        self.injector = ScenarioInjector(self.topology, self.event_queue)

        self.incidents: List[Incident] = []
        logger.info("NMS RCA Pipeline initialized successfully")

    def run_cycle(self) -> List[Incident]:
        """
        Execute one processing cycle:
        1. Pop raw events from queue
        2. Classify raw events into Alarms
        3. Deduplicate active alarms
        4. Correlate active alarms into actionable Incidents
        """
        raw_events = self.event_queue.pop_all()

        for raw_event in raw_events:
            alarm = self.classifier.classify(raw_event)
            if alarm:
                self.deduplicator.process_alarm(alarm)

        active_alarms = self.deduplicator.get_active_alarms()
        self.incidents = self.correlator.correlate(active_alarms)
        return self.incidents

    def run_csv_file(self, csv_path: Union[str, Path]) -> List[Incident]:
        """Ingest events from an offline CSV log file and run processing cycle."""
        events = load_events_from_csv(csv_path)
        for e in events:
            self.event_queue.push(e)
        return self.run_cycle()

    def run_scenario(self, scenario_name: str) -> List[Incident]:
        """Run a predefined fault injection scenario by name."""
        scenario_map = {
            "core_outage": self.injector.inject_core_outage,
            "leaf_failure": self.injector.inject_leaf_failure,
            "duplicate_storm": self.injector.inject_duplicate_storm,
            "redundant_path": self.injector.inject_redundant_path_fail,
            "double_fault": self.injector.inject_double_fault,
            "silent_parent": self.injector.inject_silent_parent,
            "flapping_link": self.injector.inject_flapping_link,
            "recovery": lambda: self.injector.inject_recovery(list(self.topology.devices.keys()))
        }

        if scenario_name not in scenario_map:
            raise ValueError(f"Unknown scenario '{scenario_name}'. Available: {list(scenario_map.keys())}")

        scenario_map[scenario_name]()
        return self.run_cycle()

    def get_metrics(self) -> Dict[str, Any]:
        raw_cnt = self.deduplicator.raw_events_count
        uniq_cnt = self.deduplicator.unique_alarms_count
        inc_cnt = len(self.incidents)
        noise_red = self.deduplicator.noise_reduction_pct

        return {
            "raw_events": raw_cnt,
            "unique_alarms": uniq_cnt,
            "active_incidents": inc_cnt,
            "noise_reduction_pct": noise_red
        }


def main():
    parser = argparse.ArgumentParser(description="Network Fault Detection & RCA Pipeline CLI Interface")
    parser.add_argument("--scenario", type=str, default="core_outage", help="Fault scenario to inject and run")
    parser.add_argument("--log-file", type=str, default=None, help="Path to offline CSV log file to ingest")
    args = parser.parse_args()

    pipeline = Pipeline()
    
    if args.log_file:
        print(f"\nIngesting offline log file: {args.log_file}")
        incidents = pipeline.run_csv_file(args.log_file)
    else:
        incidents = pipeline.run_scenario(args.scenario)

    metrics = pipeline.get_metrics()

    print("\n" + "=" * 60)
    print(f" PIPELINE PROCESSING RUN: '{args.log_file or args.scenario}'")
    print("=" * 60)
    print(f" Raw Events Ingested : {metrics['raw_events']}")
    print(f" Unique Alarms       : {metrics['unique_alarms']}")
    print(f" Active Incidents    : {metrics['active_incidents']}")
    print(f" Noise Reduction %   : {metrics['noise_reduction_pct']:.2f}%")
    print("=" * 60 + "\n")

    for idx, inc in enumerate(incidents, 1):
        print(f"Incident #{idx}:")
        print(f"  Root Cause Device : {inc.root_cause_device} ({'Inferred' if inc.inferred_root else 'Direct'})")
        print(f"  Severity          : {inc.severity.value}")
        print(f"  Confidence        : {inc.confidence}%")
        print(f"  Probable Cause    : {inc.probable_cause}")
        print(f"  Primary Alarm     : {inc.primary_alarm.event_type.value} on {inc.primary_alarm.source_device}")
        print(f"  Secondary Alarms  : {len(inc.secondary_alarms)} suppressed alarms")
        print(f"  Affected Devices  : {len(inc.affected_devices)} devices")
        print("  Recommendations   :")
        for rec in inc.recommendations:
            print(f"   - {rec}")
        print("-" * 60)


if __name__ == "__main__":
    main()
