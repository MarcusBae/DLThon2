# report_view.py
"""Standalone Streamlit UI components for rendering narrative validation reports."""

import streamlit as st
import pandas as pd
from datetime import datetime
from src.validator_agent import ValidatorAgent

def format_time(iso_str):
    """ISO 타임스탬프를 읽기 쉬운 포맷으로 변환"""
    if not iso_str: return "기록 없음"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%y-%m-%d %H:%M:%S")
    except:
        return str(iso_str)

def render_validation_report(validator: ValidatorAgent):
    """
    ValidatorAgent의 캐시된 기록 및 실시간 Mtime을 비교하여
    재생성 스위치 및 오류율 감소 트렌드, 상세 내역 등을 렌더링합니다.
    """
    history = validator.load_history()
    is_stale = validator.is_report_stale()
    
    st.markdown("### 🔍 서사 정합성(Internal Consistency) 통합 검증 리포트")
    
    # 1. 파일 최종 수정일(업데이트 시점) 트래킹 화면
    ts = validator.get_timestamps()
    
    st.caption("⏱️ 설정 파일 수정 일시 트래킹")
    colA, colB, colC, colD = st.columns(4)
    colA.info(f"**캐릭터:**\n\n{format_time(ts['characters'])}")
    colB.info(f"**세계관:**\n\n{format_time(ts['worldview'])}")
    colC.info(f"**플롯 노드:**\n\n{format_time(ts['plot_nodes'])}")
    colD.success(f"**과거 보고서:**\n\n{format_time(ts['report']) if ts['report'] else '기록 없음'}")
    
    # 2. 재생성 버튼 로직
    if is_stale or not history:
        if is_stale and history:
            st.warning("⚠️ 파일이 수정되어 기존 보고서 내용과 불일치할 수 있습니다. 최신 데이터로 다시 검증해 주세요.")
        else:
            st.warning("⚠️ 아직 생성된 1단계 검증 보고서가 없습니다.")
            
        if st.button("🔄 최신 데이터로 리포트 (재)생성", type="primary", use_container_width=True):
            with st.spinner("LLM이 다차원 서사적 모순(캐릭터/세계관/플롯)을 정밀 분석 중입니다... 🔍"):
                validator.generate_report()
            st.session_state.force_reopen_dialog = True
            st.rerun()
            return
            
    if not history:
        # 데이터가 없으면 렌더링 중단
        return
        
    latest = history[-1]
    logical = latest["logical"]
    phys = latest["physical"]
    emap = latest.get("entity_map", {})
    
    st.divider()
    
    # 3. 탭 구성
    t_summary, t_detail, t_graph = st.tabs(["📊 현재 요약", "🧐 세부 위반 내역", "📉 오류 감소 트렌드"])
    
    with t_summary:
        st.markdown("#### 1. 물리적 완성도 (데이터 기입률)")
        st.caption("캐릭터 설정, 세계관 규칙, 플롯 요약 등 필수 필드가 비어있지 않고 얼마나 촘촘히 적혀있는지 점수화합니다.")
        cols_p = st.columns(3)
        cols_p[0].metric("캐릭터 완성도", f"{phys['Characters']}%", border=True)
        cols_p[1].metric("세계관 완성도", f"{phys['Worldview']}%", border=True)
        cols_p[2].metric("플롯 노드 완성도", f"{phys['PlotNodes']}%", border=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("#### 2. 논리적 완성도 (모순 및 논리 오류율)")
        st.caption("문서 내부의 서로 다른 설정 간 발생하는 텍스트 논리 충돌 비율입니다. (가벼운 충돌: 0.3점, 완전한 대립: 1.0점)")
        cols_l = st.columns(3)
        cols_l[0].metric(
            "캐릭터 세계 논리 오류율", 
            f"{logical['Characters']['violation_rate']:.1f}%", 
            f"{logical['Characters']['error_sum']}점 감점 (비교 {logical['Characters']['total_comps']}회)", 
            delta_color="inverse", border=True
        )
        cols_l[1].metric(
            "세계관 규칙 논리 오류율", 
            f"{logical['Worldview']['violation_rate']:.1f}%", 
            f"{logical['Worldview']['error_sum']}점 감점 (비교 {logical['Worldview']['total_comps']}회)", 
            delta_color="inverse", border=True
        )
        cols_l[2].metric(
            "플롯 타임라인 논리 오류율", 
            f"{logical['PlotNodes']['violation_rate']:.1f}%", 
            f"{logical['PlotNodes']['error_sum']}점 감점 (비교 {logical['PlotNodes']['total_comps']}회)", 
            delta_color="inverse", border=True
        )
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("#### 3. 심화 논리 검증 (구조 전이 & 교차 검증)")
        st.caption("과거 아이디어를 계승하여, 플롯 홀(서사적 건너뜀)과 캐릭터 설정 및 세계관 규칙 간의 상호작용 위반 사항(트라우마 극복 지점 포함)을 검사합니다.")
        cols_l2 = st.columns(3)
        cols_l2[0].metric(
            "Phase 2: 구조적 인과율 위반율", 
            f"{logical.get('Phase2_Path', {}).get('violation_rate', 0.0):.1f}%", 
            f"{logical.get('Phase2_Path', {}).get('error_sum', 0.0)}점 감점 (비교 {logical.get('Phase2_Path', {}).get('total_comps', 0)}회)", 
            delta_color="inverse", border=True
        )
        
        # 구버전 방어코딩
        hpc_char = logical.get('Phase3_CharPlot', logical.get('Phase3_Cross', {}))
        hpc_world = logical.get('Phase3_WorldPlot', logical.get('Phase3_Cross', {}))
        
        cols_l2[1].metric(
            "Phase 3: 캐릭터 ↔ 플롯 붕괴율", 
            f"{hpc_char.get('violation_rate', 0.0):.1f}%", 
            f"{hpc_char.get('error_sum', 0.0)}점 감점 (비교 {hpc_char.get('total_comps', 0)}회)", 
            delta_color="inverse", border=True
        )
        cols_l2[2].metric(
            "Phase 3: 세계관 ↔ 플롯 붕괴율", 
            f"{hpc_world.get('violation_rate', 0.0):.1f}%", 
            f"{hpc_world.get('error_sum', 0.0)}점 감점 (비교 {hpc_world.get('total_comps', 0)}회)", 
            delta_color="inverse", border=True
        )
        
    with t_detail:
        cat_options = ["Characters", "Worldview", "PlotNodes", "Phase2_Path"]
        if "Phase3_CharPlot" in logical:
            cat_options.extend(["Phase3_CharPlot", "Phase3_WorldPlot"])
        if "Phase3_Cross" in logical:
            cat_options.append("Phase3_Cross (구버전)")
            
        sel_cat = st.selectbox("카테고리 선택", cat_options)
        actual_key = sel_cat.replace(" (구버전)", "")
        cat_data = logical.get(actual_key, {})
        
        if not cat_data["details"]:
            st.success(f"{sel_cat} 부문에는 논리적 충돌이 완벽히 제로(0)입니다! 아주 매끄럽습니다.")
        else:
            st.markdown("##### ⚠️ 위반 상세 로그 (아이디를 마우스로 올리면 세부 내용이 표기됩니다)")
            for i, d in enumerate(cat_data["details"]):
                sev_type = "🔥 치명적 충돌(1.0)" if float(d['severity']) >= 1.0 else "🟨 가벼운 비일관성(0.3)"
                
                # 식별자 디스플레이 매핑 (HTML Tooltip 주입)
                e1 = emap.get(d['entity_1_id'], {"name": d['entity_1_id'], "tooltip": ""})
                e2 = emap.get(d['entity_2_id'], {"name": d['entity_2_id'], "tooltip": ""})
                
                with st.expander(f"{i+1}. {sev_type} | {e1['name']} vs {e2['name']}"):
                    st.error(f"**충돌 탐지 이유:** {d['reason']}")
                    st.caption("충돌 객체 구조 정보:")
                    st.markdown(f"- **대상 1**: <span title='{e1['tooltip']}' style='border-bottom:1px dotted gray;cursor:help;'>{e1['name']}</span>", unsafe_allow_html=True)
                    st.markdown(f"- **대상 2**: <span title='{e2['tooltip']}' style='border-bottom:1px dotted gray;cursor:help;'>{e2['name']}</span>", unsafe_allow_html=True)
                    
            if cat_data["troublemakers"]:
                st.markdown("##### 👿 요주의 트러블메이커 순위 (누적 오류 발생량 기준)")
                tm_data = []
                for idx, (tm, score) in enumerate(cat_data["troublemakers"]):
                    t_name = emap.get(tm, {"name": tm})["name"]
                    tm_data.append({"순위": idx+1, "대상 식별자": tm, "이름 / 요약": t_name, "기여 점수": round(score, 1)})
                st.dataframe(pd.DataFrame(tm_data), use_container_width=True, hide_index=True)
                
    with t_graph:
        # 오류 자동 수정 솔루션 생성 버튼
        has_errors = (
            logical.get('Characters', {}).get('error_sum', 0) > 0 or 
            logical.get('Worldview', {}).get('error_sum', 0) > 0 or 
            logical.get('PlotNodes', {}).get('error_sum', 0) > 0 or 
            logical.get('Phase2_Path', {}).get('error_sum', 0) > 0 or 
            logical.get('Phase3_Cross', {}).get('error_sum', 0) > 0 or
            logical.get('Phase3_CharPlot', {}).get('error_sum', 0) > 0 or
            logical.get('Phase3_WorldPlot', {}).get('error_sum', 0) > 0
        )
        if has_errors:
            st.info("🚨 발견된 서사적/논리적 위반 요소가 있습니다. 고도화 처리 AI에게 이 모순을 창의적으로 해결할 방법을 물어볼까요?")
        if st.button("💡 모순 자동 수정 솔루션 제안받기", type="primary", use_container_width=True):
            suggest_prompt = "논리 검증 기능에서 구조적 위반이나 모순이 발견되었다고 들었어. 어떤 문제가 있는지 확인하고, 이를 창의적으로 해결할 수 있는 수정 플롯 노드나 설정 변경안을 직접 제안해줘."
            st.session_state.initial_prompt = {"idea": suggest_prompt}
            
            # 파일 갱신으로 Streamlit의 전체 앱 리로드(Full Rerun)를 트리거하여 다이얼로그 강제 종료
            with open("data/user_data/trigger.txt", "w") as f:
                f.write(str(datetime.now().timestamp()))
                
            st.toast("채팅 창으로 이동하여 자동 수정 해결책을 논의합니다...", icon="✅")
            st.rerun()
                
        st.markdown("---")
        st.markdown("#### ⏳ 오류율 감소 히스토리 (오류율 트래킹)")
        if len(history) < 2:
            st.info("두 번 이상의 검증 기록이 쌓여야 오류 감소 트렌드 차트를 볼 수 있습니다. 설정 수정 후 한 번 더 생성해보세요.")
        else:
            chart_data = []
            for i, h in enumerate(history):
                # 과거 파일 호환성(초기 테스트 등)을 위해 방어 코딩
                try:
                    hc = h["logical"]["Characters"]["error_sum"]
                    hw = h["logical"]["Worldview"]["error_sum"]
                    hp = h["logical"]["PlotNodes"]["error_sum"]
                    hpp = h["logical"].get("Phase2_Path", {}).get("error_sum", 0.0)
                    hpc = h["logical"].get("Phase3_Cross", {}).get("error_sum", 0.0)
                    hpc_c = h["logical"].get("Phase3_CharPlot", {}).get("error_sum", 0.0)
                    hpc_w = h["logical"].get("Phase3_WorldPlot", {}).get("error_sum", 0.0)
                    
                    chart_data.append({
                        "검증 회차": f"V-{i+1}",
                        "기초 모순 점수 (1단계)": hc + hw + hp,
                        "구조이탈 및 교차 붕괴 점수 (2,3단계)": hpp + hpc + hpc_c + hpc_w
                    })
                except KeyError:
                    pass
                    
            if chart_data:
                df = pd.DataFrame(chart_data).set_index("검증 회차")
                # 에어리어 차트나 라인 차트로 우하향을 장려 
                st.line_chart(df)
