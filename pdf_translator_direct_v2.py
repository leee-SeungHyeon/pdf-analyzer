# pdf_translator_direct_v2.py
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import asyncio

from translation_api import TranslationAPI


class DirectPDFTranslatorV2:
    """
    V2: Block 데이터를 분석하여 스마트하게 처리

    전략:
    1. blocks의 각 line을 분석
    2. X 좌표가 비슷한 연속된 line → 병합 (문단, 제목 등)
    3. X 좌표가 다른 line → 개별 처리 (테이블, 헤더 등)
    4. 개별: 원래 bbox에 번역
    5. 병합: 통합 bbox에 번역
    """

    def __init__(
        self,
        translation_api: TranslationAPI,
        font_path: Optional[str] = None,
        font_dir: Optional[str] = None,
        protected_words: Optional[List[str]] = None
    ):
        """
        Args:
            translation_api: 번역 API
            font_path: 단일 폰트 파일 경로 (레거시)
            font_dir: 폰트 디렉토리 경로 (Bold, Italic 등 자동 선택)
            protected_words: 번역하지 않고 원본 그대로 유지할 단어 리스트
        """
        self.translation_api = translation_api
        self.font_path = font_path
        self.font_dir = font_dir
        self.font_cache: Dict[str, int] = {}
        self.protected_words = protected_words or []

        # 폰트 디렉토리에서 사용 가능한 폰트 찾기
        self.font_variants = self._discover_fonts()

    def _discover_fonts(self) -> Dict[str, str]:
        """
        폰트 디렉토리에서 사용 가능한 폰트 파일 찾기

        반환 예:
        {
            'regular': 'font/NanumGothic.ttf',
            'bold': 'font/NanumGothicBold.ttf',
            'extrabold': 'font/NanumGothicExtraBold.ttf',
            'light': 'font/NanumGothicLight.ttf'
        }
        """
        fonts = {}

        # 폰트 디렉토리가 지정되어 있으면
        if self.font_dir:
            font_dir = Path(self.font_dir)
            if font_dir.exists() and font_dir.is_dir():
                for font_file in font_dir.glob("*.ttf"):
                    name_lower = font_file.stem.lower()

                    # Bold 계열
                    if 'extrabold' in name_lower or 'extra-bold' in name_lower:
                        fonts['extrabold'] = str(font_file)
                    elif 'bold' in name_lower:
                        fonts['bold'] = str(font_file)
                    # Light 계열
                    elif 'light' in name_lower or 'thin' in name_lower:
                        fonts['light'] = str(font_file)
                    # Regular (기본) - 'regular'라는 단어가 있거나, 아직 regular가 없으면 등록
                    else:
                        if 'regular' not in fonts:
                            fonts['regular'] = str(font_file)

        # 단일 폰트 파일이 지정되어 있으면 regular로 설정
        if self.font_path and 'regular' not in fonts:
            fonts['regular'] = self.font_path

        # 로깅
        if fonts:
            print("Discovered Korean fonts:")
            for variant, path in fonts.items():
                print(f"  {variant}: {Path(path).name}")

        return fonts

    def protect_words(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        보호할 단어를 플레이스홀더로 치환

        Args:
            text: 원본 텍스트

        Returns:
            (치환된 텍스트, 매핑 딕셔너리) 튜플
        """
        mapping = {}
        modified_text = text

        for i, word in enumerate(self.protected_words):
            if word in modified_text:
                placeholder = f"__PROTECTED_{i}__"
                modified_text = modified_text.replace(word, placeholder)
                mapping[placeholder] = word

        return modified_text, mapping

    def restore_words(self, text: str, mapping: Dict[str, str]) -> str:
        """
        플레이스홀더를 원본 단어로 복원

        Args:
            text: 번역된 텍스트 (플레이스홀더 포함)
            mapping: 플레이스홀더 -> 원본 단어 매핑

        Returns:
            복원된 텍스트
        """
        restored_text = text
        for placeholder, original in mapping.items():
            restored_text = restored_text.replace(placeholder, original)
        return restored_text

    async def translate_pdf(
        self,
        input_pdf: str,
        output_pdf: str,
        source_lang: str = "en",
        target_lang: str = "ko"
    ):
        """PDF 번역"""
        input_path = Path(input_pdf)
        output_path = Path(output_pdf)

        if not input_path.exists():
            raise FileNotFoundError(f"PDF not found: {input_pdf}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        print("=" * 70)
        print(f"PDF Translation V2 (Smart Merge)")
        print(f"Input:  {input_path}")
        print(f"Output: {output_path}")
        print("=" * 70)

        doc = fitz.open(str(input_path))
        total_pages = len(doc)
        print(f"\nTotal pages: {total_pages}\n")

        for page_num in range(total_pages):
            page = doc[page_num]
            print(f"[Page {page_num + 1}/{total_pages}]")

            # 1. Block 데이터 가져오기
            blocks = page.get_text(
                "dict",
                flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE
            )["blocks"]
            import ipdb; ipdb.set_trace()
            # 2. 번역 단위로 분석
            translation_units = self.analyze_blocks(blocks)
            print(f"  Found {len(translation_units)} translation units")

            if not translation_units:
                print(f"  No text to translate")
                continue

            # 3. 번역 (보호 단어 처리 포함)
            texts_to_translate = [unit['text'] for unit in translation_units]

            # 보호 단어 치환
            texts_for_translation = []
            mappings = []
            for text in texts_to_translate:
                protected_text, mapping = self.protect_words(text)
                texts_for_translation.append(protected_text)
                mappings.append(mapping)

            print(f"  Translating...")
            translated_texts = await self.translation_api.batch_translate(
                texts_for_translation,
                source_lang,
                target_lang
            )

            # 보호 단어 복원
            translated_texts = [
                self.restore_words(trans, mapping)
                for trans, mapping in zip(translated_texts, mappings)
            ]

            # 4. 페이지에 적용
            print(f"  Applying translations...")
            self.apply_translations(page, translation_units, translated_texts, doc)

            print(f"  ✓ Page {page_num + 1} completed\n")

        # 5. 저장
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

    def analyze_blocks(self, blocks: List[dict]) -> List[dict]:
        """
        Block 데이터를 분석하여 번역 단위 생성

        반환값:
        [
            {
                'text': '번역할 텍스트',
                'bbox': (x0, y0, x1, y1),  # 렌더링할 bbox
                'font': 'font_name',
                'size': 12.0,
                'color': (r, g, b),
                'spans': [원본 span 정보들]  # 원본 영역 지우기용
            }
        ]
        """
        translation_units = []

        for block in blocks:
            if block["type"] != 0:  # 텍스트 블록이 아님
                continue

            lines = block.get("lines", [])
            if not lines:
                continue

            # Block 내의 line들을 X 좌표로 그룹핑
            line_groups = self._group_lines_by_x(lines)

            # 각 그룹을 번역 단위로 변환
            for group in line_groups:
                unit = self._create_translation_unit(group)
                if unit and unit['text'].strip():
                    translation_units.append(unit)

        return translation_units

    def _group_lines_by_x(self, lines: List[dict]) -> List[List[dict]]:
        """
        X 좌표가 비슷한 line들을 임시 그룹핑 후, 문단 판단하여 최종 그룹 생성

        문단 판단 기준:
        1. 3줄 이상 & x1(오른쪽) 좌표가 1개만 다름 → 문단 병합
        2. 3줄 이상 & x1 좌표가 2개 이상 다름 → 개별 처리
        3. 2줄 & 스타일 같음 → 문단 병합
        4. 2줄 & 스타일 다름 → 개별 처리
        5. 1줄 → 개별 처리
        """
        if not lines:
            return []

        # Step 1: X 좌표(x0)로 임시 그룹핑
        temp_groups = self._group_by_x0(lines)

        # Step 2: 각 임시 그룹을 문단 판단하여 최종 그룹 생성
        final_groups = []
        for temp_group in temp_groups:
            if self._is_paragraph(temp_group):
                # 문단으로 판단 → 하나의 그룹으로 병합
                final_groups.append(temp_group)
            else:
                # 문단 아님 → 각 line을 개별 그룹으로 분리
                for line in temp_group:
                    final_groups.append([line])

        return final_groups

    def _group_by_x0(self, lines: List[dict]) -> List[List[dict]]:
        """X 좌표(x0)가 비슷한 line들끼리 임시 그룹핑"""
        if not lines:
            return []

        groups = []
        current_group = []
        current_x = None

        for line in lines:
            spans = line.get("spans", [])
            if not spans:
                continue

            line_x = spans[0]["bbox"][0]  # x0

            if current_x is None:
                current_x = line_x
                current_group = [line]
            elif abs(line_x - current_x) <= 5:  # 5pt 이내 → 같은 그룹
                current_group.append(line)
            else:
                # 새 그룹 시작
                if current_group:
                    groups.append(current_group)
                current_x = line_x
                current_group = [line]

        if current_group:
            groups.append(current_group)

        return groups

    def _is_paragraph(self, line_group: List[dict]) -> bool:
        """
        Line 그룹이 문단인지 판단

        규칙:
        1. 1줄 → False (개별)
        2. 2줄 → 스타일 체크
        3. 3줄 이상 → x1 좌표 체크
        """
        num_lines = len(line_group)

        # 규칙 5: 1줄 → 개별
        if num_lines == 1:
            return False

        # 규칙 3, 4: 2줄 → 스타일 체크
        if num_lines == 2:
            return self._has_same_style(line_group[0], line_group[1])

        # 규칙 1, 2: 3줄 이상 → x1 좌표 체크
        if num_lines >= 3:
            x1_coords = []
            for line in line_group:
                spans = line.get("spans", [])
                if spans:
                    # 마지막 span의 x1 좌표
                    last_span = spans[-1]
                    x1_coords.append(last_span["bbox"][2])

            # x1 좌표가 몇 개 다른지 체크
            unique_x1 = self._count_unique_values(x1_coords, tolerance=5)

            # 1개만 다르면 문단, 2개 이상 다르면 개별
            if unique_x1 <= 2:  # 대부분 같고 1개만 다름
                return True
            else:
                return False

        return False

    def _has_same_style(self, line1: dict, line2: dict) -> bool:
        """두 line의 스타일이 같은지 체크"""
        spans1 = line1.get("spans", [])
        spans2 = line2.get("spans", [])

        if not spans1 or not spans2:
            return False

        span1 = spans1[0]
        span2 = spans2[0]

        # 폰트 크기, flags, 색상 비교
        size_diff = abs(span1.get("size", 12) - span2.get("size", 12))
        if size_diff > 1:  # 1pt 이상 차이
            return False

        if span1.get("flags", 0) != span2.get("flags", 0):
            return False

        if span1.get("color", 0) != span2.get("color", 0):
            return False

        return True

    def _count_unique_values(self, values: List[float], tolerance: float = 5) -> int:
        """
        tolerance 범위 내에서 유사한 값들을 같은 것으로 간주하고,
        고유한 값의 개수를 반환

        예: [580, 582, 523, 581] with tolerance=5
        → [580, 582, 581]은 비슷 (1개), [523]은 다름 (1개) → 총 2개
        """
        if not values:
            return 0

        unique_groups = []

        for value in values:
            # 기존 그룹 중 tolerance 내에 있는지 확인
            found = False
            for group in unique_groups:
                if abs(value - group) <= tolerance:
                    found = True
                    break

            if not found:
                unique_groups.append(value)

        return len(unique_groups)

    def _create_translation_unit(self, line_group: List[dict]) -> dict:
        """
        Line 그룹을 번역 단위로 변환

        - 텍스트 병합 (공백 처리 포함)
        - 전체를 포함하는 bbox 계산
        - 각 span의 개별 스타일 정보 보존
        """
        if not line_group:
            return None

        merged_text = ""
        all_spans = []
        span_details = []  # 각 span의 상세 정보 저장

        # 텍스트 병합 및 span 수집
        for line in line_group:
            for span in line.get("spans", []):
                span_text = span["text"]
                text_start_idx = len(merged_text)

                # 줄 사이 공백 처리
                if merged_text and not merged_text.endswith(" ") and not span_text.startswith(" "):
                    # 하이픈으로 끝나지 않으면 공백 추가
                    if not merged_text.endswith("-"):
                        merged_text += " "
                        text_start_idx = len(merged_text)

                merged_text += span_text
                all_spans.append(span)

                # span 상세 정보 저장
                color_int = span.get("color", 0)
                color_rgb = (
                    ((color_int >> 16) & 0xFF) / 255.0,
                    ((color_int >> 8) & 0xFF) / 255.0,
                    (color_int & 0xFF) / 255.0
                )

                span_details.append({
                    'text': span_text,
                    'bbox': span["bbox"],
                    'origin': span["origin"],
                    'color': color_rgb,
                    'size': span.get("size", 12),
                    'font': span.get("font", "helv"),
                    'flags': span.get("flags", 0),
                    'text_range': (text_start_idx, len(merged_text))  # 병합된 텍스트에서의 위치
                })

        if not all_spans:
            return None

        # 전체 bbox 계산
        min_x0 = min(s["bbox"][0] for s in all_spans)
        min_y0 = min(s["bbox"][1] for s in all_spans)
        max_x1 = max(s["bbox"][2] for s in all_spans)
        max_y1 = max(s["bbox"][3] for s in all_spans)

        # 첫 번째 span 스타일 (기본값으로 사용)
        first_span = all_spans[0]

        return {
            'text': merged_text,
            'bbox': (min_x0, min_y0, max_x1, max_y1),
            'font': first_span.get("font", "helv"),
            'size': first_span.get("size", 12),
            'flags': first_span.get("flags", 0),
            'spans': all_spans,  # 원본 영역 지우기용
            'span_details': span_details  # 각 span의 상세 정보
        }

    def detect_background_color(
        self,
        page: fitz.Page,
        bbox: fitz.Rect
    ) -> Tuple[float, float, float]:
        """
        텍스트 영역의 배경색 감지

        방법:
        1. bbox 우측 0.5픽셀 영역을 이미지로 추출
        2. 해당 영역 픽셀의 평균 색상 계산
        3. RGB 값 반환

        Args:
            page: PDF 페이지
            bbox: 감지할 영역

        Returns:
            (r, g, b) 튜플 (0.0~1.0 범위)
        """
        try:
            # bbox 우측 0.5픽셀 영역 (텍스트 바로 오른쪽)
            sample_bbox = fitz.Rect(
                bbox.x1,           # 텍스트 끝
                bbox.y0,
                bbox.x1 + 0.1,       # 오른쪽 0.1픽셀
                bbox.y1
            )

            # 페이지를 이미지로 렌더링 (샘플 영역만)
            mat = fitz.Matrix(2, 2)  # 2배 확대 (더 정확한 색상 추출)
            pix = page.get_pixmap(matrix=mat, clip=sample_bbox)

            # 픽셀 데이터 추출
            if pix.n < 3:  # Grayscale
                # 그레이스케일이면 흰색 반환
                return (1.0, 1.0, 1.0)

            # 모든 픽셀 샘플링
            width = pix.width
            height = pix.height
            samples = []

            for y in range(height):
                for x in range(width):
                    try:
                        pixel = pix.pixel(x, y)
                        samples.append(pixel[:3])  # RGB만
                    except:
                        continue

            # 평균 RGB 계산
            if samples:
                avg_r = sum(s[0] for s in samples) / len(samples) / 255.0
                avg_g = sum(s[1] for s in samples) / len(samples) / 255.0
                avg_b = sum(s[2] for s in samples) / len(samples) / 255.0
                return (avg_r, avg_g, avg_b)

        except Exception as e:
            # 에러 발생 시 흰색 반환
            pass

        # 기본값: 흰색
        return (1.0, 1.0, 1.0)

    def apply_translations(
        self,
        page: fitz.Page,
        translation_units: List[dict],
        translated_texts: List[str],
        doc: fitz.Document
    ):
        """번역된 텍스트를 페이지에 적용 - 각 span을 개별적으로 렌더링"""
        for unit, translated in zip(translation_units, translated_texts):
            if not translated or not translated.strip():
                continue

            try:
                # 1. 배경색 감지
                target_bbox = fitz.Rect(unit['bbox'])
                background_color = self.detect_background_color(page, target_bbox)

                # 2. 원본 영역 지우기 (배경색으로 덮기)
                for span in unit['spans']:
                    bbox = fitz.Rect(span["bbox"])
                    bbox.x0 -= 0.5
                    bbox.y0 -= 0.5
                    bbox.x1 += 0.5
                    bbox.y1 += 0.5
                    page.draw_rect(bbox, color=None, fill=background_color, overlay=True)

                # 3. 번역된 텍스트 렌더링 (textbox 사용)
                span_details = unit.get('span_details', [])

                if span_details and len(span_details) > 0:
                    # 가장 긴 텍스트를 가진 span의 스타일 선택 (본문 우선)
                    dominant_span = max(span_details, key=lambda s: len(s['text']))

                    # 폰트 선택
                    fontname, fontfile = self.get_font_for_text(
                        translated,
                        dominant_span['font'],
                        dominant_span['flags'],
                        doc
                    )

                    # textbox로 bbox 내에서 자동 줄바꿈
                    success = self.insert_with_textbox(
                        page,
                        translated,
                        target_bbox,
                        dominant_span['size'],
                        fontname,
                        fontfile,
                        dominant_span['color']
                    )

                    if not success:
                        # textbox 실패 시 insert_text로 fallback
                        page.insert_text(
                            span_details[0]['origin'],
                            translated,
                            fontsize=dominant_span['size'] * 0.9,
                            fontname=fontname,
                            fontfile=fontfile,
                            color=dominant_span['color'],
                            render_mode=0
                        )
                else:
                    # span_details가 없으면 기존 방식 사용 (호환성)
                    fontname, fontfile = self.get_font_for_text(
                        translated,
                        unit['font'],
                        unit['flags'],
                        doc
                    )

                    first_span = unit['spans'][0]
                    color_int = first_span.get("color", 0)
                    color_rgb = (
                        ((color_int >> 16) & 0xFF) / 255.0,
                        ((color_int >> 8) & 0xFF) / 255.0,
                        (color_int & 0xFF) / 255.0
                    )

                    # textbox로 시도
                    success = self.insert_with_textbox(
                        page,
                        translated,
                        target_bbox,
                        unit['size'],
                        fontname,
                        fontfile,
                        color_rgb
                    )

                    if not success:
                        # textbox 실패 시 insert_text로 fallback
                        page.insert_text(
                            first_span["origin"],
                            translated,
                            fontsize=unit['size'] * 0.9,
                            fontname=fontname,
                            fontfile=fontfile,
                            color=color_rgb,
                            render_mode=0
                        )

            except Exception as e:
                print(f"    Warning: Failed to apply translation: {e}")

    def insert_with_textbox(
        self,
        page: fitz.Page,
        text: str,
        bbox: fitz.Rect,
        fontsize: float,
        fontname: str,
        fontfile: Optional[str],
        color: Tuple[float, float, float],
        lineheight: float = 1.3
    ) -> bool:
        """
        textbox로 텍스트 삽입 (크기 자동 조절)

        Args:
            lineheight: 줄간격 배율 (기본값 1.2 = 120%)
        """
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
                    render_mode=0,
                    lineheight=lineheight
                )

                if rc > 0:  # 성공
                    return True

            except Exception as e:
                if size_ratio == 0.7:
                    print(f"    Warning: textbox failed: {e}")
                continue

        return False

    def get_font_for_text(
        self,
        text: str,
        original_font: str,
        flags: int,
        doc: fitz.Document
    ) -> Tuple[str, Optional[str]]:
        """
        텍스트에 적합한 폰트 선택

        Args:
            text: 번역된 텍스트
            original_font: 원본 폰트 이름
            flags: 원본 폰트 플래그 (bold/italic 판단용)
            doc: PDF 문서

        Returns:
            (fontname, fontfile) 튜플
        """
        has_korean = any('\uac00' <= char <= '\ud7a3' for char in text)

        if has_korean:
            # 한글이 있으면 한글 폰트 선택
            font_file = self._select_korean_font_by_style(flags)

            if font_file:
                return self.register_font(doc, font_file)

        # 한글 폰트 없으면 영문 기본 폰트
        fontname = self.map_to_base_font(original_font)
        return (fontname, None)

    def _select_korean_font_by_style(self, flags: int) -> Optional[str]:
        """
        Flags에 따라 적절한 한글 폰트 선택

        Flags 비트:
        - 0x10 (16): Bold
        - 0x02 (2): Italic
        """
        # 폰트 디렉토리의 폰트 우선
        if self.font_variants:
            # Bold 체크 (flag & 0x10)
            if flags & 0x10:
                # Bold 폰트 선택
                if 'extrabold' in self.font_variants:
                    return self.font_variants['extrabold']
                elif 'bold' in self.font_variants:
                    return self.font_variants['bold']

            # Regular
            if 'regular' in self.font_variants:
                return self.font_variants['regular']

            # 아무거나
            return next(iter(self.font_variants.values()), None)

        # 단일 폰트 파일
        if self.font_path and Path(self.font_path).exists():
            return self.font_path

        # 시스템 폰트
        system_fonts = self.find_system_korean_fonts()
        if system_fonts:
            return system_fonts[0]

        return None

    def register_font(
        self,
        doc: fitz.Document,
        font_path: str
    ) -> Tuple[str, str]:
        """폰트 등록"""
        if font_path in self.font_cache:
            fontname = f"F{self.font_cache[font_path]}"
            return (fontname, font_path)

        font_index = len(self.font_cache)
        fontname = f"F{font_index}"
        self.font_cache[font_path] = font_index

        return (fontname, font_path)

    def find_system_korean_fonts(self) -> List[str]:
        """시스템 한글 폰트 찾기"""
        import platform

        system = platform.system()
        font_paths = []

        if system == "Darwin":  # macOS
            font_paths = [
                "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                "/Library/Fonts/AppleGothic.ttf",
            ]
        elif system == "Windows":
            font_paths = [
                "C:\\Windows\\Fonts\\malgun.ttf",
                "C:\\Windows\\Fonts\\gulim.ttc",
            ]
        elif system == "Linux":
            font_paths = [
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                "/usr/share/fonts/truetype/nanum/NanumMyeongjo.ttf",
            ]

        return [f for f in font_paths if Path(f).exists()]

    def map_to_base_font(self, original_font: str) -> str:
        """PyMuPDF 기본 폰트로 매핑"""
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
