import os
import re
from typing import Dict, List

MAX_FULL_TEXT = 50000


def build_result(markdown_content: str, extract_dir: str) -> Dict:
    """마크다운에서 공용 출력 계약 dict를 만든다. 모든 백엔드가 이걸 호출한다."""
    doc_sections = parse_sections(markdown_content, extract_dir)
    full_text = markdown_content
    if len(full_text) > MAX_FULL_TEXT:
        full_text = full_text[:MAX_FULL_TEXT] + "\n\n[... 이하 내용 생략 ...]"
    return {
        "doc_sections": doc_sections,
        "full_text": full_text,
        "extract_dir": extract_dir,
    }


def parse_sections(markdown_content: str, extract_dir: str) -> List[Dict]:
    """마크다운을 섹션 단위로 파싱한다. (# / ## 만 섹션 분리)"""
    lines = markdown_content.split("\n")
    sections = []
    current = _new_section("")

    i = 0
    while i < len(lines):
        line = lines[i]

        if re.match(r'^#{1,2}\s', line):
            title = line.lstrip("#").strip()
            if current["title"] or current["text_parts"]:
                sections.append(_finalize(current))
            current = _new_section(title)
            i += 1
            continue

        if line.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1
            table_str = "\n".join(table_lines)

            img_match = re.search(r'!\[.*?\]\((.*?)\)', table_str)
            if img_match and len(table_lines) <= 3:
                img_path = os.path.join(extract_dir, img_match.group(1))
                if os.path.exists(img_path):
                    current["images"].append(img_path)
            else:
                current["tables"].append(table_str)
            continue

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
