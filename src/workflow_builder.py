# src/workflow_builder.py
import json
import os
import sys
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# CP949 인코딩 오류 방지 (윈도우 환경 대응)
sys.stdout.reconfigure(encoding='utf-8')

def build_dynamic_theory():
    """
    Reads a new plot theory text guide (new_theory.md) and compiles it into a strict JSON object
    matching schema_theory.json. Then appends it to data/theory_plot.json.
    """
    load_dotenv()
    
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    schema_path = os.path.join(data_dir, "schema_theory.json")
    guide_path = os.path.join(data_dir, "new_theory.md")
    target_json_path = os.path.join(data_dir, "theory_plot.json")
    
    if not os.path.exists(guide_path):
        print(f"[Theory Builder] 오류: '{guide_path}' 파일이 존재하지 않습니다. 먼저 추가할 이론 텍스트를 작성해주세요.")
        return

    print("[Theory Builder] 시작: 새로운 플롯 이론 텍스트를 파싱합니다...")
    
    # 1. С키마 로드
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
        
    # 2. 새로운 플롯 이론 텍스트 로드
    with open(guide_path, "r", encoding="utf-8") as f:
        guide_text = f.read()
        
    # 3. LLM Structured Output 호출
    print("[Theory Builder] LLM 구조화 생성 요청 중... (기존 배열에 병합될 마일스톤 생성)")
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    structured_llm = llm.with_structured_output(schema)
    
    prompt = f"""
    다음 텍스트는 새로운 '스토리 플롯 구조 이론(Plot Theory)'에 대한 설명 혹은 마일스톤 가이드입니다.
    이를 분석하여 제공된 JSON 스키마(schema_theory)에 부합하는 하나의 이론 객체(theory JSON dict)를 추출해 내세요.
    - act 값은 가급적 기/승/전/결 단위로 묶어 표현하세요.
    - milestone_id는 짧고 고유한 영문 대문자+숫자 언더바 조합으로 만드세요.
    
    <New Plot Theory Text>
    {guide_text}
    </New Plot Theory Text>
    """
    
    new_theory_obj = structured_llm.invoke(prompt)
    
    # 4. 기존 theory_plot.json 읽어서 배열에 Append
    if os.path.exists(target_json_path):
        with open(target_json_path, "r", encoding="utf-8") as f:
            theory_db = json.load(f)
    else:
        theory_db = {"plot_theories": []}
        
    # 중복 체크 (동일한 theory_id가 있으면 덮어쓰기, 없으면 추가)
    existing_idx = next((i for i, t in enumerate(theory_db["plot_theories"]) if t.get("theory_id") == new_theory_obj.get("theory_id")), None)
    
    if existing_idx is not None:
        print(f"[Theory Builder] 기존 이론({new_theory_obj.get('theory_id')})을 덮어씁니다.")
        theory_db["plot_theories"][existing_idx] = new_theory_obj
    else:
        print(f"[Theory Builder] 새로운 이론({new_theory_obj.get('theory_id')})을 DB에 추가합니다.")
        theory_db["plot_theories"].append(new_theory_obj)
        
    # 5. 결과 저장
    with open(target_json_path, "w", encoding="utf-8") as f:
        json.dump(theory_db, f, ensure_ascii=False, indent=2)
        
    print(f"[Theory Builder] 성공! '{target_json_path}' 파일에 마일스톤이 동적으로 빌드/병합되었습니다.")
    
if __name__ == "__main__":
    build_dynamic_theory()
