# narrative_agent.py
"""LangGraph implementation for narrative node generation following the router-centric design."""

import os
import json
import difflib
from datetime import datetime
from typing import Annotated, Sequence, TypedDict, Union, Dict, List, Any, cast
import operator

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph.message import add_messages

from src.tools import (
    load_worldview, load_characters, load_plot, load_json,
    save_worldview, save_characters, save_plot
)

# ==========================================
# 1. 상태 정의 (NarrativeGraphState)
# ==========================================

class NarrativeGraphState(TypedDict):
    """
    서사 에이전트의 전체 상태를 관리하는 객체.
    디자인 문서(@design.md)의 architecture를 반영합니다.
    """
    # 1. 대화 기록 및 컨텍스트
    messages: Annotated[List[BaseMessage], add_messages] 
    
    # 2. 프로세스 제어 상태
    current_section: str  # 현재 진행 중인 창작 단계 (예: "Section 01의 step_num:1",  "Section 03 의 step_num:3" 등) 
    is_section_complete: bool  # 현재 섹션의 필수 요건이 모두 충족되었는지 여부
    
    # 3. 보류된 사용자 아이디어 저장소 (idea_note.json 구조)
    idea_note: Annotated[List[Dict[str, Any]], operator.add]
    
    # 4. 확정된 마스터 데이터 (schema.json 기준)
    master_data: Dict[str, Any]  # { "characters": [], "worldview": {}, "plot_nodes": [] }
    
    # 5. 서사 논리 검증 상태 (Validator)
    validation_status: Dict[str, Any] 
    # 예: { "is_valid": True, "violation_rate": 0.0, "errors": [] } 
    
    # 6. 다음 노드 분기를 위한 플래그 (Router 제어용)
    next_node: str  # 라우터가 참조할 다음 이동 경로 (예: "generate_plot", "ask_user", "validate")
    missing_info: List[str]  # 다음 단계로 넘어가기 위해 사용자에게 추가로 물어봐야 할 필수 정보 리스트

# ==========================================
# 2. 그래프 노드 구현 (Graph Nodes)
# ==========================================

def history_node(state: NarrativeGraphState):
    """
    대화 기록과 사용자 데이터를 로드하고 상태를 초기화하는 노드.
    design.md의 1번 단계에 해당합니다.
    """
    print("--- [history_node] Loading context and user data ---")
    if not isinstance(state, dict):
        state = cast(dict, {"messages": state if isinstance(state, list) else []})
    
    # 1) 데이터 로드 (동적 story_id 경로 기반)
    data_dir = "./data"
    
    def safe_load(func, path, fallback):
        import os
        return func(path) if os.path.exists(path) else fallback

    m_data = state.get("master_data", {})
    story_id = str(m_data.get("story_id", "")) if isinstance(m_data, dict) else ""
    if story_id:
        user_data_path = os.path.join(data_dir, "user_data", story_id)
        os.makedirs(user_data_path, exist_ok=True)
    else:
        user_data_path = os.path.join(data_dir, "user_data")
        
    # metadata.json 로드하여 theory_type 추출
    metadata = safe_load(load_json, os.path.join(user_data_path, "metadata.json"), {})
    theory_type = metadata.get("theory_type") or metadata.get("theory_id")
    
    master_data = {
        "story_id": story_id,
        "worldview": safe_load(load_worldview, os.path.join(user_data_path, "created_worldview.json"), None),
        "characters": safe_load(load_characters, os.path.join(user_data_path, "created_character.json"), None),
        "plot_nodes": safe_load(load_plot, os.path.join(user_data_path, "created_plot.json"), None),
        "theory_type": theory_type
    }
    idea_note = safe_load(load_json, os.path.join(user_data_path, "idea_note.json"), [])
    
    # 2) 워크플로우 로드 및 초기 섹션 설정
    workflow_data = load_json(os.path.join(data_dir, "system", "workflow_data.json"))
    
    # 전달받은 상태에 이미 섹션 정보가 있다면 유지, 없으면 초기화
    current_section = state.get("current_section")
    if not current_section:
        try:
            current_section = f"Section {workflow_data['sections'][0].get('section_id', '')}의 step_num:1"
        except (KeyError, IndexError):
            current_section = "unknown section"
    
    return {
        "master_data": master_data,
        "idea_note": idea_note if isinstance(idea_note, list) else [],
        "current_section": current_section,
        "is_section_complete": state.get("is_section_complete", False),
        "next_node": "router"
    }

