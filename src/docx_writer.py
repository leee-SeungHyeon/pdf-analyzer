from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from typing import Dict
import os


def write(analysis: Dict, output_path: str, source_filename: str = ""):
    """
    분석 결과를 docx 파일로 저장한다.

    Args:
        analysis: llm_analyzer.analyze()의 반환값
        output_path: 저장할 .docx 경로
        source_filename: 원본 PDF 파일명 (제목에 사용)
    """
    doc = Document()
    _set_default_font(doc)

    # 1. 제목
    title_text = f"문서 분석 리포트"
    if source_filename:
        title_text += f": {os.path.basename(source_filename)}"
    title = doc.add_heading(title_text, level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()

    # 2. 문서 유형
    doc_type_para = doc.add_paragraph()
    run = doc_type_para.add_run(f"문서 유형: {analysis.get('doc_type', '알 수 없음')}")
    run.bold = True
    run.font.size = Pt(13)

    doc.add_paragraph()

    # 3. 전체 요약
    doc.add_heading("전체 요약", level=1)
    summary_para = doc.add_paragraph(analysis.get("overall_summary", "요약 없음"))
    summary_para.paragraph_format.left_indent = Inches(0.3)

    doc.add_paragraph()

    # 4. 주요 수치/데이터 (표)
    key_data = analysis.get("key_data", [])
    if key_data:
        doc.add_heading("주요 수치 및 데이터", level=1)
        table = doc.add_table(rows=1, cols=2)
        table.style = "Table Grid"

        # 헤더
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "항목"
        hdr_cells[1].text = "수치/내용"
        for cell in hdr_cells:
            run = cell.paragraphs[0].runs[0]
            run.bold = True
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        # 데이터 행
        for kd in key_data:
            row_cells = table.add_row().cells
            row_cells[0].text = kd.get("item", "")
            row_cells[1].text = kd.get("value", "")

        doc.add_paragraph()

    # 5. 섹션별 요약
    sections = analysis.get("sections", [])
    if sections:
        doc.add_heading("섹션별 요약", level=1)
        for i, section in enumerate(sections, start=1):
            title_text = section.get("title", f"섹션 {i}")
            summary_text = section.get("summary", "")

            section_heading = doc.add_paragraph()
            run = section_heading.add_run(f"{i}. {title_text}")
            run.bold = True
            run.font.size = Pt(12)

            if summary_text:
                summary = doc.add_paragraph(summary_text)
                summary.paragraph_format.left_indent = Inches(0.3)

            doc.add_paragraph()

    # 저장
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    doc.save(output_path)
    print(f"저장 완료: {output_path}")


def _set_default_font(doc: Document):
    """기본 폰트 설정"""
    style = doc.styles["Normal"]
    style.font.name = "맑은 고딕"
    style.font.size = Pt(11)
