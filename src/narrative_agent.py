# narrative_agent.py
"""LangGraph implementation for narrative node generation."""

from typing import TypedDict, List, Annotated
import operator
from langgraph.graph import StateGraph, END
from src.constraint_solver import NarrativeConstraintSolver
from src.graph_manager import NarrativeGraphManager

class NarrativeState(TypedDict):
    current_node_id: str
    history: Annotated[List[str], operator.add]
    world_constants: dict
    characters: List[dict]
    last_generated_content: str
    is_valid: bool
    plot_graph_data: dict
    theory_type: str

def planner_node(state: NarrativeState):
    """Suggests the next narrative node using the constraint engine."""
    solver = NarrativeConstraintSolver(theory_type=state.get("theory_type", "propp"))
    valid_next = solver.get_valid_next_ids(state["current_node_id"])
    
    # Simple strategy: pick the first one for now
    next_node_id = valid_next[0] if valid_next else None
    
    return {
        "current_node_id": next_node_id,
        "history": [next_node_id] if next_node_id else []
    }

def generator_node(state: NarrativeState):
    """Generates the story content for the current node (Placeholder)."""
    # In a real implementation, this would call an LLM
    content = f"Generating content for node {state['current_node_id']}..."
    return {"last_generated_content": content}

def validator_node(state: NarrativeState):
    """Verifies the content and the transition."""
    # Placeholder: check if history is empty
    is_valid = bool(state["current_node_id"])
    return {"is_valid": is_valid}

def build_narrative_graph():
    builder = StateGraph(NarrativeState)
    builder.add_node("planner", planner_node)
    builder.add_node("generator", generator_node)
    builder.add_node("validator", validator_node)

    builder.set_entry_point("planner")
    builder.add_edge("planner", "generator")
    builder.add_edge("generator", "validator")
    builder.add_edge("validator", END)

    return builder.compile()

if __name__ == "__main__":
    graph = build_narrative_graph()
    initial_state = {
        "current_node_id": None,
        "history": [],
        "world_constants": {},
        "characters": [],
        "theory_type": "propp"
    }
    result = graph.invoke(initial_state)
    print("Graph execution result:", result)
