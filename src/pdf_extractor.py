import fitz  # PyMuPDF
from typing import Dict, List


def extract(pdf_path: str) -> Dict:
    """
    PDF에서 텍스트와 구조를 추출한다.

    Returns:
        {
            "pages": [{"page_num": 1, "text": "..."}],
            "sections": [{"title": "...", "page_num": 1}],
            "full_text": "..."
        }
    """
    doc = fitz.open(pdf_path)
    pages = []
    sections = []
    full_text_parts = []

    for page_num, page in enumerate(doc, start=1):
        blocks = page.get_text(
            "dict",
            flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE
        )["blocks"]

        page_text_parts = []

        for block in blocks:
            if block["type"] != 0:
                continue

            lines = block.get("lines", [])
            if not lines:
                continue

            # 첫 번째 span으로 폰트 정보 파악
            first_span = None
            for line in lines:
                spans = line.get("spans", [])
                if spans:
                    first_span = spans[0]
                    break

            block_text = _extract_block_text(block)
            if not block_text.strip():
                continue

            page_text_parts.append(block_text)

            # 섹션 제목 감지: font_size > 14 or bold flag
            if first_span:
                font_size = first_span.get("size", 12)
                font_flags = first_span.get("flags", 0)
                is_bold = bool(font_flags & 16)
                if font_size > 14 or is_bold:
                    title_text = block_text.strip()
                    if len(title_text) < 200:  # 너무 긴 텍스트는 섹션 제목 아님
                        sections.append({
                            "title": title_text,
                            "page_num": page_num
                        })

        page_text = "\n".join(page_text_parts)
        pages.append({"page_num": page_num, "text": page_text})
        full_text_parts.append(f"[Page {page_num}]\n{page_text}")

    doc.close()

    full_text = "\n\n".join(full_text_parts)
    # LLM 토큰 절약: 최대 50,000자로 제한
    if len(full_text) > 50000:
        full_text = full_text[:50000] + "\n\n[... 이하 내용 생략 ...]"

    return {
        "pages": pages,
        "sections": sections,
        "full_text": full_text
    }


def _extract_block_text(block: Dict) -> str:
    text = ""
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text += span.get("text", "")
        text += " "
    return text.strip()
