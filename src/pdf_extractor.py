import opendataloader_pdf
import os
import re
from pathlib import Path
from typing import Dict, List


def extract(pdf_path: str) -> Dict:
    """
    PDF에서 텍스트, 섹션, 테이블, 이미지를 추출한다.

    Returns:
        {
            "doc_sections": [{"title": "...", "text": "...", "tables": [...], "images": [...]}],
            "full_text": "...",
            "extract_dir": "..."
        }
    """
    pdf_stem = Path(pdf_path).stem
    extract_dir = os.path.join("output", "_extract", pdf_stem)

    opendataloader_pdf.convert(
        input_path=[pdf_path],
        output_dir=extract_dir,
        format="markdown"
    )

    md_path = os.path.join(extract_dir, f"{pdf_stem}.md")
    with open(md_path, "r", encoding="utf-8") as f:
        markdown_content = f.read()

    doc_sections = _parse_sections(markdown_content, extract_dir)

    full_text = markdown_content
    if len(full_text) > 50000:
        full_text = full_text[:50000] + "\n\n[... 이하 내용 생략 ...]"

    return {
        "doc_sections": doc_sections,
        "full_text": full_text,
        "extract_dir": extract_dir,
    }


def _parse_sections(markdown_content: str, extract_dir: str) -> List[Dict]:
    """마크다운을 섹션 단위로 파싱한다."""
    lines = markdown_content.split("\n")
    sections = []
    current = _new_section("")

    i = 0
    while i < len(lines):
        line = lines[i]

        # 헤딩 감지 (# 또는 ## 만 섹션 분리, ### 이하는 본문 처리)
        if re.match(r'^#{1,2}\s', line):
            title = line.lstrip("#").strip()
            if current["title"] or current["text_parts"]:
                sections.append(_finalize(current))
            current = _new_section(title)
            i += 1
            continue

        # 테이블 감지 (연속된 | 로 시작하는 라인)
        if line.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1
            table_str = "\n".join(table_lines)

            # 이미지를 감싼 단일 셀 테이블인지 확인
            img_match = re.search(r'!\[.*?\]\((.*?)\)', table_str)
            if img_match and len(table_lines) <= 3:
                img_path = os.path.join(extract_dir, img_match.group(1))
                if os.path.exists(img_path):
                    current["images"].append(img_path)
            else:
                current["tables"].append(table_str)
            continue

        # 인라인 이미지 감지
        img_match = re.search(r'!\[.*?\]\((.*?)\)', line)
        if img_match:
            img_path = os.path.join(extract_dir, img_match.group(1))
            if os.path.exists(img_path):
                current["images"].append(img_path)
            i += 1
            continue

        current["text_parts"].append(line)
        i += 1

    if current["title"] or current["text_parts"]:
        sections.append(_finalize(current))

    return sections


def _new_section(title: str) -> Dict:
    return {"title": title, "text_parts": [], "tables": [], "images": []}


def _finalize(section: Dict) -> Dict:
    return {
        "title": section["title"],
        "text": "\n".join(section["text_parts"]).strip(),
        "tables": section["tables"],
        "images": section["images"],
    }
