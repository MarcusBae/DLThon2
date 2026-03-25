# constraint_solver.py
"""Google OR-Tools (CP-SAT)를 사용한 논리 제약 엔진."""

from ortools.sat.python import cp_model
from src.data_loader import load_theory

class NarrativeConstraintSolver:
    """
    서사 생성을 위한 논리 기반 접근 방식을 제공합니다.
    Google OR-Tools(CP-SAT)를 사용하여 미리 정의된 전이 규칙 및 제약 조건에 따라
    프로프(Propp)의 서사 기능 또는 보글러(Vogler)의 서사 단계의 유효한 시퀀스를 찾습니다.
    """
    def __init__(self, theory_type="THEORY_PROPP_VOGLER_HYBRID"):
        self.theory_data = load_theory()
        self.theory_type = theory_type
        self.nodes = []
        for theory in self.theory_data.get("plot_theories", []):
            if theory.get("theory_id") == theory_type:
                self.nodes = theory.get("milestones", [])
                break
        self.id_to_index = {node["milestone_id"]: i for i, node in enumerate(self.nodes)}
        self.index_to_id = {i: node["milestone_id"] for i, node in enumerate(self.nodes)}

    def get_valid_next_ids(self, current_node_id: str):
        """이론에 따라 유효한 다음 노드 ID 목록을 반환합니다."""
        if not current_node_id:
            # 현재 노드가 없으면 첫 번째 노드부터 시작
            if self.nodes:
                return [self.nodes[0]["milestone_id"]]
            return []
        
        current_idx = self.id_to_index.get(current_node_id)
        if current_idx is None or current_idx + 1 >= len(self.nodes):
            return []
        
        return [self.nodes[current_idx + 1]["milestone_id"]]

    def validate_transition(self, from_id: str, to_id: str) -> bool:
        """두 노드 간의 전이가 논리적으로 유효한지 확인합니다."""
        valid_next = self.get_valid_next_ids(from_id)
        return to_id in valid_next

    def solve_sequence(self, length=5):
        """Example: Use CP-SAT to find a valid sequence of a certain length."""
        model = cp_model.CpModel()
        num_nodes = len(self.nodes)
        
        # Variables: state[i] is the index of the node at step i
        steps = [model.NewIntVar(0, num_nodes - 1, f'step_{i}') for i in range(length)]
        
        # Constraints: 1. Start with a valid initial node
        start_ids = self.get_valid_next_ids(None)
        start_indices = [self.id_to_index[sid] for sid in start_ids if sid in self.id_to_index]
        if start_indices:
            start_bools = []
            for idx in start_indices:
                sb = model.NewBoolVar(f'start_at_{idx}')
                model.Add(steps[0] == idx).OnlyEnforceIf(sb)
                start_bools.append(sb)
            model.Add(sum(start_bools) == 1)

        # Constraints: 2. Transition rules
        for i in range(length - 1):
            for current_idx in range(num_nodes):
                current_id = self.index_to_id[current_idx]
                valid_next_ids = self.get_valid_next_ids(current_id)
                valid_next_indices = [self.id_to_index[nid] for nid in valid_next_ids if nid in self.id_to_index]
                
                if not valid_next_indices:
                    # If no next, this node can't be at step i
                    model.Add(steps[i] != current_idx)
                b = model.NewBoolVar(f'at_{i}_{current_idx}')
                model.Add(steps[i] == current_idx).OnlyEnforceIf(b)
                model.Add(steps[i] != current_idx).OnlyEnforceIf(b.Not())

                if not valid_next_indices:
                    # If no next, this node can't be at step i
                    model.Add(b == 0)
                else:
                    # If steps[i] == current_idx, then steps[i+1] must be one of valid_next_indices
                    next_bools = []
                    for next_idx in valid_next_indices:
                        next_b = model.NewBoolVar(f'step_{i+1}_is_{next_idx}_for_{current_idx}')
                        model.Add(steps[i+1] == next_idx).OnlyEnforceIf(next_b)
                        next_bools.append(next_b)
                    model.Add(sum(next_bools) == 1).OnlyEnforceIf(b)

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            return [self.index_to_id[solver.Value(s)] for s in steps]
        return []

if __name__ == "__main__":
    solver = NarrativeConstraintSolver(theory_type="THEORY_4CUT_COMIC")
    print("Valid Next for 4CUT_01_INTRO:", solver.get_valid_next_ids("4CUT_01_INTRO"))
    print("Found Sequence:", solver.solve_sequence(length=4))
