from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

@dataclass(frozen=True)
class Record:
    record_id: str
    data_type: str
    created_at: datetime
    owner_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    record_id: str
    source_system: str
    payload: Dict[str, Any] = field(default_factory=dict)
    verified_at: datetime = field(default_factory=datetime.now)

@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    data_type: str
    retention_days: int
    action: str
    owner_role: str

@dataclass(frozen=True)
class PolicyFinding:
    record_id: str
    rule_id: str
    action_recommended: str
    is_expired: bool
    evidence_ids: List[str]
    ambiguities: List[str]

@dataclass(frozen=True)
class ResurrectionPath:
    path_id: str
    source_system: str
    destination_system: str
    operation: str  # e.g., 'sync', 'import', 'backup', 'restore', 'scheduled_job'
    status: str     # 'confirmed_active', 'possible', 'inactive', 'historical', 'ambiguous'
    evidence_ids: List[str]
    upstream_dependencies: List[str] = field(default_factory=list)

class ResurrectionAnalyzer:
    def __init__(self, paths: List[ResurrectionPath]):
        self.paths = paths

    def identify_paths_for_record(self, record_id: str, evidences: List[Evidence]) -> List[ResurrectionPath]:
        relevant_evidence_ids = {e.evidence_id for e in evidences if e.record_id == record_id}
        matched_paths = []
        for path in self.paths:
            if any(ev_id in relevant_evidence_ids for ev_id in path.evidence_ids):
                matched_paths.append(path)
        return matched_paths

    def detect_cycles(self) -> List[List[str]]:
        # Simple cycle detection in dependency graph
        graph: Dict[str, List[str]] = {}
        for path in self.paths:
            graph.setdefault(path.source_system, []).append(path.destination_system)

        cycles = []
        visited: Set[str] = {}
        stack: Set[str] = {}

        def dfs(node: str, path: List[str]):
            visited[node] = True
            stack[node] = True
            path.append(node)

            for neighbor in graph.get(node, []):
                if not visited.get(neighbor, False):
                    dfs(neighbor, list(path))
                elif stack.get(neighbor, False):
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])

            stack[node] = False

        for source in graph:
            if not visited.get(source, False):
                dfs(source, [])

        return cycles

    def recommend_remediation_order(self) -> List[ResurrectionPath]:
        # Topological sort or dependency-based ordering for upstream remediation
        in_degree: Dict[str, int] = {}
        nodes: Set[str] = set()

        for path in self.paths:
            nodes.add(path.source_system)
            nodes.add(path.destination_system)
            in_degree.setdefault(path.destination_system, 0)
            in_degree.setdefault(path.source_system, 0)

        for path in self.paths:
            # destination depends on source
            in_degree[path.destination_system] += 1

        # Return paths ordered by upstream-first (source systems with lower in-degree)
        ordered_paths = sorted(self.paths, key=lambda p: in_degree.get(p.source_system, 0))
        return ordered_paths
