# tools.py
"""Tools for the narrative agent"""

import os
import re
import json
import requests
import random
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Literal, Mapping, Sequence
from dataclasses import dataclass, asdict
from langchain_core.tools import tool
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from fpdf import FPDF
import pdfplumber
from PIL import Image
from dotenv import load_dotenv

warnings.filterwarnings("ignore")

# ==========================================
# 1. 데이터 모델 (Data Models)
# ==========================================

@dataclass
class WorldConstant:
    """세계관 내 불변하는 환경 변수"""
    name: str
    value: str

@dataclass
class WorldRule:
    """세계관의 물리적/사회적 규칙과 위반 조건"""
    rule_title: str
    description: str
    forbidden_events: List[str]

@dataclass
class Worldview:
    """전체 세계관 데이터 구조"""
    world_id: str
    genre: str
    features: dict
    constants: List[WorldConstant]
    rules: List[WorldRule]

    @classmethod
    def from_dict(cls, data: dict) -> "Worldview":
        constants = [WorldConstant(**c) for c in data.get("constants", [])]
        rules = [WorldRule(**r) for r in data.get("rules", [])]
        return cls(
            world_id=data["world_id"],
            genre=data["genre"],
            features=data.get("features", {}),
            constants=constants,
            rules=rules,
        )

    def to_dict(self) -> dict:
        return {
            "world_id": self.world_id,
            "genre": self.genre,
            "features": self.features,
            "constants": [asdict(c) for c in self.constants],
            "rules": [asdict(r) for r in self.rules],
        }

@dataclass
class CharacterRelationship:
    """캐릭터 간의 관계 정보"""
    category: str
    relationship_title: str
    target_char_id: str
    emotions: List[str]

@dataclass
class Character:
    """개별 캐릭터 데이터 구조"""
    char_id: str
    name: str
    char_role: str
    dominant_trait: str
    forbidden_action: str
    initial_lack: Optional[str] = None
    char_relationship: Optional[List[CharacterRelationship]] = None

@dataclass
class CharacterSet:
    """작품에 등장하는 캐릭터들의 집합"""
    characters: List[Character]

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterSet":
        chars: List[Character] = []
        for raw in data.get("characters", []):
            rels_raw = raw.get("char_relationship", [])
            rels = [CharacterRelationship(**r) for r in rels_raw] if rels_raw else None
            ch = Character(
                char_id=raw["char_id"],
                name=raw["name"],
                char_role=raw["char_role"],
                dominant_trait=raw["dominant_trait"],
                forbidden_action=raw["forbidden_action"],
                initial_lack=raw.get("initial_lack"),
                char_relationship=rels,
            )
            chars.append(ch)
        return cls(characters=chars)

    def to_dict(self) -> dict:
        result = []
        for ch in self.characters:
            ch_dict = asdict(ch)
            ch_dict = {k: v for k, v in ch_dict.items() if v is not None}
            result.append(ch_dict)
        return {"characters": result}

# --- Plot 관련 모델 ---
@dataclass
class MainCharacters:
    Protagonist_ID: str
    Antagonist_ID: Optional[str] = None

@dataclass
class CoreDeficiency:
    Immediate_Lack: Optional[str] = None
    Fundamental_Lack: Optional[str] = None

@dataclass
class Tags:
    Topics: List[str]
    Polarity: Literal["Positive", "Negative", "Neutral"]

@dataclass
class ValidationStatus:
    Violation_Rate: str
    Is_Valid: bool

@dataclass
class PlotMetadata:
    Story_ID: str
    Title: str
    Author: str
    Created_At: str
    Updated_At: str
    Applied_Structure: str
    Main_Characters: MainCharacters
    Core_Deficiency: Optional[CoreDeficiency] = None
    Tags: Optional[Tags] = None
    Validation_Status: Optional[ValidationStatus] = None

@dataclass
class StateUpdate:
    Target_Char_ID: str
    Target_Trait: str
    New_Value: str

@dataclass
class ValidationData:
    Required_Trait: Optional[str]
    Effect_Type: Literal["NONE", "SETTING_CHANGE", "WORLD_CHANGE"]
    State_Update: Optional[StateUpdate] = None

