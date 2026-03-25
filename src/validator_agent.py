# validator_agent.py
"""Logic and causality verification agent."""

from src.constraint_solver import NarrativeConstraintSolver

class ValidatorAgent:
    def __init__(self, theory_type="THEORY_PROPP_VOGLER_HYBRID"):
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
    validator = ValidatorAgent(theory_type="THEORY_4CUT_COMIC")
    print("4CUT_01_INTRO -> 4CUT_02_DEVELOPMENT Valid?", validator.validate_transition("4CUT_01_INTRO", "4CUT_02_DEVELOPMENT"))
    print("4CUT_01_INTRO -> 4CUT_04_CONCLUSION Valid?", validator.validate_transition("4CUT_01_INTRO", "4CUT_04_CONCLUSION"))
