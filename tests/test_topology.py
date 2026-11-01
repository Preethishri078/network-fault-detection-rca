import pytest
from pathlib import Path
from src.topology import NetworkTopology, TopologyError

BASE_DIR = Path(__file__).resolve().parent.parent
TOPOLOGY_FILE = BASE_DIR / "data" / "topology.json"


def test_topology_loading():
    topology = NetworkTopology(TOPOLOGY_FILE)
    assert topology.is_dag() is True
    assert len(topology.devices) == 21
    assert "Cisco-Nexus9K-Core1" in topology.devices
    assert "Arista-7050X-DistA" in topology.devices


def test_ancestors_and_descendants():
    topology = NetworkTopology(TOPOLOGY_FILE)
    
    anc_srv = topology.ancestors("Dell-PowerEdge-Srv01")
    assert "Juniper-EX2300-Acc1" in anc_srv
    assert "Arista-7050X-DistA" in anc_srv
    assert "Cisco-Nexus9K-Core1" in anc_srv

    desc_core = topology.descendants("Cisco-Nexus9K-Core1")
    assert "Arista-7050X-DistB" in desc_core
    assert "Juniper-EX2300-Acc3" in desc_core
    assert "Dell-PowerEdge-Srv05" in desc_core


def test_depth_calculation():
    topology = NetworkTopology(TOPOLOGY_FILE)
    assert topology.depth("Cisco-Nexus9K-Core1") == 0
    assert topology.depth("Cisco-Nexus9K-Core2") == 0
    assert topology.depth("Arista-7050X-DistA") == 1
    assert topology.depth("Juniper-EX2300-Acc1") == 2
    assert topology.depth("Dell-PowerEdge-Srv01") == 3


def test_lowest_common_ancestor():
    topology = NetworkTopology(TOPOLOGY_FILE)
    lca = topology.find_lowest_common_ancestor(["Juniper-EX2300-Acc1", "Juniper-EX2300-Acc2"])
    assert lca == "Arista-7050X-DistA"


def test_cycle_rejection(tmp_path):
    cycle_json = tmp_path / "cycle.json"
    cycle_json.write_text("""{
      "nodes": [
        {"id": "A", "type": "CORE"},
        {"id": "B", "type": "DIST"}
      ],
      "edges": [["A", "B"], ["B", "A"]]
    }""")

    with pytest.raises(TopologyError):
        NetworkTopology(cycle_json)
