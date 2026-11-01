import pytest
from pathlib import Path
from src.pipeline import Pipeline
from src.models import AlarmRole, Severity

BASE_DIR = Path(__file__).resolve().parent.parent
TOPOLOGY_FILE = BASE_DIR / "data" / "topology.json"
RULES_FILE = BASE_DIR / "data" / "rules.yaml"


@pytest.fixture
def pipeline():
    return Pipeline(TOPOLOGY_FILE, RULES_FILE)


def test_core_outage_correlation(pipeline):
    incidents = pipeline.run_scenario("core_outage")
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.root_cause_device == "Cisco-Nexus9K-Core1"
    assert inc.primary_alarm.role in (AlarmRole.PRIMARY_FAULT, AlarmRole.STANDALONE)
    assert len(inc.secondary_alarms) == 5
    assert inc.severity == Severity.CRITICAL


def test_leaf_failure_correlation(pipeline):
    incidents = pipeline.run_scenario("leaf_failure")
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.root_cause_device == "Juniper-EX2300-Acc1"
    assert len(inc.secondary_alarms) == 2  # Srv01 and Srv02


def test_duplicate_storm_reduction(pipeline):
    incidents = pipeline.run_scenario("duplicate_storm")
    metrics = pipeline.get_metrics()
    assert metrics["raw_events"] == 100
    assert metrics["unique_alarms"] == 1
    assert metrics["noise_reduction_pct"] == 99.0
    assert len(incidents) == 1
    assert incidents[0].root_cause_device == "Juniper-EX2300-Acc2"


def test_redundant_path_behavior(pipeline):
    # Core1 down, but DistA and Acc5 remain UP via Core2 / DistB
    incidents = pipeline.run_scenario("redundant_path")
    assert len(incidents) == 1
    inc = incidents[0]
    secondary_devices = [a.source_device for a in inc.secondary_alarms]
    assert "Arista-7050X-DistA" not in secondary_devices
    assert "Juniper-EX2300-Acc5" not in secondary_devices


def test_simultaneous_double_fault(pipeline):
    incidents = pipeline.run_scenario("double_fault")
    assert len(incidents) == 2
    roots = {inc.root_cause_device for inc in incidents}
    assert "Cisco-Nexus9K-Core2" in roots
    assert "Juniper-EX2300-Acc3" in roots


def test_silent_parent_inference(pipeline):
    incidents = pipeline.run_scenario("silent_parent")
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.root_cause_device == "Arista-7050X-DistA"
    assert inc.inferred_root is True


def test_recovery_clears_alarms(pipeline):
    pipeline.run_scenario("core_outage")
    assert len(pipeline.incidents) == 1

    # Inject recovery
    pipeline.run_scenario("recovery")
    metrics = pipeline.get_metrics()
    assert metrics["active_incidents"] == 0
