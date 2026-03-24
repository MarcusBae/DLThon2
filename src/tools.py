# tools.py
"""Tools for the narrative agent"""

import os
import requests
from datetime import datetime
from typing import Any
from langchain_core.tools import tool
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from fpdf import FPDF
import pdfplumber
from dotenv import load_dotenv



class PDF(FPDF):
    def __init__(self, font_path="./fonts/NotoSansKR.ttf"):
        super().__init__()
        self.title_text = ""
        self.font_path = font_path

    def header(self):
        """페이지 상단에 표시될 헤더"""
        if self.title_text:
            # fpdf2 normalizes font families to lowercase
            font_family = "notosans"
            if font_family in self.fonts:
                self.set_font(font_family, 'B', 16)
            else:
                self.set_font('helvetica', 'B', 16)
            
            self.cell(0, 10, self.title_text, border=0, align='C')
            self.ln(10)

    def footer(self):
        """페이지 하단에 표시될 푸터"""
        self.set_y(-15)
        font_family = "notosans"
        if font_family in self.fonts:
            self.set_font(font_family, 'I', 8)
        else:
            self.set_font('helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', align='C')

def ensure_font():
    """Ensures the NotoSansKR font is available locally."""
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf"
    font_dir = "./fonts"
    font_path = os.path.join(font_dir, "NotoSansKR.ttf")

    if not os.path.exists(font_dir):
        os.makedirs(font_dir, exist_ok=True)
    
    if not os.path.exists(font_path):
        try:
            print(f"Downloading font to {font_path}...")
            response = requests.get(font_url)
            with open(font_path, "wb") as f:
                f.write(response.content)
            print("Font downloaded successfully.")
        except Exception as e:
            print(f"Font download failed: {e}")
    return font_path

def create_structured_pdf(title, summary, content, filename):
    """
    제목, 요약, 내용을 포함한 구조화된 PDF 생성
    """
    font_path = ensure_font()

    pdf = PDF(font_path=font_path)
    pdf.title_text = title

    # Register font BEFORE adding pages to ensure header can use it
    if os.path.exists(font_path):
        try:
            # Add NotoSans for all styles with the same font file (if only one available)
            pdf.add_font("notosans", "", font_path)
            pdf.add_font("notosans", "B", font_path)
            pdf.add_font("notosans", "I", font_path)
        except Exception as e:
            print(f"Warning: Failed to register font: {e}")

    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    def set_safe_font(style='', size=12):
        if "notosans" in pdf.fonts:
            pdf.set_font("notosans", style, size)
        else:
            pdf.set_font("helvetica", style, size)

    # 작성일시
    set_safe_font(size=10)
    pdf.cell(0, 8, f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    pdf.ln(10)

    # 요약 섹션
    if summary:
        set_safe_font('B', 14)
        pdf.cell(0, 10, "Summary")
        pdf.ln(10)
        set_safe_font('', 11)
        pdf.multi_cell(0, 6, summary)
        pdf.ln(5)

    # 구분선
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    # 본문 내용
    set_safe_font('B', 14)
    pdf.cell(0, 10, "Content")
    pdf.ln(10)
    set_safe_font('', 11)
    pdf.multi_cell(0, 6, content)

    # PDF 파일 저장
    file_dir = os.path.dirname(os.path.abspath(filename))
    if not os.path.exists(file_dir):
        os.makedirs(file_dir, exist_ok=True)
    
    pdf.output(filename)
    print(f"✅ PDF saved: {filename}")
    return filename

@tool
def create_formated_pdf(title: str, summary: str, content: str, filename: str):
    """제목/요약/본문 내용을 받아 PDF 파일을 생성하고, 생성된 파일 경로를 반환하는 도구."""
    return create_structured_pdf(title, summary, content, filename)

@tool
def read_pdf(file_path: str):
    """PDF 파일 경로를 입력받아 텍스트 내용을 반환하는 도구."""
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
def write_pdf(content: str, llm: Any = None, filename: str = "output.pdf", summary: bool = True):
    """긴 텍스트 내용을 요약(선택)하여 PDF 파일로 저장하는 도구."""
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
    try:
        pdf.add_font("notosans", "", font_path)
    except:
        pass
        
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    if "notosans" in pdf.fonts:
        pdf.set_font("notosans", size=12)
    else:
        pdf.set_font("helvetica", size=12)

    for line in content.split("\n"):
        pdf.multi_cell(0, 10, line)
    
    pdf.output(filename)
    return f"{filename} 저장 완료"

if __name__ == "__main__":
    from langchain_openai import ChatOpenAI

    load_dotenv()
    test_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    test_pdf_path = "./output_test.pdf"
    try:
        create_formated_pdf.invoke({
            "title": "내 이야기 제목",
            "summary": "이 이야기의 요약입니다.",
            "content": "본문 내용이 여기에 들어갑니다.\n\n여러 줄도 가능합니다.",
            "filename": test_pdf_path
        })
        if os.path.exists(test_pdf_path):
            print("Verification: PDF successfully created with Korean support.")
            
        # Test write_pdf with llm (commented out by default to avoid API calls)
        # res = write_pdf.invoke({"content": "테스트 본문", "llm": test_llm, "filename": "./output_summary.pdf"})
        # print(res)
        
    except Exception as e:
        print(f"Verification failed: {e}")
        import traceback
        traceback.print_exc()