@dataclass
class CausalLinks:
    Causes: Optional[List[str]] = None
    Effects: Optional[List[str]] = None

@dataclass
class PlotNode:
    Node_ID: str
    Sequence_Index: float
    Function_ID: str
    Content: str
    Involved_Characters: List[str]
    Background_World_ID: str
    Validation_Data: ValidationData
    Causal_Links: Optional[CausalLinks] = None
    Memo: Optional[str] = None

@dataclass
class Plot:
    """전체 플롯 데이터 구조"""
    Plot_Metadata: PlotMetadata
    Plot_Nodes: List[PlotNode]

    @classmethod
    def from_dict(cls, data: dict) -> "Plot":
        pm = data["Plot_Metadata"]
        mc = MainCharacters(**pm["Main_Characters"])
        core_def = CoreDeficiency(**pm["Core_Deficiency"]) if "Core_Deficiency" in pm else None
        tags = Tags(**pm["Tags"]) if "Tags" in pm else None
        vs = ValidationStatus(**pm["Validation_Status"]) if "Validation_Status" in pm else None

        meta = PlotMetadata(
            Story_ID=pm["Story_ID"], Title=pm["Title"], Author=pm["Author"],
            Created_At=pm["Created_At"], Updated_At=pm["Updated_At"],
            Applied_Structure=pm["Applied_Structure"], Main_Characters=mc,
            Core_Deficiency=core_def, Tags=tags, Validation_Status=vs,
        )

        nodes: List[PlotNode] = []
        for raw in data.get("Plot_Nodes", []):
            cl = CausalLinks(**raw["Causal_Links"]) if "Causal_Links" in raw else None
            vu = raw["Validation_Data"]
            su = StateUpdate(**vu["State_Update"]) if "State_Update" in vu and vu["State_Update"] is not None else None
            vd = ValidationData(
                Required_Trait=vu.get("Required_Trait"),
                Effect_Type=vu["Effect_Type"],
                State_Update=su,
            )
            node = PlotNode(
                Node_ID=raw["Node_ID"], Sequence_Index=raw["Sequence_Index"],
                Function_ID=raw["Function_ID"], Content=raw["Content"],
                Involved_Characters=raw.get("Involved_Characters", []),
                Background_World_ID=raw["Background_World_ID"],
                Validation_Data=vd, Causal_Links=cl, Memo=raw.get("Memo"),
            )
            nodes.append(node)
        return cls(Plot_Metadata=meta, Plot_Nodes=nodes)

    def to_dict(self) -> dict:
        data = asdict(self)
        def drop_none(obj):
            if isinstance(obj, dict):
                return {k: drop_none(v) for k, v in obj.items() if v is not None}
            if isinstance(obj, list):
                return [drop_none(v) for v in obj]
            return obj
        return drop_none(data)

# ==========================================
# 2. 유틸리티 함수 (Utility Functions)
# ==========================================

