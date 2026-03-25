# mapper_agent.py
"""Maps user input to structural units (Propp/Vogler)."""

from src.data_loader import load_theory

class MapperAgent:
    def __init__(self, theory_type="THEORY_PROPP_VOGLER_HYBRID"):
        self.theory_data = load_theory()
        self.theory_type = theory_type
        self.nodes = []
        for theory in self.theory_data.get("plot_theories", []):
            if theory.get("theory_id") == theory_type:
                self.nodes = theory.get("milestones", [])
                break

    def map_input_to_node(self, user_idea: str) -> str:
        """Finds the best matching theoretical node for a user's idea (Placeholder)."""
        # In a real implementation, this would use semantic search or LLM classification
        # For now, if the input contains 'start', return the first node if available
        if self.nodes:
            if "start" in user_idea.lower() or "once" in user_idea.lower():
                return self.nodes[0]["milestone_id"]
            return self.nodes[0]["milestone_id"] # Default to first node
        return ""

if __name__ == "__main__":
    mapper = MapperAgent(theory_type="THEORY_4CUT_COMIC")
    print("Mapped 'Once upon a time':", mapper.map_input_to_node("Once upon a time"))
