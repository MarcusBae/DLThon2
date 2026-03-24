# visualizer.py
"""Visualization utilities for the narrative graph."""

import networkx as nx
import matplotlib.pyplot as plt
import streamlit as st

def draw_narrative_graph(graph_data: dict):
    """Draws a NetworkX graph using Matplotlib and displays it in Streamlit."""
    if not graph_data or not graph_data.get("nodes"):
        st.info("No plot graph to display yet.")
        return

    G = nx.node_link_graph(graph_data)
    
    fig, ax = plt.subplots(figsize=(10, 6))
    pos = nx.spring_layout(G)  # spring layout for better visualization
    
    # Draw nodes and labels
    nx.draw(G, pos, with_labels=True, node_color='lightblue', 
            node_size=2000, font_size=10, font_weight='bold', 
            arrows=True, arrowsize=20, ax=ax)
    
    # Draw edge labels
    edge_labels = nx.get_edge_attributes(G, 'description')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=8, ax=ax)
    
    st.pyplot(fig)

if __name__ == "__main__":
    # Test visualization
    test_data = {
        "nodes": [{"id": "Start"}, {"id": "Middle"}, {"id": "End"}],
        "links": [
            {"source": "Start", "target": "Middle", "description": "Then"},
            {"source": "Middle", "target": "End", "description": "Finally"}
        ],
        "multigraph": False,
        "directed": True
    }
    # This won't work without a streamlit context
    # draw_narrative_graph(test_data)
