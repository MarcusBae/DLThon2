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

    # Windows 맑은 고딕 등 한글 폰트 지원
    import platform
    if platform.system() == 'Windows':
        plt.rc('font', family='Malgun Gothic')
    plt.rcParams['axes.unicode_minus'] = False

    G = nx.node_link_graph(graph_data)
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # 좌측 상단 -> 우측 하단 대각선 흐름(계층적 위상 정렬) 적용
    pos = {}
    try:
        layers = list(nx.topological_generations(G))
        for layer_idx, nodes in enumerate(layers):
            layer_size = len(nodes)
            for i, node in enumerate(nodes):
                # 대각선 기준(x증가, y감소)에서 같은 계층 노드들을 대각선 직교축으로 분산
                offset_x = (i - (layer_size - 1) / 2) * 0.5
                offset_y = (i - (layer_size - 1) / 2) * 0.5
                x = layer_idx + offset_x
                y = -layer_idx + offset_y
                pos[node] = (x, y)
    except Exception:
        # 사이클이 존재하거나 위상정렬 실패 시 기본 spring_layout 폴백
        pos = nx.spring_layout(G)
    
    # Draw nodes and labels
    nx.draw(G, pos, with_labels=True, node_color='#E8F0FE', 
            node_size=2800, font_size=10, font_weight='bold', 
            arrows=True, arrowsize=20, ax=ax,
            edgecolors='#1A73E8', linewidths=2.0)
    
    # Draw edge labels
    edge_labels = nx.get_edge_attributes(G, 'description')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=9, font_family='Malgun Gothic', ax=ax)
    
    plt.margins(0.2)
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