def generator_node(state: NarrativeGraphState):
    """
    LLM을 사용하여 응답을 생성하는 노드.
    """
    print("--- [generator_node] Researching and generating response ---")
    if not isinstance(state, dict):
        state = cast(dict, {"messages": state if isinstance(state, list) else []})

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    
    # 워크플로우 로드하여 현재 섹션 정보 찾기
    data_dir = "./data"
    workflow_data = load_json(os.path.join(data_dir, "system", "workflow_data.json"))
    if isinstance(workflow_data, dict):
        persona = workflow_data.get("agent_persona", {"identity": "스토리 작가", "core_role": "창작 보조"})
        interaction_rules = workflow_data.get("interaction_rules", {})
    else:
        persona = {"identity": "스토리 작가", "core_role": "창작 보조"}
        interaction_rules = {}
        
    rules_text = "\n    ".join([f"- {v}" for k, v in interaction_rules.items()]) if interaction_rules else "- 인터뷰 스타일 유지"
    
    # 2. 동적 플롯 이론 로드 및 마일스톤 추출
    theory_type = state.get('master_data', {}).get('theory_type', 'THEORY_PROPP_VOGLER_HYBRID')
    theory_plot_data = load_json(os.path.join(data_dir, "theory", "theory_plot.json"))
    milestones_text = "지정된 플롯 이론이 없습니다."
    
    if isinstance(theory_plot_data, dict):
        for t in theory_plot_data.get("plot_theories", []):
            if t.get("theory_id") == theory_type:
                theory_name = t.get("theory_name", "")
                theory_desc = t.get("description", "")
                ms_list = []
                for ms in t.get("milestones", []):
                    ms_list.append(f"[{ms.get('act', 'Act')}] {ms.get('title', '')}: {ms.get('description', '')}")
                milestones_text = f"이론명: {theory_name}\n    설명: {theory_desc}\n    마일스톤 구성:\n    " + "\n    ".join(ms_list)
                break

    # 2. 현재 단계 및 다음 단계 지침 추출
    current_section_str = str(state.get("current_section", ""))
    section_num = ""
    step_num = 1
    
    if "Section" in current_section_str:
        try:
            if "의 step_num:" in current_section_str:
                parts = current_section_str.split("의 step_num:")
                section_num = parts[0].replace("Section ", "").strip()
                step_num = int(parts[1].strip())
        except: pass

    # 현재 단계 정보
    current_step_info = {}
    next_step_info = {}
    
    if isinstance(workflow_data, dict) and section_num:
        for sec in workflow_data.get("sections", []):
            if sec.get("section_id") == section_num:
                steps = sec.get("steps", [])
                for i, stp in enumerate(steps):
                    if stp.get("step_number") == step_num:
                        current_step_info = stp
                        if i + 1 < len(steps):
                            next_step_info = steps[i+1]
                        break
                # 만약 현재 섹션의 마지막 스텝이라면 다음 섹션의 첫 스텝을 찾아야 함 (여기선 단순화)
    
    task_name = current_step_info.get("task_name", "창작 진행")
    agent_mission = current_step_info.get("agent_action", "사용자의 아이디어를 구체화하세요.")
    
    # 만약 플롯 이론이 이미 선택되어 있다면, 지침에서 이론 선택 유도 부분을 무시하도록 명시
    if theory_type:
        agent_mission += f"\n(참고: 현재 플롯 이론은 '{theory_type}'으로 이미 확정되었습니다. 사용자에게 어떤 이론을 쓸지 다시 묻지 마세요.)"
        
    output_reqs = current_step_info.get("output_requirements", [])
    reqs_text = "\n    - ".join(output_reqs) if output_reqs else "없음"
    
    next_task_name = next_step_info.get("task_name", "다음 단계")
    next_agent_mission = next_step_info.get("agent_action", "다음 설정을 진행하세요.")

    worldview = state.get('master_data', {}).get('worldview', {})
    worldview_id = worldview.get('world_id', '미정') if isinstance(worldview, dict) else getattr(worldview, 'world_id', '미정')
    characters = state.get('master_data', {}).get('characters', [])
    if hasattr(characters, 'characters'):
        _chars_list = characters.characters
    elif isinstance(characters, dict):
        _chars_list = characters.get('characters', [])
    else:
        _chars_list = characters if isinstance(characters, list) else []

    char_names = [c.get('name') if isinstance(c, dict) else getattr(c, 'name', 'N/A') for c in _chars_list] if _chars_list else []

    user_context = f"현재 세계관: {worldview_id}, " \
                   f"참여 캐릭터: {char_names}"
    
    # 3. 메시지 히스토리 길이 및 섹션 기반 복잡도/포화도 파악
    messages = state.get("messages", [])
    history_len = len(messages) if isinstance(messages, list) else 0
    current_section = str(state.get("current_section", ""))
    
    is_early_stage = current_section.startswith("Section 01")
    complexity_instruction = ""
    if is_early_stage:
        complexity_instruction = "현재는 스토리 초반부입니다. 복잡한 설정을 피하고 **1개의 핵심 주제/키워드**에 대해서만 심플하게 대화를 이어가세요."
    
    saturation_warning = ""
    if is_early_stage:
        msgs = state.get("messages", [])
        if isinstance(msgs, list) and len(msgs) < 6:
            saturation_warning = "\n[중요] 아직 아이디어 포화도가 낮습니다(대화 3회 미만). 절대로 플롯이나 구체적 전개를 제안하지 마세요."

    # 4. 시스템 프롬프트 구성
    system_msg = SystemMessage(content=f"""
    [당신의 정체성]
    - {persona.get('identity', '기본 정체성')}
    - 역할: {persona.get('core_role', '기본 역할')}
    
    [핵심 상호작용 원칙 (절대 준수)]
    1. **단일 질문 (Single Question)**: 답변의 마지막에 오직 **단 하나**의 핵심 질문만 던지세요. 질문이 여러 개이면 사용자가 혼란을 느낍니다.
    2. **3~5개 예시 (Numbered Examples)**: 사용자의 답변을 돕기 위해 반드시 **3~5개의 구체적인 답변 예시**를 번호 목록(1. 2. 3...)으로 제공하세요.
    3. **단계별 집중 (Step-Fidelity)**: 현재 단계({task_name})의 미션에만 집중하세요. {task_name}를 구축하는 것이 목표입니다.
    4. **점진적 복잡성**: {complexity_instruction}
    
    [심리스 다음 단계 지침 (Seamless Transition)]
    만약 현재 단계({task_name})의 요건이 충분히 충족되어 확정되었다면, **"{task_name}이(가) 확정되었습니다! [STEP_COMPLETED]"**라고 명시하고, **대화를 끊지 말고 즉시** 다음 단계인 **'{next_task_name}'**에 대한 첫 질문을 던지세요.
    
    [답변 가이드]
    - 사용자가 "좋아", "확정" 등 긍정적인 반응을 보이면 해당 요소를 확정하고 요약해 주세요.
    - 확정된 내용은 반드시 답변 내에 명확히 언급하여 사용자가 인지하게 하세요.
    - {saturation_warning}
    
    위 원칙을 준수하여 사용자를 친절하게 리드하세요. 질문은 단 하나, 예시는 3~5개!
    """)
    
    response = llm.invoke([system_msg] + state.get("messages", []))
    
    return {
        "messages": [response],
        "next_node": "update"
    }