def load_json(path: str) -> dict:
    """임의의 JSON 파일 로더 (UTF-8-sig 지원)"""
    file_path = Path(path).resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"파일 없음: {file_path}")
    with open(file_path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def load_schema_data(path: str) -> dict:
    """
    주석(//, /* */) 및 특수 기호($)가 포함된 schema_data.json 파일을 정제하여 로드합니다.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
        
    text = Path(path).read_text(encoding="utf-8")
    text = text.replace("\r\n", "\n")

    # 1) "$schema" 포함된 줄 제거
    lines = text.split("\n")
    lines = [ln for ln in lines if '"$schema"' not in ln]
    text = "\n".join(lines)

    # 2) 블록 주석 제거: /* ... */
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    # 3) 라인 주석 제거: // ...
    text = re.sub(r"//.*", "", text)

    # 4) $ 로 시작하는 라인 제거 (설명용 가짜 속성)
    text = re.sub(r"^\s*\$.*$", "", text, flags=re.MULTILINE)

    # 5) 제어문자 제거 (\n, \t 제외)
    text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]", "", text)

    # 6) 빈 줄 제거 및 최종 파싱
    lines = [ln for ln in text.split("\n") if ln.strip() != ""]
    text = "\n".join(lines)

    return json.loads(text)

def print_schema_tree(data: Any, indent: int = 0, max_list_items: int = 3):
    """dict / list 중첩 구조를 트리 형태로 출력 (디버깅용)"""
    prefix = "  " * indent
    if isinstance(data, Mapping):
        for key, value in data.items():
            print(f"{prefix}- {key} ({type(value).__name__})")
            print_schema_tree(value, indent + 1, max_list_items)
    elif isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        for i, item in enumerate(data[:max_list_items]):
            print(f"{prefix}- [idx {i}] ({type(item).__name__})")
            print_schema_tree(item, indent + 1, max_list_items)
        if len(data) > max_list_items:
            print(f"{prefix}  ... (+{len(data) - max_list_items} more)")

# ==========================================
# 3. PDF 생성 보조 기능 (PDF Generation Helpers)
# ==========================================

def _ensure_font_file(font_path: str):
    """NotoSansKR 폰트 파일이 있는지 확인하고 없으면 다운로드합니다."""
    os.makedirs(os.path.dirname(font_path), exist_ok=True)
    if not os.path.exists(font_path):
        font_url = "https://github.com/google/fonts/raw/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf"
        try:
            print(f"Downloading font to {font_path}...")
            resp = requests.get(font_url)
            resp.raise_for_status()
            with open(font_path, "wb") as f:
                f.write(resp.content)
            print("Font downloaded successfully.")
        except Exception as e:
            print(f"Font download failed: {e}")

def _register_font(pdf: FPDF, font_path: str):
    """PDF 인스턴스에 NotoSans 폰트를 등록합니다."""
    if os.path.exists(font_path):
        try:
            pdf.add_font("notosans", "", font_path)
            pdf.add_font("notosans", "B", font_path)
            pdf.add_font("notosans", "I", font_path)
        except Exception as e:
            print(f"Warning: Failed to register font: {e}")

def _add_summary(pdf: FPDF, summary: str):
    """요약 섹션 추가"""
    if not summary: return
    font_family = "notosans" if "notosans" in pdf.fonts else "helvetica"
    pdf.set_font(font_family, "B", 14)
    pdf.cell(0, 10, "Summary", ln=1)
    pdf.set_font(font_family, "", 11)
    pdf.multi_cell(0, 6, summary)
    pdf.ln(5)

def _add_content(pdf: FPDF, content: str):
    """본문 섹션 추가"""
    if not content: return
    font_family = "notosans" if "notosans" in pdf.fonts else "helvetica"
    pdf.set_font(font_family, "B", 14)
    pdf.cell(0, 10, "Content", ln=1)
    pdf.set_font(font_family, "", 11)
    pdf.multi_cell(0, 6, content)
    pdf.ln(5)

def _add_bullet_list(pdf: FPDF, bullets: List[str]):
    """불릿 리스트 섹션 추가"""
    if not bullets: return
    font_family = "notosans" if "notosans" in pdf.fonts else "helvetica"
    pdf.set_font(font_family, "B", 14)
    pdf.cell(0, 10, "List", ln=1)
    pdf.set_font(font_family, "", 11)
    for item in bullets:
        pdf.cell(5)
        pdf.cell(5, 6, u"\u2022") # Bullet character
        pdf.cell(2)
        pdf.multi_cell(0, 6, item)
    pdf.ln(3)

def _add_table(pdf: FPDF, table: List[List[str]]):
    """표(Table) 섹션 추가"""
    if not table or not table[0]: return
    font_family = "notosans" if "notosans" in pdf.fonts else "helvetica"
    pdf.set_font(font_family, "B", 14)
    pdf.cell(0, 10, "Table", ln=1)
    pdf.set_font(font_family, "", 10)
    
    col_count = len(table[0])
    page_width = pdf.w - 20
    col_width = page_width / col_count
    row_height = 8

    for row in table:
        start_y = pdf.get_y()
        for col_idx, cell in enumerate(row):
            x = 10 + col_idx * col_width
            pdf.set_xy(x, start_y)
            pdf.multi_cell(col_width, row_height, str(cell), border=1)
        pdf.set_y(start_y + row_height)
    pdf.ln(5)

def _add_flowchart(pdf: FPDF, flowchart_path: Optional[str]):
    """이미지(플로우차트) 필드 추가"""
    if not flowchart_path or not os.path.exists(flowchart_path): return
    pdf.add_page()
    font_family = "notosans" if "notosans" in pdf.fonts else "helvetica"
    pdf.set_font(font_family, "B", 14)
    pdf.cell(0, 10, "Flowchart", ln=1)
    pdf.ln(5)

    max_w, max_h = pdf.w - 30, pdf.h - 50
    img = Image.open(flowchart_path)
    iw, ih = img.size
    scale = min(max_w / iw, max_h / ih)
    w, h = iw * scale, ih * scale
    x, y = (pdf.w - w) / 2, pdf.get_y()
    pdf.image(flowchart_path, x=x, y=y, w=w, h=h)

# ==========================================
# 4. 데이터 로더 / 세이버 (Loaders & Savers)
# ==========================================

def load_worldview(path: str) -> Worldview:
    """세계관 정보를 로드하여 Worldview 객체로 반환"""
    return Worldview.from_dict(load_json(path))

def save_worldview(world: Worldview, path: str):
    """Worldview 객체를 JSON 파일로 저장"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(world.to_dict(), f, ensure_ascii=False, indent=2)

def load_characters(path: str) -> CharacterSet:
    """캐릭터 정보를 로드하여 CharacterSet 객체로 반환"""
    return CharacterSet.from_dict(load_json(path))

def save_characters(charset: CharacterSet, path: str):
    """CharacterSet 객체를 JSON 파일로 저장"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(charset.to_dict(), f, ensure_ascii=False, indent=2)

def load_plot(path: str) -> Plot:
    """플롯 정보를 로드하여 Plot 객체로 반환"""
    return Plot.from_dict(load_json(path))

def save_plot(plot: Plot, path: str):
    """Plot 객체를 JSON 파일로 저장"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plot.to_dict(), f, ensure_ascii=False, indent=2)

# ==========================================
# 5. 서사 에이전트 도구 (Narrative Agent Tools)
# ==========================================

class PDF(FPDF):
    """
    고급 PDF 생성을 위한 커스텀 FPDF 클래스.
    헤더, 푸터 및 한글 폰트 지원을 포함합니다.
    """
    def __init__(self, font_path="./fonts/NotoSansKR.ttf"):
        super().__init__()
        self.title_text = ""
        self.font_path = font_path

    def header(self):
        """페이지 상단 헤더: 제목 표시"""
        if self.title_text:
            font_family = "notosans" if "notosans" in self.fonts else "helvetica"
            self.set_font(font_family, 'B', 16)
            self.cell(0, 10, self.title_text, border=0, align='C')
            self.ln(10)

    def footer(self):
        """페이지 하단 푸터: 페이지 번호 표시"""
        self.set_y(-15)
        font_family = "notosans" if "notosans" in self.fonts else "helvetica"
        self.set_font(font_family, 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', align='C')

def ensure_font():
    """NotoSansKR 폰트 파일 가용성 확인 및 다운로드"""
    font_path = "./fonts/NotoSansKR.ttf"
    _ensure_font_file(font_path)
    return font_path

def create_structured_pdf(title, summary, content, filename):
    """
    제목, 요약, 본문을 포함한 기본적인 구조화된 PDF 생성
    """
    font_path = ensure_font()
    pdf = PDF(font_path=font_path)
    pdf.title_text = title
    _register_font(pdf, font_path)

    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    def set_safe_font(style='', size=12):
        font_family = "notosans" if "notosans" in pdf.fonts else "helvetica"
        pdf.set_font(font_family, style, size)

    # 작성일시
    set_safe_font(size=10)
    pdf.cell(0, 8, f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    pdf.ln(10)

    # 요약 및 본문 섹션 추가
    _add_summary(pdf, summary)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)
    _add_content(pdf, content)

    # 출력 저장
    file_dir = os.path.dirname(os.path.abspath(filename))
    os.makedirs(file_dir, exist_ok=True)
    pdf.output(filename)
    print(f"✅ PDF saved: {filename}")
    return filename

@tool
def create_formated_pdf(title: str, summary: str, content: str, filename: str):
    """제목, 요약, 본문을 받아 구조화된 PDF 파일을 생성하고 경로를 반환합니다."""
    return create_structured_pdf(title, summary, content, filename)

@tool
def read_pdf(file_path: str):
    """PDF 파일에서 텍스트를 추출하여 반환합니다. (pdfplumber 사용)"""
    try:
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip() if text.strip() else "❌ PDF에서 텍스트를 추출할 수 없습니다."
    except Exception as e:
        return f"❌ PDF 읽기 오류: {str(e)}"

@tool
def write_pdf_tool(
    content: str,
    filename: str,
    title: str = "",
    summary: str = "",
    bullets: Optional[List[str]] = None,
    table: Optional[List[List[str]]] = None,
    flowchart_path: Optional[str] = None,
):
    """
    고급 PDF 작성 도구:
    - 제목, 요약, 본문 서식 지원
    - 불릿 리스트(bullets) 및 테이블(table) 삽입 지원
    - 플로우차트 등의 이미지(flowchart_path) 삽입 지원
    """
    font_path = "./fonts/NotoSansKR.ttf"
    _ensure_font_file(font_path)

    pdf = PDF(font_path=font_path)
    pdf.title_text = title or filename.replace(".pdf", "")
    _register_font(pdf, font_path)

    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # 작성 시간
    font_family = "notosans" if "notosans" in pdf.fonts else "helvetica"
    pdf.set_font(font_family, 'I', 10)
    pdf.cell(0, 8, f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=1)
    pdf.ln(3)

    # 섹션별 데이터 추가
    _add_summary(pdf, summary)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)
    _add_content(pdf, content)
    _add_bullet_list(pdf, bullets or [])
    _add_table(pdf, table or [])
    _add_flowchart(pdf, flowchart_path)

    # 결과 저장
    file_dir = os.path.dirname(os.path.abspath(filename))
    os.makedirs(file_dir, exist_ok=True)
    pdf.output(filename)
    return filename

@tool
def write_pdf(content: str, llm: Any = None, filename: str = "output.pdf", summary: bool = True):
    """긴 텍스트를 LLM으로 요약(선택)하여 PDF로 저장합니다."""
    if summary:
        if not llm:
            return "❌ 오류: 요약 기능을 사용하려면 llm 인스턴스가 제공되어야 합니다."
            
        prompt = PromptTemplate.from_template("""
                당신은 보고서를 작성하는 어시스턴트입니다. 당신에겐 문서 모음이 제공되고 이를 잘 분석하여 보고서를 작성하여야 합니다.
                아래의 content는 문서 모음입니다. 문서의 제목, 본문을 잘 판단하고 정리하여 요약합니다.
                항상 구조화된 출력을 제공하세요.
                항상 마지막엔 인사이트도 첨부합니다.

                content : {content}
                """)
        chain = prompt | llm
        content = chain.invoke({"content": content}).content

    font_path = ensure_font()
    pdf = FPDF()
    _register_font(pdf, font_path)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    font_family = "notosans" if "notosans" in pdf.fonts else "helvetica"
    pdf.set_font(font_family, size=12)

    for line in content.split("\n"):
        pdf.multi_cell(0, 10, line)
    
    pdf.output(filename)
    return f"{filename} 저장 완료"

# ==========================================
# 6. 테스트 코드 (Verification)
# ==========================================

if __name__ == "__main__":
    from langchain_openai import ChatOpenAI
    load_dotenv()
    test_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    test_pdf_path = "./output_test.pdf"
    try:
        # 1. 일반 PDF 생성 테스트
        create_formated_pdf.invoke({
            "title": "테스트 제목",
            "summary": "테스트 요약입니다.",
            "content": "본문 테스트 내용입니다.",
            "filename": test_pdf_path
        })
        
        # 2. 고급 PDF 생성 테스트 (표, 리스트 포함)
        write_pdf_tool.invoke({
            "title": "고급 리포트 테스트",
            "filename": "./advanced_test.pdf",
            "bullets": ["첫 번째 항목", "두 번째 항목"],
            "table": [["항목", "내용"], ["A", "100"], ["B", "200"]],
            "content": "이 리포트는 표와 리스트를 포함합니다."
        })
        
        if os.path.exists("./advanced_test.pdf"):
            print("✅ Verification: Advanced PDF tools are working correctly.")
            
    except Exception as e:
        print(f"❌ Verification failed: {e}")