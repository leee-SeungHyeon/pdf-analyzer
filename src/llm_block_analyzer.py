# src/llm_block_analyzer.py
import json
from typing import List, Dict
from openai import AsyncOpenAI


class LLMBlockAnalyzer:
    """LLM을 사용하여 텍스트 블록을 분석하는 클래스"""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        """
        Args:
            api_key: OpenAI API 키
            model: 사용할 모델 (기본값: gpt-4o-mini)
        """
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def analyze_blocks(self, blocks_metadata: List[Dict]) -> List[Dict]:
        """
        모든 블록을 한 번의 LLM 호출로 분석

        Args:
            blocks_metadata: BlockMetadataExtractor에서 추출한 메타데이터

        Returns:
            분석 결과 리스트
            [
              {
                "id": 0,
                "type": "title|header|paragraph|caption|equation|code|table|footer|reference",
                "should_translate": true/false,
                "merge_strategy": "standalone|merge_next|continue_previous",
                "reasoning": "간단한 이유",
                "protected_terms": ["API", "GitHub", ...]
              }
            ]
        """
        if not blocks_metadata:
            return []

        # 메타데이터를 간결하게 요약 (LLM에 전달)
        blocks_summary = self._summarize_metadata(blocks_metadata)

        # LLM 호출
        prompt = self._build_analysis_prompt(blocks_summary)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )

            result = json.loads(response.choices[0].message.content)
            return result.get("blocks", [])

        except Exception as e:
            print(f"    Warning: LLM analysis failed: {e}")
            # Fallback: 모든 블록을 번역 대상으로 처리
            return self._create_fallback_decisions(blocks_metadata)

    def _summarize_metadata(self, blocks_metadata: List[Dict]) -> List[Dict]:
        """메타데이터를 LLM이 이해하기 쉽게 요약"""
        summary = []
        for b in blocks_metadata:
            summary.append({
                "id": b["id"],
                "text": b["text"][:300],  # 처음 300자만 (토큰 절약)
                "font_size": round(b["font_size"], 1),
                "is_bold": bool(b["font_flags"] & 16),
                "is_italic": bool(b["font_flags"] & 2),
                "position": b["position_in_page"],
                "x_align": b["x_position"],
                "line_count": b["line_count"],
                "has_special_chars": b["has_special_chars"],
                "char_count": b["char_count"]
            })
        return summary

    def _build_analysis_prompt(self, blocks_summary: List[Dict]) -> str:
        """LLM 분석 프롬프트 생성"""
        return f"""Analyze these text blocks from a PDF page:

{json.dumps(blocks_summary, indent=2, ensure_ascii=False)}

For each block, determine:
1. Its type (title, header, paragraph, caption, equation, code, table, footer, reference)
2. Whether it should be translated from English to Korean
3. How it relates to adjacent blocks (merge strategy)
4. Any terms that should be protected from translation

Return your analysis in the JSON format specified in the system prompt."""

    def _get_system_prompt(self) -> str:
        """시스템 프롬프트"""
        return """You are a PDF document structure analyzer for academic/technical papers.

Your task: Analyze text blocks and determine their properties.

**Block Types:**
- title: Main document title
- header: Section/subsection headers
- paragraph: Body text paragraphs
- caption: Figure/table captions
- equation: Mathematical equations
- code: Code snippets
- table: Tabular data
- footer: Page numbers, footnotes
- reference: Bibliography/citations

**Translation Decision (should_translate):**
- true: Regular English text that needs Korean translation
- false: Equations, code, URLs, proper nouns only, already translated, etc.

**Merge Strategy:**
- standalone: Independent unit (headers, equations, captions)
- merge_next: Should be merged with the following block (paragraph continues across blocks)
- continue_previous: Continuation of previous block

**Protected Terms:**
List technical terms, API names, proper nouns that should NOT be translated.
Examples: "API", "GitHub", "Docker", "TensorFlow", "REST"

**Analysis Hints:**
- Large font size (>14) + bold → likely header/title
- Italic text → likely caption or emphasis
- Special math symbols → likely equation
- Bottom position → likely footer/page number
- Single line + large font → likely header
- Multiple lines + normal font → likely paragraph
- Short text (<50 chars) + bold → likely header
- Text starting with "Figure" or "Table" → likely caption

Return JSON:
{
  "blocks": [
    {
      "id": 0,
      "type": "paragraph",
      "should_translate": true,
      "merge_strategy": "standalone",
      "reasoning": "Normal body text, standalone sentence",
      "protected_terms": ["API", "REST"]
    }
  ]
}

IMPORTANT: Return ONLY valid JSON. No extra text."""

    def _create_fallback_decisions(self, blocks_metadata: List[Dict]) -> List[Dict]:
        """LLM 호출 실패 시 폴백 결정"""
        decisions = []
        for b in blocks_metadata:
            decisions.append({
                "id": b["id"],
                "type": "paragraph",
                "should_translate": not b["has_special_chars"],  # 특수문자 있으면 번역 안함
                "merge_strategy": "standalone",
                "reasoning": "Fallback decision (LLM unavailable)",
                "protected_terms": []
            })
        return decisions
