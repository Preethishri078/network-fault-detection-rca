import json
import logging
from pathlib import Path
from typing import Set, Dict, List, Optional, Union
import networkx as nx
from src.models import Device, DeviceType

logger = logging.getLogger("nms.topology")


class TopologyError(Exception):
    """Custom exception for network topology DAG validation errors."""
    pass


class NetworkTopology:
    """
    Graph Topology Manager using NetworkX DiGraph.
    Represents parent-to-child network dependencies (Core -> Dist -> Access -> Server).
    """
    def __init__(self, json_path: Optional[Union[str, Path]] = None):
        self.graph: nx.DiGraph = nx.DiGraph()
        self.devices: Dict[str, Device] = {}
        if json_path:
            self.load_from_json(json_path)

    def load_from_json(self, json_path: Union[str, Path]) -> None:
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"Topology JSON file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.graph.clear()
        self.devices.clear()

        # Add graph nodes
        for node_data in data.get("nodes", []):
            device = Device(
                id=node_data["id"],
                type=DeviceType(node_data["type"]),
                ip=node_data.get("ip", "0.0.0.0"),
                location=node_data.get("location", "Unknown Location"),
                role_description=node_data.get("role_description")
            )
            self.devices[device.id] = device
            self.graph.add_node(device.id, device=device, type=device.type)

        # Add graph directed edges (parent -> child)
        for parent, child in data.get("edges", []):
            if parent not in self.devices or child not in self.devices:
                raise TopologyError(f"Edge ({parent} -> {child}) references unknown device.")
            self.graph.add_edge(parent, child)

        # Validate DAG structure to prevent circular dependencies
        if not self.is_dag():
            raise TopologyError("Topology contains graph cycles! Must be a Directed Acyclic Graph (DAG).")

        logger.info(f"Loaded valid DAG NetworkTopology: {len(self.devices)} nodes, {self.graph.number_of_edges()} edges")

    def is_dag(self) -> bool:
        return nx.is_directed_acyclic_graph(self.graph)

    def get_device(self, node_id: str) -> Optional[Device]:
        return self.devices.get(node_id)

    def ancestors(self, node_id: str) -> Set[str]:
        if node_id not in self.graph:
            return set()
        return nx.ancestors(self.graph, node_id)

    def descendants(self, node_id: str) -> Set[str]:
        if node_id not in self.graph:
            return set()
        return nx.descendants(self.graph, node_id)

    def parents(self, node_id: str) -> Set[str]:
        if node_id not in self.graph:
            return set()
        return set(self.graph.predecessors(node_id))

    def children(self, node_id: str) -> Set[str]:
        if node_id not in self.graph:
            return set()
        return set(self.graph.successors(node_id))

    def depth(self, node_id: str) -> int:
        """Distance from nearest CORE node. Core nodes have depth 0."""
        if node_id not in self.graph:
            return -1
        
        core_nodes = [nid for nid, dev in self.devices.items() if dev.type == DeviceType.CORE]
        if node_id in core_nodes:
            return 0

        min_depth = float("inf")
        for core in core_nodes:
            if nx.has_path(self.graph, core, node_id):
                path_len = nx.shortest_path_length(self.graph, core, node_id)
                if path_len < min_depth:
                    min_depth = path_len

        return int(min_depth) if min_depth != float("inf") else -1

    def find_lowest_common_ancestor(self, node_ids: List[str]) -> Optional[str]:
        """
        Find deepest common ancestor for a list of node IDs.
        Used for Silent Parent / Unmonitored Switch failure inference.
        """
        if not node_ids:
            return None
        if len(node_ids) == 1:
            parents = self.parents(node_ids[0])
            return list(parents)[0] if parents else node_ids[0]

        ancestor_sets = []
        for nid in node_ids:
            if nid in self.graph:
                anc = self.ancestors(nid) | {nid}
                ancestor_sets.append(anc)
            else:
                return None

        common_ancestors = set.intersection(*ancestor_sets)
        if not common_ancestors:
            return None

        # Pick ancestor with maximum topological depth
        deepest_ancestor = max(common_ancestors, key=lambda n: self.depth(n))
        return deepest_ancestor
