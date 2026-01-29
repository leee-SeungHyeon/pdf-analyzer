# src/block_metadata_extractor.py
import fitz  # PyMuPDF
from typing import List, Dict


class BlockMetadataExtractor:
    """PyMuPDF에서 블록의 메타데이터를 추출하는 클래스"""

    def extract_blocks_metadata(self, page: fitz.Page) -> List[Dict]:
        """
        각 블록의 메타데이터를 추출

        Args:
            page: PDF 페이지 객체

        Returns:
            블록 메타데이터 리스트
            [
              {
                "id": 0,
                "text": "텍스트 내용",
                "bbox": [x0, y0, x1, y1],
                "font_name": "Arial-Bold",
                "font_size": 18.0,
                "font_flags": 16,  # bold, italic 등
                "color": (0, 0, 0),
                "x_position": "left|center|right",
                "width": 500,
                "height": 20,
                "line_count": 1,
                "char_count": 50,
                "has_special_chars": true,
                "position_in_page": "top|middle|bottom"
              }
            ]
        """
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        metadata_list = []
        page_height = page.rect.height
        page_width = page.rect.width

        for idx, block in enumerate(blocks):
            if block["type"] != 0:  # 텍스트 블록만 처리
                continue

            # 텍스트 추출
            text = self._extract_block_text(block)
            if not text.strip():
                continue

            # bbox
            bbox = list(block["bbox"])

            # 폰트 정보 (첫 번째 span 기준)
            first_span = self._get_first_span(block)
            font_name = first_span.get("font", "unknown")
            font_size = first_span.get("size", 12)
            font_flags = first_span.get("flags", 0)
            color_int = first_span.get("color", 0)

            # 색상 변환
            color = self._int_to_rgb(color_int)

            # 위치 분석
            x_pos = self._classify_x_position(bbox, page_width)
            y_pos = self._classify_y_position(bbox, page_height)

            # 특수 문자 체크
            has_special = self._has_special_chars(text)

            metadata_list.append({
                "id": idx,
                "text": text,
                "bbox": bbox,
                "font_name": font_name,
                "font_size": font_size,
                "font_flags": font_flags,
                "color": color,
                "x_position": x_pos,
                "width": bbox[2] - bbox[0],
                "height": bbox[3] - bbox[1],
                "line_count": len(block.get("lines", [])),
                "char_count": len(text),
                "has_special_chars": has_special,
                "position_in_page": y_pos,
                "original_block": block  # 나중에 렌더링할 때 필요
            })

        return metadata_list

    def _extract_block_text(self, block: Dict) -> str:
        """블록에서 텍스트를 추출"""
        text = ""
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text += span.get("text", "")
            text += " "
        return text.strip()

    def _get_first_span(self, block: Dict) -> Dict:
        """블록의 첫 번째 span을 반환"""
        lines = block.get("lines", [])
        if lines and lines[0].get("spans"):
            return lines[0]["spans"][0]
        return {}

    def _int_to_rgb(self, color_int: int) -> tuple:
        """정수 색상을 RGB 튜플로 변환"""
        r = ((color_int >> 16) & 0xFF) / 255.0
        g = ((color_int >> 8) & 0xFF) / 255.0
        b = (color_int & 0xFF) / 255.0
        return (r, g, b)

    def _classify_x_position(self, bbox: List[float], page_width: float) -> str:
        """좌우 위치 분류"""
        center_x = (bbox[0] + bbox[2]) / 2
        if center_x < page_width * 0.33:
            return "left"
        elif center_x > page_width * 0.67:
            return "right"
        return "center"

    def _classify_y_position(self, bbox: List[float], page_height: float) -> str:
        """상하 위치 분류"""
        center_y = (bbox[1] + bbox[3]) / 2
        if center_y < page_height * 0.25:
            return "top"
        elif center_y > page_height * 0.75:
            return "bottom"
        return "middle"

    def _has_special_chars(self, text: str) -> bool:
        """수식 기호, 특수문자 포함 여부 체크"""
        # 수학 기호, 그리스 문자 등
        special_chars = set("∑∫∂√±×÷≈≠≤≥∞αβγδθλπσωΔΩ∈∉⊂⊃∪∩⊕⊗")
        return any(c in special_chars for c in text)
