# validator_agent.py
"""Logic and causality verification agent."""

from src.constraint_solver import NarrativeConstraintSolver

class ValidatorAgent:
    def __init__(self, theory_type="propp"):
        self.solver = NarrativeConstraintSolver(theory_type=theory_type)

    def validate_transition(self, from_id: str, to_id: str) -> bool:
        """Checks if a transition between two nodes is logically consistent."""
        valid_next = self.solver.get_valid_next_ids(from_id)
        return to_id in valid_next

    def check_plot_hole(self, history: list) -> list:
        """Checks the entire history for logical gaps (Placeholder)."""
        holes = []
        for i in range(len(history) - 1):
            if not self.validate_transition(history[i], history[i+1]):
                holes.append((history[i], history[i+1]))
        return holes

if __name__ == "__main__":
    validator = ValidatorAgent(theory_type="propp")
    print("P01 -> P02 Valid?", validator.validate_transition("P01", "P02"))
    print("P01 -> P04 Valid?", validator.validate_transition("P01", "P04"))