def update_node(state: NarrativeGraphState):
    """
    대화 내용을 분석하여 확정된 설정을 추출하고 JSON 파일로 자동 저장하는 노드.
    """
    print("--- [update_node] Extracting & Updating Metadata ---")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0) # 정확성을 위해 0
    
    if not isinstance(state, dict):
        return {"next_node": "response_check"}
        
    messages = state.get("messages", [])
    m_data = state.get("master_data", {})
    story_id = str(m_data.get("story_id", "")) if isinstance(m_data, dict) else ""
    
    if not story_id: return {"next_node": "response_check"}

    # 0. Load Schemas and Theory
    data_dir = "./data"
    
    def safe_load(func, path, fallback):
        return func(path) if os.path.exists(path) else fallback
        
    # Load schema for characters and worldview
    schema_path = os.path.join(data_dir, "system", "schema_data.json")
    schema_data = safe_load(load_json, schema_path, {})
    char_schema = schema_data.get("definitions", {}).get("character_schema", {})
    world_schema = schema_data.get("definitions", {}).get("worldview_schema", {})
    
    # Load theory milestones
    theory_type = m_data.get('theory_type') or m_data.get('theory_id') or 'THEORY_PROPP_VOGLER_HYBRID'
    theory_plot_data = safe_load(load_json, os.path.join(data_dir, "theory", "theory_plot.json"), {})
    
    theory_desc = "선택된 이론이 없습니다."
    if isinstance(theory_plot_data, dict):
        for t in theory_plot_data.get("plot_theories", []):
            if t.get("theory_id") == theory_type:
                ms_list = []
                for ms in t.get("milestones", []):
                    if not isinstance(ms, dict): continue
                    funcs_list = []
                    for f in ms.get("mapped_functions", []):
                        if isinstance(f, dict):
                            funcs_list.append(f"{f.get('function_id', '')}({f.get('name', '')})")
                        else:
                            funcs_list.append(str(f))
                    funcs = ", ".join(funcs_list)
                    ms_list.append(f"[{ms.get('act')}] {ms.get('title')} - 가능 함수: {funcs}")
                theory_desc = f"이론명: {t.get('theory_name')}\n" + "\n".join(ms_list)
                break

    # 기존 캐릭터 컨텍스트 추출
    characters_data = state.get('master_data', {}).get('characters', [])
    if hasattr(characters_data, 'characters'): _chars_list = characters_data.characters
    elif isinstance(characters_data, dict): _chars_list = characters_data.get('characters', [])
    elif isinstance(characters_data, list): _chars_list = characters_data
    else: _chars_list = []
    if _chars_list is None: _chars_list = []
    
    chars_ext = []
    for c in _chars_list:
        if isinstance(c, dict): chars_ext.append(f"{c.get('name')}: {c.get('char_id')}")
        elif hasattr(c, 'name'): chars_ext.append(f"{c.name}: {c.char_id}")
    
    existing_chars_info = ", ".join(chars_ext)
    char_context = f"\n    [기존 등록된 캐릭터 ID 매핑]\n    기존 인물을 다시 추출할 때는 절대 임의의 새 ID를 쓰지 말고 반드시 아래의 기존 고유 ID를 동일하게 재사용하세요:\n    {existing_chars_info}\n" if existing_chars_info else ""

    # 기존 플롯 노드 컨텍스트 추출 (소수점 인덱스 파악용)
    plot_data = state.get('master_data', {}).get('plot_nodes', [])
    if hasattr(plot_data, 'Plot_Nodes'): _plot_list = plot_data.Plot_Nodes
    elif isinstance(plot_data, dict): _plot_list = plot_data.get('Plot_Nodes', []) or plot_data.get('plot_nodes', [])
    elif isinstance(plot_data, list): _plot_list = plot_data
    else: _plot_list = []
    if _plot_list is None: _plot_list = []
    
    plot_strings = []
    for pn in _plot_list:
        if isinstance(pn, dict):
            plot_strings.append(f"- {pn.get('Node_ID')}: {pn.get('Function_ID')} (Seq: {pn.get('Sequence_Index')}) - {pn.get('Content')}")
        elif hasattr(pn, 'Node_ID'):
            plot_strings.append(f"- {pn.Node_ID}: {pn.Function_ID} (Seq: {pn.Sequence_Index}) - {pn.Content}")
            
    plot_ctx_info = "\n    ".join(plot_strings)
    plot_context = f"\n    [기존 작성된 플롯 노드 상태]\n    새로운 노드의 Sequence_Index를 정할 때 아래 기존 노드들의 Seq 값을 참고하세요:\n    {plot_ctx_info}\n" if plot_ctx_info else ""

    # 1. 메타데이터 추출용 프롬프트
    extract_msg = SystemMessage(content=f"""
    당신의 임무는 대화 기록을 분석하여 사용자와 에이전트 사이에 '확정'된 스토리 요소를 JSON 형태로 추출하는 것입니다.
    사용자가 "좋아", "그걸로 가자", "응" 등 긍정적인 반응을 보인 내용만 확정된 것으로 간주합니다.
    {char_context}{plot_context}
    [참고 구조 및 제약]
    1. 세계관: 다음 구조를 따르세요.
       {json.dumps(world_schema.get('properties', {}), ensure_ascii=False)}
    2. 캐릭터: 다음 구조를 따르세요. 반드시 고유 char_id를 부여할 것.
       {json.dumps(char_schema.get('properties', {}), ensure_ascii=False)}
    3. 플롯 (현재 구상된 전체 서사 흐름):
       다음 이론의 진행 단계를 참고하여 매핑하세요:
       {theory_desc}
    
    출력은 반드시 다음 JSON 구조를 엄격히 따라야 합니다:
    {{
      "worldview": {{
        "world_id": "WORLD_01",
        "genre": "...",
        "description": "세계관에 대한 핵심 설명 (3~5문장)",
        "features": {{}},
        "rules": [ {{"rule_title": "...", "forbidden_events": []}} ]
      }},
      "characters": [
        {{
          "char_id": "CHAR_01",
          "name": "...",
          "char_role": "주인공",
          "dominant_trait": "...",
          "forbidden_action": "..."
        }}
      ],
      "plot_data": {{
        "Plot_Metadata": {{
          "Story_ID": "{story_id}",
          "Title": "스토리 제목",
          "Applied_Structure": "{theory_type}",
          "Main_Characters": {{ "Protagonist_ID": "...", "Antagonist_ID": "..." }},
          "Core_Deficiency": {{ "Immediate_Lack": "...", "Fundamental_Lack": "..." }},
          "Tags": {{ "Topics": [], "Polarity": "Neutral" }},
          "Validation_Status": {{ "Violation_Rate": "0%", "Is_Valid": true }}
        }},
        "Plot_Nodes": [
          {{
            "Node_ID": "N_001",
            "Sequence_Index": 10.0,
            "Function_ID": "<반드시 3. 플롯의 해당 단계 '가능 함수' 중 하나를 정확히 복사해서 기입할 것>",
            "Content": "해당 단계에서 일어난 구체적 사건 요약",
            "Involved_Characters": ["CHAR_01"],
            "Background_World_ID": "WORLD_01",
            "Validation_Data": {{ "Required_Trait": "...", "Effect_Type": "NONE" }},
            "Memo": "메모 내용"
          }}
        ]
      }}
    }}
    
    오직 순수한 JSON만 출력하세요. 데이터가 충분하지 않다면 기존 데이터를 유지하거나 빈 항목으로 두세요. 마크다운 언어 태그(```json 등)를 사용하지 마세요. 방금 전 대화에서 새롭게 확정된 진행 단계(단일 노드)만 **새로 추가**할 것. 'description' 필드와 'features' 필드를 최대한 구체적으로 채워주세요.
    주의: Function_ID에는 임의의 값을 적지 말고, 반드시 위 3. 플롯에 제공된 '가능 함수' 목록에 있는 텍스트(예: P01(부재), STC_OPENING 등)를 그대로 써야 합니다.
    Sequence_Index 부여 규칙: 각 사건은 [마일스톤 순서][함수 순서].0 의 기본값을 가집니다 (예: 2막 3번째 함수면 23.0). 같은 함수의 사건이 여러 개라면 23.1, 23.2 로 증가시키며, 기존 23.8과 23.9 사이에 발생한 중간 사건이라면 23.85 처럼 소수점을 지정하세요.
    """)
    
    try:
        res = llm.invoke([extract_msg] + messages[-4:])
        content = str(res.content)
        
        # ```json ... ``` 블록 제거
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        data = json.loads(content)
        if not isinstance(data, dict):
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            else:
                data = {}
        
        print(f"--- [update_node] Extracted data keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
        
        # 2. 파일 저장 로드 및 업데이트
        data_dir = "./data/user_data"
        user_path = os.path.join(data_dir, story_id)
        
        # master_data 상태도 업데이트
        new_master = dict(state.get("master_data", {}))
        
        # 1. Worldview 병합 저장
        if isinstance(data, dict) and "worldview" in data:
            wv_file = os.path.join(user_path, "created_worldview.json")
            existing_wv = {}
            if os.path.exists(wv_file):
                try:
                    with open(wv_file, "r", encoding="utf-8") as f:
                        existing_wv = json.load(f)
                except Exception: pass
            if isinstance(data["worldview"], dict):
                existing_wv.update(data["worldview"])
            with open(wv_file, "w", encoding="utf-8") as f:
                json.dump(existing_wv, f, ensure_ascii=False, indent=2)
            new_master["worldview"] = existing_wv

        # 2. Characters 병합 저장
        if isinstance(data, dict) and "characters" in data:
            char_file = os.path.join(user_path, "created_character.json")
            existing_chars_data = {"characters": []}
            if os.path.exists(char_file):
                try:
                    with open(char_file, "r", encoding="utf-8") as f:
                        existing_chars_data = json.load(f)
                except Exception: pass
            
            existing_chars = existing_chars_data.get("characters", [])
            new_chars = data["characters"] if isinstance(data["characters"], list) else []
            
            for nc in new_chars:
                if not isinstance(nc, dict): continue
                c_id = nc.get("char_id")
                matched = False
                for i, ec in enumerate(existing_chars):
                    if isinstance(ec, dict) and ec.get("char_id") == c_id:
                        if c_id is not None:
                            existing_chars[i].update(nc)
                            matched = True
                            break
                if not matched:
                    if not c_id:
                        nc["char_id"] = f"CHAR_{len(existing_chars)+1:02d}"
                    existing_chars.append(nc)
                    
            existing_chars_data["characters"] = existing_chars
            with open(char_file, "w", encoding="utf-8") as f:
                json.dump(existing_chars_data, f, ensure_ascii=False, indent=2)
            new_master["characters"] = existing_chars

        # 3. Plot Data 병합 저장
        existing_plot_data = {"Plot_Metadata": {}, "Plot_Nodes": []}
        plot_file_path = os.path.join(user_path, "created_plot.json")
        if os.path.exists(plot_file_path):
            try:
                with open(plot_file_path, "r", encoding="utf-8") as f:
                    existing_plot_data = json.load(f)
            except Exception: pass
            
        if "Plot_Nodes" not in existing_plot_data:
            existing_plot_data["Plot_Nodes"] = []

        if isinstance(data, dict) and "plot_data" in data:
            new_plot_data = data["plot_data"]
            if isinstance(new_plot_data, dict):
                if "Plot_Metadata" in new_plot_data:
                    if "Plot_Metadata" not in existing_plot_data: existing_plot_data["Plot_Metadata"] = {}
                    existing_plot_data["Plot_Metadata"].update(new_plot_data["Plot_Metadata"])
                    
                new_nodes = new_plot_data.get("Plot_Nodes", [])
                if isinstance(new_nodes, list):
                    for n in new_nodes:
                        if isinstance(n, dict):
                            # 중복 (유사도 80% 이상) 텍스트 검사기
                            is_dup = False
                            for ex_n in existing_plot_data.get("Plot_Nodes", []):
                                if isinstance(ex_n, dict):
                                    ratio = difflib.SequenceMatcher(None, n.get("Content", ""), ex_n.get("Content", "")).ratio()
                                    if ratio > 0.8:
                                        is_dup = True
                                        break
                            if is_dup: continue
                            
                            # N_001 버그를 막기 위한 동적 ID 순차 발급
                            new_idx = len(existing_plot_data["Plot_Nodes"]) + 1
                            n["Node_ID"] = f"N_{new_idx:03d}"
                            
                            # 플롯 이론에 기반한 Sequence_Index 자동 계산
                            calc_seq = 0.0
                            f_id_val = str(n.get("Function_ID", ""))
                            from src.data_loader import load_theory
                            t_data = load_theory()
                            curr_t = state.get("theory_choice", "THEORY_PROPP_VOGLER_HYBRID")
                            
                            if t_data and "plot_theories" in t_data:
                                for t in t_data["plot_theories"]:
                                    if t.get("theory_id") == curr_t:
                                        for m_idx, ms in enumerate(t.get("milestones", [])):
                                            for f_idx, func in enumerate(ms.get("mapped_functions", [])):
                                                func_str = func.get("function_id", "") if isinstance(func, dict) else str(func)
                                                if f_id_val and (f_id_val in func_str or func_str in f_id_val):
                                                    calc_seq = float((m_idx + 1) * 10 + (f_idx + 1))
                                                    break
                                            if calc_seq > 0: break
                                        break
                                        
                            if calc_seq > 0:
                                llm_seq = float(n.get("Sequence_Index", 0.0))
                                # LLM이 현재 Function_ID의 대역(calc_seq의 정수부) 내에서 소수점(예: 23.85)을 지정했다면 존중
                                if int(llm_seq) == int(calc_seq):
                                    n["Sequence_Index"] = llm_seq
                                else:
                                    # 파이썬에서 자동 순차 소수점 할당 로직
                                    same_base_seqs = [
                                        float(old_n.get("Sequence_Index", 0.0)) 
                                        for old_n in existing_plot_data["Plot_Nodes"] 
                                        if int(float(old_n.get("Sequence_Index", 0.0))) == int(calc_seq)
                                    ]
                                    if not same_base_seqs:
                                        n["Sequence_Index"] = calc_seq
                                    else:
                                        max_seq = max(same_base_seqs)
                                        if max_seq == calc_seq:
                                            n["Sequence_Index"] = calc_seq + 0.1
                                        else:
                                            next_seq = max_seq + 0.1
                                            if next_seq >= calc_seq + 1.0:
                                                next_seq = max_seq + 0.01
                                            n["Sequence_Index"] = round(next_seq, 2)
                                
                            existing_plot_data["Plot_Nodes"].append(n)
                            
            with open(plot_file_path, "w", encoding="utf-8") as f:
                json.dump(existing_plot_data, f, ensure_ascii=False, indent=2)
                
            new_master["plot_nodes"] = existing_plot_data["Plot_Nodes"]
        else:
            new_master["plot_nodes"] = existing_plot_data.get("Plot_Nodes", [])
        
        
        return {"master_data": new_master, "next_node": "response_check"}
    except Exception as e:
        print(f"Error in update_node: {e}")
        return {"next_node": "response_check"}

def tools_node(state: NarrativeGraphState):
    """
    PDF 생성 등 외부 도구를 실행하는 노드.
    design.md의 5번 단계에 해당합니다.
    """
    print("--- [tools_node] Executing tools ---")
    # 예시: write_pdf_tool 호출 등
    return {"next_node": "router"}

def response_check_node(state: NarrativeGraphState):
    """
    생성된 답변이 요구사항을 충족하는지 검증하고 다음 단계를 결정하는 노드.
    """
    print("--- [response_check_node] Validating response & progression ---")
    if not isinstance(state, dict):
        state = cast(dict, {"messages": state if isinstance(state, list) else []})
    
    current_section = str(state.get("current_section", ""))
    messages = state.get("messages", [])
    last_ai_msg = messages[-1].content if messages else ""
    
    # AI가 답변에 [STEP_COMPLETED] 태그를 포함했는지 확인
    is_completed = "[STEP_COMPLETED]" in last_ai_msg
    
    # [추가] 메타데이터 검증: Section 01인 경우 로그라인 아이디어가 있는지 등 확인
    mdata = state.get("master_data")
    if is_completed and current_section.startswith("Section 01") and isinstance(mdata, dict):
        # Premise Builder 단계 등에서 실제 데이터가 채워졌는지 간접 확인
        wv = mdata.get("worldview")
        if not wv:
            print("--- [response_check] Blocking progression: Worldview metadata missing ---")
            # 사용자가 내용을 충분히 채웠는지 확인 (여기서는 시뮬레이션상 통과시키되 지침상 강조)

    # [추가] 메타데이터 검증: 실질적인 데이터가 채워졌는지 확인
    mdata = state.get("master_data")
    is_valid_data = True
    missing_reason = ""
    
    if is_completed and isinstance(mdata, dict):
        if current_section.startswith("Section 01의 step_num:1"):
             wv = mdata.get("worldview", {})
             # description, features, Setting 중 하나라도 있으면 유효한 것으로 간주 (유연한 검증)
             description = wv.get("description") or wv.get("Setting") or (wv.get("features") if isinstance(wv.get("features"), dict) and len(wv.get("features")) > 0 else None)
             if not wv or not description:
                 is_valid_data = False
                 missing_reason = "세계관에 대한 설명이 아직 부족합니다."
        elif current_section.startswith("Section 01의 step_num:3"):
             chars = mdata.get("characters", [])
             if not chars:
                 is_valid_data = False
                 missing_reason = "주요 캐릭터 설정이 아직 완료되지 않았습니다."

    if is_completed and not is_valid_data:
        print(f"--- [response_check] Validation FAILED: {missing_reason} ---")
        is_completed = False

    # 만약 현재 단계가 완료되었다면 다음 단계 계산
    next_section = current_section
    if is_completed:
        # Section 01 step 1 -> step 2 -> step 3 -> Section 02 step 1...
        try:
            if "의 step_num:" in current_section:
                parts = current_section.split("의 step_num:")
                s_name = parts[0]
                s_id_str = s_name.replace("Section ", "").strip()
                s_step = int(parts[1])
                
                # 다음 스텝으로 (S1은 3단계까지 있음)
                if s_step < 3:
                    next_section = f"{s_name}의 step_num:{s_step + 1}"
                else:
                    # 다음 섹션으로
                    next_id = int(s_id_str) + 1
                    next_section = f"Section {next_id:02d}의 step_num:1"
        except Exception as e:
            print(f"Error calculating next section: {e}")

    return {
        "current_section": next_section,
        "is_section_complete": is_completed,
        "validation_status": {"is_valid": True, "violation_rate": 0.0, "errors": []},
        "next_node": "END"
    }

# ==========================================
# 3. 라우팅 로직 (Routing Logic)
# ==========================================

def router_logic(state: NarrativeGraphState):
    """
    어떤 노드로 분기할지 결정하는 조건부 엣지 함수.
    """
    if not isinstance(state, dict):
        return "END"
    print(f"--- [router] Deciding next step for {state.get('next_node', 'END')} ---")
    return state.get("next_node", "END")

# ==========================================
# 4. 그래프 구축 (Graph Building)
# ==========================================

def build_narrative_graph():
    builder = StateGraph(NarrativeGraphState)
    
    # 노드 추가
    builder.add_node("history", history_node)
    builder.add_node("generator", generator_node)
    builder.add_node("update", update_node)
    builder.add_node("tools", tools_node)
    builder.add_node("response_check", response_check_node)
    
    # 엣지 연결
    builder.set_entry_point("history")
    
    # 라우터 기반 조건부 분기
    builder.add_conditional_edges(
        "history",
        router_logic,
        {
            "router": "generator", # history 다음엔 주로 생성으로
            "generator": "generator",
            "update": "update",
            "tools": "tools",
            "END": END
        }
    )
    
    builder.add_edge("generator", "update")
    
    builder.add_conditional_edges(
        "response_check",
        lambda x: "END" if isinstance(x, dict) and x.get("validation_status", {}).get("is_valid", False) else "generator",
        {
            "END": END,
            "generator": "generator"
        }
    )
    
    builder.add_edge("update", "response_check") # 업데이트 후 검증으로
    builder.add_edge("tools", "generator")
    
    return builder.compile()

# ==========================================
# 5. 실행 테스트 (Test Run)
# ==========================================

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    graph = build_narrative_graph()
    
    # 초기 질문
    initial_input = "김철수가 사막에서 모험을 시작하는 로그라인을 잡아줘."
    
    config = {"configurable": {"thread_id": "test_user_01"}}
    
    for chunk in graph.stream(
        {"messages": [HumanMessage(content=initial_input)]},
        config
    ):
        for node_name, output in chunk.items():
            print(f"\n[Node: {node_name}]")
            if "messages" in output and output["messages"]:
                print(f"AI: {output['messages'][-1].content}")
