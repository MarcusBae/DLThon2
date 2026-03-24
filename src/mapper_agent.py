# mapper_agent.py
"""Maps user input to structural units (Propp/Vogler)."""

from src.data_loader import load_theory

class MapperAgent:
    def __init__(self, theory_type="propp"):
        self.theory_data = load_theory()
        self.nodes = self.theory_data.get(f"{theory_type}_functions" if theory_type == "propp" else f"{theory_type}_stages", [])

    def map_input_to_node(self, user_idea: str) -> str:
        """Finds the best matching theoretical node for a user's idea (Placeholder)."""
        # In a real implementation, this would use semantic search or LLM classification
        # For now, if the input contains 'start', return P01
        if "start" in user_idea.lower() or "once" in user_idea.lower():
            return "P01"
        return "P01" # Default to start

if __name__ == "__main__":
    mapper = MapperAgent(theory_type="propp")
    print("Mapped 'Once upon a time':", mapper.map_input_to_node("Once upon a time"))
