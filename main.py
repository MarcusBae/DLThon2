import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

# main.py
"""N.L (Narrative-Logic) Engine Streamlit Dashboard."""

import streamlit as st
import os
from dotenv import load_dotenv

from src.narrative_agent import build_narrative_graph
from src.visualizer import draw_narrative_graph
from src.graph_manager import NarrativeGraphManager
from src.mapper_agent import MapperAgent

load_dotenv()

st.set_page_config(page_title="N.L Story Engine", layout="wide")

st.title("🧙‍♂️ Narrative-Logic (N.L) Engine")
st.markdown("""
독점론적 서사 엔진을 통해 논리적 결함 없는 완벽한 스토리 블루프린트를 설계하세요.
""")

# Sidebar settings
with st.sidebar:
    st.header("⚙️ Settings")
    theory_type = st.selectbox("Narrative Theory", ["propp", "vogler"], index=0)
    st.divider()
    st.subheader("Writer's Palette")
    genre = st.text_input("Genre", "Fantasy")
    world_rules = st.text_area("World Rules", "Magic is rare, Dragons are extinct.")

# Main area
col1, col2 = st.columns([1, 1])

with col1:
    st.header("✍️ Initial Idea")
    user_idea = st.text_area("당신의 이야기를 시작할 키워드나 시나리오를 입력하세요.", "Once upon a time in a far away kingdom...")
    
    if st.button("Generate First Milestone"):
        with st.spinner("Mapping to Narrative Nodes..."):
            # 1. Map input to node
            mapper = MapperAgent(theory_type=theory_type)
            start_node_id = mapper.map_input_to_node(user_idea)
            
            # 2. Setup initial state
            initial_state = {
                "current_node_id": None, # Start from None to let planner decide first node if needed
                "history": [],
                "world_constants": {"genre": genre, "rules": world_rules},
                "characters": [],
                "theory_type": theory_type
            }
            
            # 3. Compile and Run LangGraph
            workflow = build_narrative_graph()
            result = workflow.invoke(initial_state)
            
            st.session_state.current_result = result
            st.success(f"Milestone '{result['current_node_id']}' generated!")

    if 'current_result' in st.session_state:
        res = st.session_state.current_result
        st.subheader(f"Current Milestone: {res['current_node_id']}")
        st.info(res['last_generated_content'])
        
        st.write("---")
        st.write("### Story History")
        for i, node_id in enumerate(res['history']):
            st.code(f"Step {i+1}: {node_id}")

with col2:
    st.header("📊 Narrative Plot Graph")
    if 'current_result' in st.session_state:
        # Construct graph data for visualization
        res = st.session_state.current_result
        history = res['history']
        
        # Build simple graph for visualization
        manager = NarrativeGraphManager()
        for i in range(len(history)):
            node_id = history[i]
            manager.add_milestone(node_id)
            if i > 0:
                manager.add_causality(history[i-1], node_id, "Then")
        
        draw_narrative_graph(manager.get_graph_data())
    else:
        st.info("이야기를 시작하면 그래프가 여기에 표시됩니다.")

st.divider()
st.caption("© 2026 Narrative-Logic Engine - AIFFEL DLThon Project")
