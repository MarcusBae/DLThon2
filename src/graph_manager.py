# graph_manager.py
"""Manage narrative DAG using NetworkX."""

import networkx as nx
from src.data_loader import load_theory

class NarrativeGraphManager:
    def __init__(self):
        self.graph = nx.DiGraph()
        self.theory_data = load_theory()

    def add_milestone(self, node_id: str, content: str = "", metadata: dict = None):
        """Adds a narrative node to the graph."""
        self.graph.add_node(node_id, content=content, metadata=metadata or {})

    def add_causality(self, from_node: str, to_node: str, transition_desc: str = ""):
        """Adds a causal link between two nodes."""
        self.graph.add_edge(from_node, to_node, description=transition_desc)

    def is_valid_dag(self):
        """Checks if the current graph is a valid Directed Acyclic Graph."""
        return nx.is_directed_acyclic_graph(self.graph)

    def get_plot_holes(self):
        """identifies nodes that are not reachable or lead to dead ends (placeholder)."""
        # A real implementation would check connectivity and terminal states
        return list(nx.isolates(self.graph))

    def get_graph_data(self):
        """Returns the graph in a format suitable for visualization or export."""
        return nx.node_link_data(self.graph)

if __name__ == "__main__":
    manager = NarrativeGraphManager()
    manager.add_milestone("Start", "The hero is born.")
    manager.add_milestone("Call", "A message arrives.")
    manager.add_causality("Start", "Call")
    print("Is Valid DAG:", manager.is_valid_dag())
    print("Graph Data:", manager.get_graph_data())
