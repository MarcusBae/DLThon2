# report_view.py
"""Standalone Streamlit UI components for rendering narrative validation reports."""

import streamlit as st
import pandas as pd

def render_validation_report(validation_results: dict):
    """
    ValidatorAgent의 validate_phase_1() 결과를 받아 
    Streamlit 대시보드(오류율, 세부 내역, 트러블메이커)로 시각화합니다.
    """
    st.markdown("### 🔍 서사 정합성(Internal Consistency) 검증 리포트")
    
    if not validation_results:
        st.info("검증 결과가 없습니다.")
        return
        
    # 상단 요약 매트릭스 (카테고리별 오류율)
    cols = st.columns(len(validation_results))
    for i, (category, stat) in enumerate(validation_results.items()):
        with cols[i]:
            st.metric(
                label=f"{category} 위반율", 
                value=f"{stat['violation_rate']:.1f}%",
                delta=f"에러 점수: {stat['error_sum']:.1f} (비교 {stat['total_comps']}회)",
                delta_color="inverse"
            )
            
    st.divider()
    
    # 탭을 활용하여 카테고리별 상세 내역 및 트러블메이커 표시
    tabs = st.tabs(list(validation_results.keys()))
    
    for tab, (category, stat) in zip(tabs, validation_results.items()):
        with tab:
            if stat["total_comps"] == 0:
                st.write("해당 카테고리에 비교할 데이터가 충분하지 않습니다.")
                continue
                
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown("##### ⚠️ 세부 충돌 내역")
                if stat["details"]:
                    # DataFrame으로 깔끔하게 표출
                    df_data = []
                    for d in stat["details"]:
                        sev_str = "🔴 심각(1.0)" if float(d.severity) == 1.0 else "🟡 가벼움(0.3)"
                        df_data.append({
                            "상태": sev_str,
                            "대상 1": d.entity_1_id,
                            "대상 2": d.entity_2_id,
                            "충돌 사유": d.reason
                        })
                    st.dataframe(pd.DataFrame(df_data), use_container_width=True, hide_index=True)
                else:
                    st.success("발견된 논리 충돌이 없습니다! 아주 매끄럽습니다.")
            
            with col2:
                st.markdown("##### 👿 요주의 트러블메이커")
                if stat["troublemakers"]:
                    tm_data = [{"ID": tm, "기여 점수": round(score, 1)} for tm, score in stat["troublemakers"]]
                    st.dataframe(pd.DataFrame(tm_data), use_container_width=True, hide_index=True)
                else:
                    st.info("문제를 일으킨 개체가 없습니다.")
