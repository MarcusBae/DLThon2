# constraint_solver.py
"""Logic-Constraint Engine using Google OR-Tools (CP-SAT)."""

from ortools.sat.python import cp_model
from src.data_loader import load_theory

class NarrativeConstraintSolver:
    def __init__(self, theory_type="propp"):
        self.theory_data = load_theory()
        self.theory_type = theory_type
        self.nodes = self.theory_data.get(f"{theory_type}_functions" if theory_type == "propp" else f"{theory_type}_stages", [])
        self.id_to_index = {node["id"]: i for i, node in enumerate(self.nodes)}
        self.index_to_id = {i: node["id"] for i, node in enumerate(self.nodes)}

    def get_valid_next_ids(self, current_node_id: str):
        """Returns a list of valid next node IDs based on the theory."""
        if not current_node_id:
            # If no current node, start with the first ones
            return [n["id"] for n in self.nodes if n["id"].endswith("01")]
        
        current_node = next((n for n in self.nodes if n["id"] == current_node_id), None)
        if not current_node:
            return []
        
        return current_node.get("allowed_next", [])

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
    solver = NarrativeConstraintSolver(theory_type="propp")
    print("Valid Next for P01:", solver.get_valid_next_ids("P01"))
    print("Found Sequence:", solver.solve_sequence(length=4))
