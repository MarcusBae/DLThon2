import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

# main.py

import streamlit as st
import pickle
import glob
import datetime
import json
from dotenv import load_dotenv

from src.narrative_agent import build_narrative_graph
from src.visualizer import draw_narrative_graph
from src.graph_manager import NarrativeGraphManager
from src.mapper_agent import MapperAgent
from langchain_core.messages import HumanMessage, AIMessage
from src.tools import load_worldview, load_characters, load_plot

load_dotenv()

st.set_page_config(page_title="N.L Story Engine", layout="wide", initial_sidebar_state="collapsed")

# Load external CSS
if os.path.exists("resource/style.css"):
    with open("resource/style.css", "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ---------------------------------------------------------
# State Initialization
# ---------------------------------------------------------
if "workflow" not in st.session_state:
    st.session_state.workflow = build_narrative_graph()
if "current_page" not in st.session_state:
    st.session_state.current_page = "home"
if "active_story_id" not in st.session_state:
    st.session_state.active_story_id = None
if "current_state" not in st.session_state:
    st.session_state.current_state = None
if "chat_ui_messages" not in st.session_state:
    st.session_state.chat_ui_messages = []

def get_cache_file(story_id):
    os.makedirs(os.path.join("data", "session", story_id), exist_ok=True)
    return os.path.join("data", "session", story_id, "session_cache.pkl")

def get_user_data_dir(story_id):
    path = os.path.join("data", "user_data", story_id)
    os.makedirs(path, exist_ok=True)
    return path

def get_story_registry() -> dict:
    registry_file = os.path.join("data", "user_data", "stories.json")
    if os.path.exists(registry_file):
        try:
            with open(registry_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {"next_id": 1, "stories": {}}

def save_story_registry(registry: dict):
    os.makedirs(os.path.join("data", "user_data"), exist_ok=True)
    registry_file = os.path.join("data", "user_data", "stories.json")
    with open(registry_file, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

def register_new_story(story_id: str):
    registry = get_story_registry()
    new_num = int(registry.get("next_id", 1))
    title = f"제목 없는 이야기 {new_num}"
    
    stories_dict = registry.get("stories", {})
    if not isinstance(stories_dict, dict):
        stories_dict = {}
        
    stories_dict[story_id] = {
        "title": title,
        "created_at": datetime.datetime.now().isoformat()
    }
    
    registry["stories"] = stories_dict
    registry["next_id"] = new_num + 1
    save_story_registry(registry)

def remove_story_from_registry(story_id: str):
    registry = get_story_registry()
    stories_dict = registry.get("stories", {})
    if isinstance(stories_dict, dict) and story_id in stories_dict:
        _ = stories_dict.pop(story_id, None)
        registry["stories"] = stories_dict
        save_story_registry(registry)

# =========================================================
# HOME VIEW
# =========================================================
def show_home():
    st.markdown('<div class="home-spacer"></div>', unsafe_allow_html=True)

    # 1. Main Title & Subtitle (Centered)
    st.markdown("<h2 class='home-title'>어떤 이야기를 만드실 건가요?</h2>", unsafe_allow_html=True)
    st.markdown("<p class='home-subtitle'>다양한 서사 플롯 이론을 기반으로 당신만의 완벽한 스토리를 설계해 보세요!</p>", unsafe_allow_html=True)
    
    # 2. Centered Card Block    
    plots_file = os.path.join("data", "system", "registered_plots.json")
    if os.path.exists(plots_file):
        with open(plots_file, "r", encoding="utf-8") as f:
            plots = json.load(f)
    else:
        plots = []
    
    if plots:
        _, center_col, _ = st.columns([1, 8, 1])
        with center_col:
            cols = st.columns(len(plots))
            for idx, plot in enumerate(plots):
                with cols[idx]:
                    # 이모지와 시작하기 텍스트 제외하고 별칭만 노출
                    btn_label = f"{plot.get('alias', plot['name'])}"
                    if st.button(btn_label, key=f"start_plot_{plot['id']}", use_container_width=True):
                        # usage count update
                        plot['usage_count'] = plot.get('usage_count', 0) + 1
                        with open(plots_file, "w", encoding="utf-8") as f:
                            json.dump(plots, f, ensure_ascii=False, indent=2)
                        
                        # init new story
                        story_id = f"story_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        st.session_state.active_story_id = story_id
                        st.session_state.current_page = "chat"
                        st.session_state.current_state = None
                        st.session_state.chat_ui_messages = []
                        
                        # save metadata mapping
                        user_d_path = os.path.join("data", "user_data", story_id)
                        os.makedirs(user_d_path, exist_ok=True)
                        with open(os.path.join(user_d_path, "metadata.json"), "w", encoding="utf-8") as mdf:
                            json.dump({"theory_type": plot['id'], "created_at": datetime.datetime.now().isoformat()}, mdf, ensure_ascii=False)
                        
                        register_new_story(story_id)
                        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    _, input_col, _ = st.columns([2, 5, 2])
    with input_col:
        with st.form("idea_start_form", border=False):
            new_idea = st.text_input("💡 아이디어로 대화 시작하기", label_visibility="collapsed", placeholder="당신의 아이디어를 들려주세요!")
            submitted = st.form_submit_button("이야기 시작하기", type="secondary", use_container_width=True)
            if submitted:
                if new_idea.strip():
                    story_id = f"story_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    st.session_state.active_story_id = story_id
                    st.session_state.current_page = "chat"
                    st.session_state.current_state = None
                    st.session_state.chat_ui_messages = []
                    
                    user_d_path = os.path.join("data", "user_data", story_id)
                    os.makedirs(user_d_path, exist_ok=True)
                    # 기본 플롯으로 세팅
                    with open(os.path.join(user_d_path, "metadata.json"), "w", encoding="utf-8") as mdf:
                        json.dump({"theory_type": "THEORY_PROPP_VOGLER_HYBRID", "created_at": datetime.datetime.now().isoformat()}, mdf, ensure_ascii=False)
                    
                    register_new_story(story_id)
                    st.session_state.initial_prompt = {"idea": new_idea, "theory": "THEORY_PROPP_VOGLER_HYBRID"}
                    st.rerun()
                else:
                    st.warning("아이디어를 입력해 주세요.")

    st.markdown("<hr class='home-divider'>", unsafe_allow_html=True)
    
    # 3. Past Stories (Centered)
    st.markdown("<h4 class='home-section-title'>🗂️ 예전에 만들었던 스토리</h4>", unsafe_allow_html=True)
    
    session_root = os.path.join("data", "session")
    if os.path.exists(session_root):
        story_dirs = [d for d in os.listdir(session_root) if os.path.isdir(os.path.join(session_root, d))]
        valid_stories = []
        import shutil
        plots_file = os.path.join("data", "system", "registered_plots.json")
        for d in story_dirs:
            cache_file = os.path.join(session_root, d, "session_cache.pkl")
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, "rb") as f:
                        cache = pickle.load(f)
                    if isinstance(cache, dict) and cache.get("chat_ui_messages"):
                        valid_stories.append(d)
                    else:
                        # 대화 내용이 없는 빈 세션이므로 찌꺼기 폴더 삭제
                        shutil.rmtree(os.path.join(session_root, d), ignore_errors=True)
                        ud_path = os.path.join("data", "user_data", d)
                        if os.path.exists(ud_path):
                            meta_file = os.path.join(ud_path, "metadata.json")
                            if os.path.exists(meta_file):
                                with open(meta_file, "r", encoding="utf-8") as mf:
                                    meta = json.load(mf)
                                theory_id = meta.get("theory_type")
                                if theory_id and os.path.exists(plots_file):
                                    with open(plots_file, "r", encoding="utf-8") as pf:
                                        plots = json.load(pf)
                                    for p in plots:
                                        if p["id"] == theory_id and p.get("usage_count", 0) > 0:
                                            p["usage_count"] -= 1
                                            break
                                    with open(plots_file, "w", encoding="utf-8") as pf:
                                        json.dump(plots, pf, ensure_ascii=False, indent=2)
                            shutil.rmtree(ud_path, ignore_errors=True)
                        remove_story_from_registry(d)
                except Exception:
                    pass
                
        if not valid_stories:
            st.markdown("<p class='home-empty-msg'>아직 저장된 스토리가 없습니다.</p>", unsafe_allow_html=True)
        else:
            _, hist_col, _ = st.columns([1, 8, 1])
            with hist_col:
                cols = st.columns(3)
                for i, sid in enumerate(sorted(valid_stories, reverse=True)):
                    with cols[i % 3]:
                        with st.container(border=True):
                            registry_data = get_story_registry()
                            stories_dict = registry_data.get("stories", {})
                            if isinstance(stories_dict, dict):
                                story_info = stories_dict.get(sid, {})
                                title = story_info.get("title", sid) if isinstance(story_info, dict) else sid
                            else:
                                title = sid
                            st.markdown(f"<div class='history-card-title'><b>{title}</b></div>", unsafe_allow_html=True)
                            _, inner_btn, _ = st.columns([1, 4, 1])
                            if inner_btn.button("이어서 쓰기", key=f"resume_{sid}", use_container_width=True):
                                st.session_state.active_story_id = sid
                                st.session_state.current_page = "chat"
                                cache_file = os.path.join(session_root, sid, "session_cache.pkl")
                                try:
                                    with open(cache_file, "rb") as f:
                                        cache = pickle.load(f)
                                        st.session_state.current_state = cache.get("current_state")
                                        st.session_state.chat_ui_messages = cache.get("chat_ui_messages", [])
                                except Exception:
                                    st.session_state.current_state = None
                                    st.session_state.chat_ui_messages = []
                                st.rerun()
    else:
        st.markdown("<p class='home-empty-msg'>아직 저장된 스토리가 없습니다.</p>", unsafe_allow_html=True)

# =========================================================
# CHAT VIEW
# =========================================================
def show_chat():
    story_id = st.session_state.active_story_id
    if not story_id:
        st.warning("스토리가 선택되지 않았습니다.")
        if st.button("홈으로 이동"):
            st.session_state.current_page = "home"
            st.rerun()
        return

    CACHE_FILE = get_cache_file(story_id)
    user_data_path = get_user_data_dir(story_id)
    
    # ---------------------------------------------------------
    # Get Title and Theory Type Early
    # ---------------------------------------------------------
    registry_data = get_story_registry()
    stories_dict = registry_data.get("stories", {})
    if isinstance(stories_dict, dict):
        story_info = stories_dict.get(story_id, {})
        title = story_info.get("title", story_id) if isinstance(story_info, dict) else story_id
    else:
        title = story_id

    res = st.session_state.current_state
    meta_path = os.path.join(user_data_path, "metadata.json")
    if res:
        theory_type = res.get('master_data', {}).get('theory_type', 'THEORY_PROPP_VOGLER_HYBRID')
    elif os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            theory_type = json.load(f).get("theory_type", "THEORY_PROPP_VOGLER_HYBRID")
    else:
        theory_type = "THEORY_PROPP_VOGLER_HYBRID"
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    col_chat, col_data = st.columns([6, 4], gap="small")
    
    # ---------------------------------------------------------
    # Chat Interface (Left)
    # ---------------------------------------------------------
    with col_chat:
        with st.container(border=True):
            c_title, c_settings = st.columns([8, 2])
            with c_title:
                st.markdown(f"### 💬 {title}")
            with c_settings:
                with st.popover("⚙️", help="Story Settings"):
                    st.markdown("**⚙️ 설정 (Settings)**")
                    
                    new_title = st.text_input("스토리 제목 변경", value=title)
                    
                    plots_file = os.path.join("data", "system", "registered_plots.json")
                    plot_options = {}
                    if os.path.exists(plots_file):
                        with open(plots_file, "r", encoding="utf-8") as f:
                            p_data = json.load(f)
                            for p in p_data:
                                plot_options[p["id"]] = f"{p.get('alias', p['name'])}"
                    
                    plot_ids = list(plot_options.keys())
                    try:
                        current_idx = plot_ids.index(theory_type)
                    except ValueError:
                        current_idx = 0
                        
                    if plot_ids:
                        selected_plot = st.selectbox("플롯 이론 변경", options=plot_ids, format_func=lambda x: plot_options.get(x, x), index=current_idx)
                    else:
                        selected_plot = theory_type
                    
                    if st.button("변경 사항 저장", use_container_width=True, type="primary"):
                        changed = False
                        # 제목 업데이트
                        if new_title != title:
                            if not isinstance(stories_dict, dict):
                                stories_dict = {}
                            if story_id not in stories_dict:
                                stories_dict[story_id] = {}
                            stories_dict[story_id]["title"] = new_title
                            registry_data["stories"] = stories_dict
                            save_story_registry(registry_data)
                            changed = True
                            
                        # 플롯 업데이트 (metadata.json 및 세션 상태)
                        if selected_plot != theory_type:
                            # 1) 파일 업데이트
                            meta_data = {}
                            if os.path.exists(meta_path):
                                try:
                                    with open(meta_path, "r", encoding="utf-8") as mf:
                                        loaded = json.load(mf)
                                        if isinstance(loaded, dict):
                                            meta_data = loaded
                                except Exception: pass
                            meta_data["theory_type"] = selected_plot
                            with open(meta_path, "w", encoding="utf-8") as mf:
                                json.dump(meta_data, mf, ensure_ascii=False, indent=2)
                            
                            # 2) 현재 활성 상태 업데이트
                            if st.session_state.current_state is not None:
                                current_s = st.session_state.current_state
                                if "master_data" in current_s:
                                    current_s["master_data"]["theory_type"] = selected_plot
                                    st.session_state.current_state = current_s
                                    
                            changed = True
                            
                        if changed:
                            st.rerun()

                    st.markdown("---")
                    if st.button("초기화 (Reset)", use_container_width=True):
                        st.session_state.current_state = None
                        st.session_state.chat_ui_messages = []
                        if os.path.exists(CACHE_FILE):
                            os.remove(CACHE_FILE)
                        st.rerun()

            # Display existing chat messages
            chat_container = st.container(height=650, border=False)
            with chat_container:
                if not st.session_state.chat_ui_messages:
                    st.markdown("아래 입력창에 첫 아이디어를 입력하여 이야기를 시작하세요!")
                for msg in st.session_state.chat_ui_messages:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])
                        
            # Chat Input
            user_input = st.chat_input("서사 에이전트와 대화를 나눠보세요...")

    # ---------------------------------------------------------
    # Source Panel (Right)
    # ---------------------------------------------------------
    with col_data:
        st.header("📝 창작 데이터 (Master Data)")
        
        res = st.session_state.current_state
        
        def get_master_data(key, file_name, loader):
            if res and res.get('master_data', {}).get(key):
                return res['master_data'][key]
            file_path = os.path.join(user_data_path, file_name)
            if os.path.exists(file_path):
                try:
                    return loader(file_path)
                except Exception:
                    return None
            return None

        wv_data = get_master_data('worldview', 'created_worldview.json', load_worldview)
        char_data = get_master_data('characters', 'created_character.json', load_characters)
        plot_data = get_master_data('plot_nodes', 'created_plot.json', load_plot)
        
        with st.expander("🌍 세계관 및 배경 (Worldview)", expanded=True):
            if wv_data:
                if isinstance(wv_data, dict):
                    st.write(f"**장르:** {wv_data.get('genre', '미정')}")
                    st.write(f"**설명:** {wv_data.get('description', '')}")
                else:
                    st.write(f"**장르:** {getattr(wv_data, 'genre', '미정')}")
                    st.write(f"**설명:** {getattr(wv_data, 'description', '')}")
            else:
                st.caption("아직 생성된 세계관이 없습니다. 채팅을 시작하면 자동 생성됩니다.")

        with st.expander("👥 등장 인물 (Characters)", expanded=True):
            if char_data:
                if isinstance(char_data, dict):
                    _chars_list = char_data.get("characters", [])
                elif isinstance(char_data, list):
                    _chars_list = char_data
                else:
                    _chars_list = getattr(char_data, "characters", [])
                
                if _chars_list:
                    for c in _chars_list:
                        name = c.get('name') if isinstance(c, dict) else getattr(c, 'name', 'N/A')
                        role = c.get('char_role') if isinstance(c, dict) else getattr(c, 'char_role', 'N/A')
                        st.markdown(f"- **{name}** ({role})")
                else:
                    st.caption("아직 생성된 캐릭터가 없습니다. 채팅을 시작하면 자동 생성됩니다.")
            else:
                st.caption("아직 생성된 캐릭터가 없습니다. 채팅을 시작하면 자동 생성됩니다.")

        with st.expander("📚 플롯 서사 구조 (Plot Nodes)", expanded=True):
            if plot_data:
                if hasattr(plot_data, 'Plot_Nodes'):
                    history = [node.Node_ID for node in plot_data.Plot_Nodes]
                elif isinstance(plot_data, list):
                    history = plot_data
                else:
                    history = []
                
                if history:
                    if res and 'current_section' in res:
                        st.caption(f"**Current Checkpoint:** {res['current_section']}")
                    for i, node_id in enumerate(history):
                        st.markdown(f"**Step {i+1}:** `{node_id}`")
                        
                    st.markdown("---")
                    st.markdown("**Causal Plot Graph**")
                    manager = NarrativeGraphManager()
                    for i in range(len(history)):
                        manager.add_milestone(history[i])
                        if i > 0:
                            manager.add_causality(history[i-1], history[i], "Then")
                    draw_narrative_graph(manager.get_graph_data())
                else:
                    st.caption("아직 생성된 플롯 노드가 없습니다. 채팅을 시작하면 자동 생성됩니다.")
            else:
                st.caption("아직 생성된 플롯 노드가 없습니다. 채팅을 시작하면 자동 생성됩니다.")

    # ---------------------------------------------------------
    # Input Execution
    # ---------------------------------------------------------
    # meta_path and theory_type are handled at the top of show_chat
        
    genre = res.get('master_data', {}).get('worldview', {}).get('genre', '') if (res and isinstance(res.get('master_data', {}).get('worldview', {}), dict)) else ""
    world_rules = ""

    # 초기 진입 시 홈 화면에서 전달받은 아이디어가 있다면 user_input으로 설정
    if hasattr(st.session_state, "initial_prompt") and st.session_state.initial_prompt:
        p_data = st.session_state.initial_prompt
        if "idea" in p_data and p_data["idea"].strip():
            user_input = p_data["idea"]
        del st.session_state.initial_prompt

    if user_input:
        st.session_state.chat_ui_messages.append({"role": "user", "content": user_input})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(user_input)
                
        with chat_container:
            with st.chat_message("assistant"):
                with st.spinner("N.L Engine이 서사를 계산 중입니다..."):
                    if st.session_state.current_state is None:
                        mapper = MapperAgent(theory_type=theory_type)
                        start_node_id = mapper.map_input_to_node(user_input)
                        
                        state_input = {
                            "messages": [HumanMessage(content=user_input)],
                            "current_section": "Section 01의 step_num:1", 
                            "is_section_complete": False,
                            "idea_note": [],
                            "master_data": {
                                "story_id": story_id,
                                "characters": [], 
                                "worldview": {"genre": genre, "rules": world_rules}, 
                                "plot_nodes": [start_node_id],
                                "theory_type": theory_type
                            },
                            "validation_status": {},
                            "next_node": "history",
                            "missing_info": []
                        }
                    else:
                        state_input = st.session_state.current_state
                        state_input["messages"].append(HumanMessage(content=user_input))
                    
                    try:
                        print(f"--- DEBUG: state_input type: {type(state_input)}")
                        if isinstance(state_input, dict):
                            print(f"--- DEBUG: state_input keys: {list(state_input.keys())}")
                        
                        new_state = st.session_state.workflow.invoke(state_input, config={"configurable": {"thread_id": story_id}})
                        
                        print(f"--- DEBUG: new_state type: {type(new_state)}")
                        
                        # new_state가 리스트인 경우 딕셔너리로 보정 (LangGraph 버전 이슈 대응)
                        if isinstance(new_state, list):
                            print("--- DEBUG: new_state is a list! Correcting to dict...")
                            new_state = {"messages": new_state}
                            
                        st.session_state.current_state = new_state
                        
                        # ai_response 추출
                        if isinstance(new_state, dict) and "messages" in new_state and new_state["messages"]:
                            ai_response = new_state["messages"][-1].content
                        elif isinstance(new_state, list) and new_state:
                            ai_response = new_state[-1].content
                        else:
                            ai_response = "응답을 생성하지 못했습니다."
                            
                    except Exception as e:
                        import traceback
                        tb_str = traceback.format_exc()
                        print(f"--- DEBUG: CAUGHT EXCEPTION: {tb_str}")
                        ai_response = f"**오류가 발생했습니다:** {str(e)}"
                        
                    st.markdown(ai_response)
                    st.session_state.chat_ui_messages.append({"role": "assistant", "content": ai_response})
                    
        with open(CACHE_FILE, "wb") as f:
            pickle.dump({
                "current_state": st.session_state.current_state,
                "chat_ui_messages": st.session_state.chat_ui_messages
            }, f)
        st.rerun()

# =========================================================
# MAIN ROUTING
# =========================================================
# 공통 상단 로고 (모든 뷰에서 노출, 클릭 시 홈으로 이동)
st.markdown('<div class="main-header-wrapper">', unsafe_allow_html=True)
if st.button("🧙‍♂️ Narrative-Logic (N.L) Engine", key="main_header_btn"):
    st.session_state.current_page = "home"
    st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

if st.session_state.current_page == "home":
    show_home()
else:
    show_chat()

st.markdown("""
<div class="footer-text">
    © N.L (Narrative-Logic) Engine Streamlit Dashboard.
</div>
""", unsafe_allow_html=True)
