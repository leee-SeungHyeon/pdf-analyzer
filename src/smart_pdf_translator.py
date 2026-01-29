# src/smart_pdf_translator.py
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from src.block_metadata_extractor import BlockMetadataExtractor
from src.llm_block_analyzer import LLMBlockAnalyzer
from translation_api import TranslationAPI


class SmartPDFTranslator:
    """
    PyMuPDF + LLM 하이브리드 방식의 스마트 PDF 번역기

    - PyMuPDF: 정확한 bbox, 텍스트 추출
    - LLM: 번역 여부, 문단 병합, 용어 보호 판단
    """

    def __init__(
        self,
        translation_api: TranslationAPI,
        llm_analyzer: LLMBlockAnalyzer,
        font_path: Optional[str] = None,
        font_dir: Optional[str] = None
    ):
        """
        Args:
            translation_api: 번역 API
            llm_analyzer: LLM 블록 분석기
            font_path: 단일 폰트 파일 경로
            font_dir: 폰트 디렉토리 경로
        """
        self.translation_api = translation_api
        self.llm_analyzer = llm_analyzer
        self.font_path = font_path
        self.font_dir = font_dir
        self.font_cache: Dict[str, int] = {}

        # 모듈 초기화
        self.metadata_extractor = BlockMetadataExtractor()

        # 폰트 발견
        self.font_variants = self._discover_fonts()

    def _discover_fonts(self) -> Dict[str, str]:
        """폰트 디렉토리에서 사용 가능한 폰트 파일 찾기"""
        fonts = {}

        if self.font_dir:
            font_dir = Path(self.font_dir)
            if font_dir.exists() and font_dir.is_dir():
                for font_file in font_dir.glob("*.ttf"):
                    name_lower = font_file.stem.lower()

                    if 'extrabold' in name_lower or 'extra-bold' in name_lower:
                        fonts['extrabold'] = str(font_file)
                    elif 'bold' in name_lower:
                        fonts['bold'] = str(font_file)
                    elif 'light' in name_lower or 'thin' in name_lower:
                        fonts['light'] = str(font_file)
                    else:
                        if 'regular' not in fonts:
                            fonts['regular'] = str(font_file)

        if self.font_path and 'regular' not in fonts:
            fonts['regular'] = self.font_path

        if fonts:
            print("Discovered Korean fonts:")
            for variant, path in fonts.items():
                print(f"  {variant}: {Path(path).name}")

        return fonts

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
        print(f"Smart PDF Translation (PyMuPDF + LLM)")
        print(f"Input:  {input_path}")
        print(f"Output: {output_path}")
        print("=" * 70)

        doc = fitz.open(str(input_path))
        total_pages = len(doc)
        print(f"\nTotal pages: {total_pages}\n")

        for page_num in range(total_pages):
            page = doc[page_num]
            print(f"[Page {page_num + 1}/{total_pages}]")

            # Step 1: PyMuPDF로 메타데이터 추출
            print("  Extracting block metadata...")
            blocks_metadata = self.metadata_extractor.extract_blocks_metadata(page)
            import ipdb; ipdb.set_trace()
            if not blocks_metadata:
                print("  No text blocks found")
                continue

            print(f"  Found {len(blocks_metadata)} text blocks")

            # Step 2: LLM으로 분석 (단일 호출)
            print("  Analyzing blocks with LLM...")
            llm_decisions = await self.llm_analyzer.analyze_blocks(blocks_metadata)

            # Step 3: 분석 결과 병합
            enriched_blocks = self._merge_metadata_and_decisions(
                blocks_metadata,
                llm_decisions
            )

            # Step 4: 번역 필요한 블록만 필터링 및 병합
            translation_units = self._create_translation_units(enriched_blocks)

            print(f"  Created {len(translation_units)} translation units")

            # Step 5: 번역
            if translation_units:
                translated_texts = await self._translate_units(
                    translation_units,
                    source_lang,
                    target_lang
                )

                # Step 6: PDF에 적용
                print("  Applying translations...")
                self._apply_translations(page, translation_units, translated_texts, doc)

            print(f"  ✓ Page {page_num + 1} completed\n")

        # 저장
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

    def _merge_metadata_and_decisions(
        self,
        metadata: List[Dict],
        decisions: List[Dict]
    ) -> List[Dict]:
        """메타데이터와 LLM 분석 결과 병합"""
        decision_map = {d["id"]: d for d in decisions}

        enriched = []
        for meta in metadata:
            decision = decision_map.get(meta["id"], {})
            enriched.append({
                **meta,
                "type": decision.get("type", "paragraph"),
                "should_translate": decision.get("should_translate", True),
                "merge_strategy": decision.get("merge_strategy", "standalone"),
                "protected_terms": decision.get("protected_terms", []),
                "reasoning": decision.get("reasoning", "")
            })

        return enriched

    def _create_translation_units(self, blocks: List[Dict]) -> List[Dict]:
        """
        번역이 필요한 블록만 선택하고 merge_strategy에 따라 병합
        """
        units = []
        i = 0

        while i < len(blocks):
            block = blocks[i]

            # 번역 불필요하면 스킵
            if not block["should_translate"]:
                print(f"    Skipping block {block['id']} ({block['type']}): {block['text'][:50]}...")
                i += 1
                continue

            if block["merge_strategy"] == "merge_next":
                # 다음 블록들과 병합
                merged_text = block["text"]
                merged_bbox = list(block["bbox"])
                merged_blocks = [block]
                protected_terms = set(block.get("protected_terms", []))

                j = i + 1
                while j < len(blocks) and blocks[j]["merge_strategy"] == "continue_previous":
                    merged_text += " " + blocks[j]["text"]
                    merged_blocks.append(blocks[j])
                    protected_terms.update(blocks[j].get("protected_terms", []))

                    # bbox 확장
                    merged_bbox[0] = min(merged_bbox[0], blocks[j]["bbox"][0])
                    merged_bbox[1] = min(merged_bbox[1], blocks[j]["bbox"][1])
                    merged_bbox[2] = max(merged_bbox[2], blocks[j]["bbox"][2])
                    merged_bbox[3] = max(merged_bbox[3], blocks[j]["bbox"][3])

                    j += 1

                units.append({
                    "text": merged_text,
                    "bbox": merged_bbox,
                    "blocks": merged_blocks,
                    "protected_terms": list(protected_terms),
                    "type": block["type"]
                })

                i = j

            elif block["merge_strategy"] == "continue_previous":
                # 이미 이전에서 처리됨
                i += 1

            else:  # standalone
                units.append({
                    "text": block["text"],
                    "bbox": block["bbox"],
                    "blocks": [block],
                    "protected_terms": block.get("protected_terms", []),
                    "type": block["type"]
                })
                i += 1

        return units

    async def _translate_units(
        self,
        units: List[Dict],
        source_lang: str,
        target_lang: str
    ) -> List[str]:
        """번역 단위들을 번역"""
        texts_to_translate = []
        all_protected_words = set()

        for unit in units:
            texts_to_translate.append(unit["text"])
            all_protected_words.update(unit.get("protected_terms", []))

        if all_protected_words:
            print(f"  Protected terms: {', '.join(all_protected_words)}")

        # 보호 단어 처리
        protected_texts = []
        mappings = []
        for text in texts_to_translate:
            protected, mapping = self._protect_words(text, all_protected_words)
            protected_texts.append(protected)
            mappings.append(mapping)

        # 번역
        print(f"  Translating {len(protected_texts)} units...")
        translated = await self.translation_api.batch_translate(
            protected_texts,
            source_lang,
            target_lang
        )

        # 보호 단어 복원
        restored = [
            self._restore_words(trans, mapping)
            for trans, mapping in zip(translated, mappings)
        ]

        return restored

    def _protect_words(self, text: str, protected_words: set) -> Tuple[str, Dict]:
        """보호 단어를 플레이스홀더로 치환"""
        mapping = {}
        modified = text

        for i, word in enumerate(sorted(protected_words)):  # 정렬로 일관성 유지
            if word in modified:
                placeholder = f"__PROTECTED_{i}__"
                modified = modified.replace(word, placeholder)
                mapping[placeholder] = word

        return modified, mapping

    def _restore_words(self, text: str, mapping: Dict) -> str:
        """플레이스홀더를 원본으로 복원"""
        restored = text
        for placeholder, original in mapping.items():
            restored = restored.replace(placeholder, original)
        return restored

    def _apply_translations(
        self,
        page: fitz.Page,
        units: List[Dict],
        translations: List[str],
        doc: fitz.Document
    ):
        """번역 결과를 PDF에 적용"""
        for unit, translated in zip(units, translations):
            if not translated or not translated.strip():
                continue

            try:
                # 배경색 감지
                target_bbox = fitz.Rect(unit["bbox"])
                background_color = self._detect_background_color(page, target_bbox)

                # 원본 영역 지우기
                for block in unit["blocks"]:
                    original_block = block["original_block"]
                    for line in original_block.get("lines", []):
                        for span in line.get("spans", []):
                            bbox = fitz.Rect(span["bbox"])
                            bbox.x0 -= 0.5
                            bbox.y0 -= 0.5
                            bbox.x1 += 0.5
                            bbox.y1 += 0.5
                            page.draw_rect(bbox, color=None, fill=background_color, overlay=True)

                # 번역된 텍스트 삽입
                first_block = unit["blocks"][0]
                fontname, fontfile = self._get_font_for_text(
                    translated,
                    first_block["font_name"],
                    first_block["font_flags"],
                    doc
                )

                # textbox로 삽입
                success = self._insert_with_textbox(
                    page,
                    translated,
                    target_bbox,
                    first_block["font_size"],
                    fontname,
                    fontfile,
                    first_block["color"]
                )

                if not success:
                    print(f"    Warning: Could not insert text for block {first_block['id']}")

            except Exception as e:
                print(f"    Warning: Failed to apply translation: {e}")

    def _detect_background_color(
        self,
        page: fitz.Page,
        bbox: fitz.Rect
    ) -> Tuple[float, float, float]:
        """배경색 감지"""
        try:
            sample_bbox = fitz.Rect(
                bbox.x0,
                bbox.y0,
                bbox.x0 + 0.5,
                bbox.y1
            )

            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat, clip=sample_bbox)

            if pix.n < 3:
                return (1.0, 1.0, 1.0)

            width = pix.width
            height = pix.height
            samples = []

            for y in range(height):
                for x in range(width):
                    try:
                        pixel = pix.pixel(x, y)
                        samples.append(pixel[:3])
                    except:
                        continue

            if samples:
                avg_r = sum(s[0] for s in samples) / len(samples) / 255.0
                avg_g = sum(s[1] for s in samples) / len(samples) / 255.0
                avg_b = sum(s[2] for s in samples) / len(samples) / 255.0
                return (avg_r, avg_g, avg_b)

        except:
            pass

        return (1.0, 1.0, 1.0)

    def _insert_with_textbox(
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
        """textbox로 텍스트 삽입 (크기 자동 조절)"""
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

                if rc > 0:
                    return True

            except Exception as e:
                if size_ratio == 0.7:
                    print(f"    Warning: textbox failed: {e}")
                continue

        return False

    def _get_font_for_text(
        self,
        text: str,
        original_font: str,
        flags: int,
        doc: fitz.Document
    ) -> Tuple[str, Optional[str]]:
        """텍스트에 적합한 폰트 선택"""
        has_korean = any('\uac00' <= char <= '\ud7a3' for char in text)

        if has_korean:
            font_file = self._select_korean_font_by_style(flags)
            if font_file:
                return self._register_font(doc, font_file)

        fontname = self._map_to_base_font(original_font)
        return (fontname, None)

    def _select_korean_font_by_style(self, flags: int) -> Optional[str]:
        """Flags에 따라 적절한 한글 폰트 선택"""
        if self.font_variants:
            if flags & 0x10:  # Bold
                if 'extrabold' in self.font_variants:
                    return self.font_variants['extrabold']
                elif 'bold' in self.font_variants:
                    return self.font_variants['bold']

            if 'regular' in self.font_variants:
                return self.font_variants['regular']

            return next(iter(self.font_variants.values()), None)

        if self.font_path and Path(self.font_path).exists():
            return self.font_path

        return None

    def _register_font(
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

    def _map_to_base_font(self, original_font: str) -> str:
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
