# pdf_translator_direct.py
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import asyncio
import re

from translation_api import TranslationAPI, DummyTranslationAPI


class DirectPDFTranslator:
    """원본 PDF를 직접 수정하여 번역 (레이아웃 완벽 보존)"""
    
    def __init__(
        self,
        translation_api: TranslationAPI,
        font_path: Optional[str] = None,
        merge_strategy: str = "smart"  # "span", "block", "smart"
    ):
        """
        Args:
            translation_api: 번역 API 인스턴스
            font_path: 한글 폰트 파일 경로 (선택)
            merge_strategy: 텍스트 병합 전략
                - "span": Span 단위 (기존 방식, 문맥 없음)
                - "block": Block 단위 (문단 단위, 테이블 깨질 수 있음)
                - "smart": 스마트 병합 (문단은 병합, 테이블은 span 유지) - 권장
        """
        self.translation_api = translation_api
        self.font_path = font_path
        self.merge_strategy = merge_strategy
        self.font_cache: Dict[str, int] = {}

        print(f"Text merge strategy: {merge_strategy}")
    
    async def translate_pdf(
        self,
        input_pdf: str,
        output_pdf: str,
        source_lang: str = "en",
        target_lang: str = "ko"
    ):
        """
        PDF의 텍스트만 번역하고 레이아웃은 완벽히 유지
        """
        input_path = Path(input_pdf)
        output_path = Path(output_pdf)
        
        if not input_path.exists():
            raise FileNotFoundError(f"PDF not found: {input_pdf}")
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        print("=" * 70)
        print(f"Direct PDF Translation (Layout Preserved)")
        print(f"Input:  {input_path}")
        print(f"Output: {output_path}")
        print("=" * 70)
        
        doc = fitz.open(str(input_path))
        
        total_pages = len(doc)
        print(f"\nTotal pages: {total_pages}\n")
        
        for page_num in range(total_pages):
            page = doc[page_num]
            print(f"[Page {page_num + 1}/{total_pages}]")
            
            # 1. 텍스트 추출 (병합 전략에 따라)
            if self.merge_strategy == "span":
                text_groups = self.extract_text_by_span(page)
            elif self.merge_strategy == "block":
                text_groups = self.extract_text_by_block(page)
            elif self.merge_strategy == "smart":
                text_groups = self.extract_text_smart(page)
            else:
                raise ValueError(f"Unknown merge strategy: {self.merge_strategy}")
            print(f"  Found {len(text_groups)} text elements to translate")
            if not text_groups:
                print(f"  No text to translate")
                continue
            
            # 2. 번역
            texts_to_translate = [g['text'] for g in text_groups]
            
            print(f"  Translating...")
            translated_texts = await self.translation_api.batch_translate(
                texts_to_translate,
                source_lang,
                target_lang
            )
            
            # 3. 교체
            print(f"  Replacing text on page...")
            self.replace_text_groups(page, text_groups, translated_texts, doc)
            
            print(f"  ✓ Page {page_num + 1} completed\n")
        
        # 4. 저장
        print("Saving translated PDF...")
        doc.save(
            str(output_path),
            garbage=4,
            deflate=True,
            clean=True
        )
        doc.close()
        
        print(f"\n{'=' * 70}")
        print(f"✅ Translation complete!")
        print(f"Output saved to: {output_path}")
        print(f"{'=' * 70}\n")
    
    def extract_text_by_span(self, page: fitz.Page) -> List[dict]:
        """
        Span 단위로 추출 (기존 방식)
        장점: 위치 정확
        단점: 문맥 없음, 번역 품질 낮음
        """
        text_groups = []
        
        blocks = page.get_text(
            "dict",
            flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE
        )["blocks"]

        for block in blocks:
            if block["type"] != 0:
                continue
            
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"]
                    
                    if not text or not text.strip():
                        continue
                    
                    color_int = span.get("color", 0)
                    color_rgb = (
                        ((color_int >> 16) & 0xFF) / 255.0,
                        ((color_int >> 8) & 0xFF) / 255.0,
                        (color_int & 0xFF) / 255.0
                    )
                    
                    text_groups.append({
                        'text': text,
                        'spans': [{
                            'bbox': tuple(span["bbox"]),
                            'font': span.get("font", "helv"),
                            'size': span.get("size", 12),
                            'color': color_rgb,
                            'flags': span.get("flags", 0),
                            'origin': tuple(span["origin"])
                        }]
                    })
        
        return text_groups
    
    
    def extract_text_by_block(self, page: fitz.Page) -> List[dict]:
        """
        Block 단위로 추출 (문단 단위)
        장점: 전체 문단 문맥 유지
        단점: 위치 정확도 낮을 수 있음
        
        예: 여러 문장으로 된 문단을 한 번에 번역
        """
        text_groups = []
        
        blocks = page.get_text(
            "dict",
            flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE
        )["blocks"]
        
        for block in blocks:
            if block["type"] != 0:
                continue
            
            block_text = ""
            block_spans = []
            
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    block_text += span["text"]
                    
                    color_int = span.get("color", 0)
                    color_rgb = (
                        ((color_int >> 16) & 0xFF) / 255.0,
                        ((color_int >> 8) & 0xFF) / 255.0,
                        (color_int & 0xFF) / 255.0
                    )
                    
                    block_spans.append({
                        'bbox': tuple(span["bbox"]),
                        'font': span.get("font", "helv"),
                        'size': span.get("size", 12),
                        'color': color_rgb,
                        'flags': span.get("flags", 0),
                        'origin': tuple(span["origin"]),
                        'text': span["text"]
                    })
            
            if not block_text.strip():
                continue
            
            text_groups.append({
                'text': block_text,
                'spans': block_spans
            })
        
        return text_groups

    def extract_text_smart(self, page: fitz.Page) -> List[dict]:
        """
        스마트 병합: X 좌표가 같은 연속된 줄들은 무조건 병합

        핵심 원칙:
        - 같은 X 좌표의 연속된 줄 → 하나로 병합하여 번역 (제목, 문단 등)
        - X 좌표가 다른 줄 → 별도로 번역 (테이블, 좌우 분리 요소 등)
        """
        text_groups = []

        blocks = page.get_text(
            "dict",
            flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE
        )["blocks"]

        for block in blocks:
            if block["type"] != 0:  # 텍스트 블록이 아님
                continue

            lines = block.get("lines", [])
            if not lines:
                continue

            # 1. Block 내의 line들을 X 좌표로 그룹핑
            line_groups = self._group_lines_by_x_coordinate(lines)

            # 2. 각 그룹을 하나의 text_group으로 병합
            for line_group in line_groups:
                text_group = self._merge_line_group(line_group)
                if text_group and text_group['text'].strip():
                    text_groups.append(text_group)

        return text_groups

    def _group_lines_by_x_coordinate(self, lines: List[dict]) -> List[List[dict]]:
        """
        X 좌표가 비슷한 line들끼리 그룹핑

        예:
        Line 1: X=28.8   → Group A
        Line 2: X=208.8  → Group B
        Line 3: X=208.8  → Group B

        결과: [Group A [Line 1], Group B [Line 2, Line 3]]
        """
        if not lines:
            return []

        groups = []
        current_group = []
        current_x = None

        for line in lines:
            spans = line.get("spans", [])
            if not spans:
                continue

            line_x = spans[0]["bbox"][0]  # 첫 span의 X 좌표

            if current_x is None:
                # 첫 번째 line
                current_x = line_x
                current_group = [line]
            elif abs(line_x - current_x) <= 5:  # 5pt 이내 차이 → 같은 그룹
                current_group.append(line)
            else:
                # 새로운 그룹 시작
                if current_group:
                    groups.append(current_group)
                current_x = line_x
                current_group = [line]

        if current_group:
            groups.append(current_group)

        return groups

    def _merge_line_group(self, line_group: List[dict]) -> dict:
        """
        X 좌표가 같은 line 그룹을 하나로 병합

        - 1줄이든 10줄이든 상관없이 모두 하나로 병합
        - 전체 텍스트를 하나로 번역
        - 번역 후 전체 bbox에 렌더링
        """
        merged_text = ""
        merged_spans = []

        for line in line_group:
            for span in line.get("spans", []):
                merged_text += span["text"]

                color_int = span.get("color", 0)
                color_rgb = (
                    ((color_int >> 16) & 0xFF) / 255.0,
                    ((color_int >> 8) & 0xFF) / 255.0,
                    (color_int & 0xFF) / 255.0
                )

                merged_spans.append({
                    'bbox': tuple(span["bbox"]),
                    'font': span.get("font", "helv"),
                    'size': span.get("size", 12),
                    'color': color_rgb,
                    'flags': span.get("flags", 0),
                    'origin': tuple(span["origin"]),
                    'text': span["text"]
                })

        return {
            'text': merged_text,
            'spans': merged_spans,
            'is_merged': len(line_group) > 1  # 2줄 이상이면 병합됨
        }

    def replace_text_groups(
        self,
        page: fitz.Page,
        text_groups: List[dict],
        translated_texts: List[str],
        doc: fitz.Document
    ):
        """
        텍스트 그룹을 번역된 텍스트로 교체

        Args:
            text_groups: [{'text': '원본', 'spans': [span정보들]}]
            translated_texts: 번역된 텍스트 리스트
        """
        for group, translated in zip(text_groups, translated_texts):
            if not translated or not translated.strip():
                continue

            try:
                spans = group['spans']
                original_text = group['text']

                # 1. 모든 span 영역을 흰색으로 덮기
                for span in spans:
                    bbox = fitz.Rect(span['bbox'])
                    bbox.x0 -= 0.5
                    bbox.y0 -= 0.5
                    bbox.x1 += 0.5
                    bbox.y1 += 0.5
                    page.draw_rect(bbox, color=None, fill=(1, 1, 1), overlay=True)

                # 2. 번역된 텍스트 삽입
                is_paragraph = group.get('is_paragraph', False)
                is_merged = group.get('is_merged', False)

                if self.merge_strategy == "block" or (self.merge_strategy == "smart" and is_merged):
                    # Block 모드 또는 Smart 모드에서 병합된 경우
                    # → 전체 bbox에 번역 텍스트 삽입
                    self.insert_block_translated_text(
                        page,
                        spans,
                        translated,
                        doc
                    )
                elif self.merge_strategy == "smart" and not is_merged:
                    # Smart 모드에서 병합되지 않은 경우 (1줄)
                    # → 해당 span에 그대로 삽입
                    if len(spans) == 1:
                        self.insert_translated_text(page, translated, spans[0], doc)
                    else:
                        # 여러 span이 있으면 분배
                        self.distribute_translated_text(
                            page,
                            spans,
                            original_text,
                            translated,
                            doc
                        )
                else:
                    # Span 모드 또는 기타
                    # → 개별 span별로 텍스트 분배
                    self.distribute_translated_text(
                        page,
                        spans,
                        original_text,
                        translated,
                        doc
                    )

            except Exception as e:
                print(f"    Warning: Failed to replace text: {e}")

    def insert_block_translated_text(
        self,
        page: fitz.Page,
        spans: List[dict],
        translated_text: str,
        doc: fitz.Document
    ):
        """
        Block 모드: 문단 전체 bbox에 번역된 텍스트를 삽입

        여러 span으로 구성된 문단을 하나의 bbox로 통합하여 번역 텍스트 삽입
        """
        if not spans:
            return

        # 1. 문단 전체를 포함하는 bbox 계산
        min_x0 = min(span['bbox'][0] for span in spans)
        min_y0 = min(span['bbox'][1] for span in spans)
        max_x1 = max(span['bbox'][2] for span in spans)
        max_y1 = max(span['bbox'][3] for span in spans)

        block_bbox = fitz.Rect(min_x0, min_y0, max_x1, max_y1)

        # 2. 첫 번째 span의 스타일 정보 사용
        first_span = spans[0]
        color = first_span['color']
        fontsize = first_span['size']
        fontname = first_span.get('font', 'helv')

        # 3. 한글 폰트 선택
        fontname, fontfile = self.get_font_for_text(translated_text, fontname, doc)

        # 4. 문단 bbox에 번역 텍스트 삽입
        success = self.insert_with_textbox(
            page, translated_text, block_bbox, fontsize, fontname, fontfile, color
        )

        if not success:
            # textbox 실패 시 첫 번째 span의 origin에 삽입
            try:
                page.insert_text(
                    first_span['origin'],
                    translated_text,
                    fontsize=fontsize * 0.9,
                    fontname=fontname,
                    fontfile=fontfile,
                    color=color,
                    render_mode=0
                )
            except Exception as e:
                print(f"    Warning: insert_text failed: {e}")

    def distribute_translated_text(
        self,
        page: fitz.Page,
        spans: List[dict],
        original_text: str,
        translated_text: str,
        doc: fitz.Document
    ):
        """
        번역된 텍스트를 bbox 가로 너비에 맞춰 재분배

        새로운 접근:
        1. 전체 문단을 한 번에 번역 (문맥 유지)
        2. 각 줄(span)의 bbox 가로 너비 계산
        3. 번역 텍스트를 bbox 너비에 맞춰 줄바꿈 (단어 경계 기준)

        예:
        원본 줄1: "Target reported F4Q24 results largely consistent with pre-announced expectations (comp"
        원본 줄2: "growth of 1.5%, consensus 1.5%..."

        번역: "타겟은 F4Q24 결과를 사전 발표된 기대치와 대체로 일치하게 보고했습니다(동기 대비 성장률 1.5%..."

        → bbox1 너비만큼: "타겟은 F4Q24 결과를 사전 발표된 기대치와 대체로 일치하게 보고했습니다(동기 대비"
        → bbox2 너비만큼: "성장률 1.5%, 컨센서스 1.5%..."
        """
        if len(spans) == 1:
            # Span이 하나면 간단히 처리
            span = spans[0]
            self.insert_translated_text(
                page,
                translated_text,
                span,
                doc
            )
        else:
            # 여러 span이면 bbox 너비 기반으로 재분배
            remaining_text = translated_text

            for i, span in enumerate(spans):
                if not remaining_text.strip():
                    break

                bbox = fitz.Rect(span['bbox'])
                bbox_width = bbox.width
                fontsize = span['size']
                fontname = span.get('font', 'helv')

                # 이 bbox에 들어갈 수 있는 텍스트 추정
                # 대략적인 문자 너비: 한글 = fontsize * 0.9, 영문/숫자 = fontsize * 0.5
                estimated_text = self.estimate_text_for_width(
                    remaining_text,
                    bbox_width,
                    fontsize
                )

                if estimated_text:
                    self.insert_translated_text(
                        page,
                        estimated_text,
                        span,
                        doc
                    )

                    # 남은 텍스트 업데이트
                    remaining_text = remaining_text[len(estimated_text):].lstrip()

            # 남은 텍스트가 있으면 마지막 span에 추가로 넣기 시도
            if remaining_text.strip():
                print(f"    Warning: {len(remaining_text)} characters remaining: {remaining_text[:50]}...")

    def estimate_text_for_width(
        self,
        text: str,
        target_width: float,
        fontsize: float
    ) -> str:
        """
        주어진 bbox 너비에 들어갈 수 있는 텍스트 추정
        단어 경계를 고려하여 자연스럽게 분할
        """
        if not text:
            return ""

        # 문자별 대략적인 너비 계산
        def char_width(c):
            if '\uac00' <= c <= '\ud7a3':  # 한글
                return fontsize * 0.9
            elif c.isalpha() and ord(c) < 128:  # 영문
                return fontsize * 0.5
            elif c.isdigit():  # 숫자
                return fontsize * 0.5
            elif c in '.,;:!?':  # 구두점
                return fontsize * 0.3
            elif c == ' ':  # 공백
                return fontsize * 0.3
            elif c in '()[]{}':  # 괄호
                return fontsize * 0.4
            else:  # 기타
                return fontsize * 0.6

        current_width = 0
        best_split_pos = 0
        last_word_boundary = 0

        for i, char in enumerate(text):
            current_width += char_width(char)

            if current_width > target_width * 0.95:  # 95%까지 채우기
                # 가장 가까운 단어 경계에서 분할
                if last_word_boundary > 0:
                    return text[:last_word_boundary].rstrip()
                else:
                    # 단어 경계가 없으면 현재 위치에서 분할
                    return text[:i].rstrip() if i > 0 else text[:1]

            # 단어 경계 체크 (공백, 구두점 다음)
            if char in ' .,;:!?)]\n':
                last_word_boundary = i + 1

            best_split_pos = i + 1

        # 모든 텍스트가 들어감
        return text
    
    def insert_translated_text(
        self,
        page: fitz.Page,
        text: str,
        span: dict,
        doc: fitz.Document
    ):
        """번역된 텍스트를 span 위치에 삽입"""
        bbox = fitz.Rect(span['bbox'])
        color = span['color']
        fontsize = span['size']
        
        fontname, fontfile = self.get_font_for_text(text, span['font'], doc)
        
        success = self.insert_with_textbox(
            page, text, bbox, fontsize, fontname, fontfile, color
        )
        
        if not success:
            try:
                page.insert_text(
                    span['origin'],
                    text,
                    fontsize=fontsize * 0.9,
                    fontname=fontname,
                    fontfile=fontfile,
                    color=color,
                    render_mode=0
                )
            except Exception as e:
                print(f"    Warning: insert_text failed: {e}")
    
    def insert_with_textbox(
        self,
        page: fitz.Page,
        text: str,
        bbox: fitz.Rect,
        fontsize: float,
        fontname: str,
        fontfile: Optional[str],
        color: Tuple[float, float, float]
    ) -> bool:
        """textbox를 사용하여 텍스트 삽입"""
        for size_ratio in [1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7]:
            adjusted_size = fontsize * size_ratio
            
            try:
                rc = page.insert_textbox(
                    bbox,
                    text,
                    fontsize=adjusted_size,
                    fontname=fontname,
                    fontfile=fontfile,
                    color=color,
                    align=fitz.TEXT_ALIGN_LEFT,
                    render_mode=0
                )
                
                if rc > 0:
                    return True
                    
            except Exception as e:
                if size_ratio == 0.7:
                    print(f"    Warning: textbox insertion failed: {e}")
                continue
        
        return False
    
    def get_font_for_text(
        self,
        text: str,
        original_font: str,
        doc: fitz.Document
    ) -> Tuple[str, Optional[str]]:
        """텍스트에 적합한 폰트 선택"""
        has_korean = any('\uac00' <= char <= '\ud7a3' for char in text)
        
        if has_korean:
            if self.font_path and Path(self.font_path).exists():
                return self.register_font(doc, self.font_path)
            else:
                system_fonts = self.find_system_korean_fonts()
                if system_fonts:
                    return self.register_font(doc, system_fonts[0])
        
        fontname = self.map_to_base_font(original_font)
        return (fontname, None)
    
    def register_font(
        self,
        doc: fitz.Document,
        font_path: str
    ) -> Tuple[str, str]:
        """커스텀 폰트를 문서에 등록"""
        if font_path in self.font_cache:
            fontname = f"F{self.font_cache[font_path]}"
            return (fontname, font_path)
        
        font_index = len(self.font_cache)
        fontname = f"F{font_index}"
        self.font_cache[font_path] = font_index
        
        return (fontname, font_path)
    
    def find_system_korean_fonts(self) -> List[str]:
        """시스템에서 한글 폰트 찾기"""
        import platform
        
        system = platform.system()
        font_paths = []
        
        if system == "Darwin":  # macOS
            font_paths = [
                "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                "/Library/Fonts/AppleGothic.ttf",
                "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
            ]
        elif system == "Windows":
            font_paths = [
                "C:\\Windows\\Fonts\\malgun.ttf",
                "C:\\Windows\\Fonts\\gulim.ttc",
                "C:\\Windows\\Fonts\\batang.ttc"
            ]
        elif system == "Linux":
            font_paths = [
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                "/usr/share/fonts/truetype/nanum/NanumMyeongjo.ttf",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
            ]
        
        return [f for f in font_paths if Path(f).exists()]
    
    def map_to_base_font(self, original_font: str) -> str:
        """원본 폰트를 PyMuPDF 기본 폰트로 매핑"""
        original_lower = original_font.lower()
        
        if 'times' in original_lower or 'serif' in original_lower:
            if 'bold' in original_lower and 'italic' in original_lower:
                return 'tibi'
            elif 'bold' in original_lower:
                return 'tibo'
            elif 'italic' in original_lower:
                return 'tiit'
            return 'tiro'
        
        if 'courier' in original_lower or 'mono' in original_lower:
            if 'bold' in original_lower and ('italic' in original_lower or 'oblique' in original_lower):
                return 'cobi'
            elif 'bold' in original_lower:
                return 'cobo'
            elif 'italic' in original_lower or 'oblique' in original_lower:
                return 'coit'
            return 'cour'
        
        if 'bold' in original_lower and ('italic' in original_lower or 'oblique' in original_lower):
            return 'helv-boldoblique'
        elif 'bold' in original_lower:
            return 'helv-bold'
        elif 'italic' in original_lower or 'oblique' in original_lower:
            return 'helv-oblique'
        
        return 'helv'