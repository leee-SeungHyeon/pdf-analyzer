import os
import json
from typing import Dict
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "gemini-2.5-flash-lite"

SYSTEM_PROMPT = """당신은 전문 문서 분석가입니다. 주어진 PDF 문서 텍스트를 분석하여 한국어로 다음 정보를 추출하세요.

반드시 아래 JSON 구조로만 응답하세요:
{
  "doc_type": "문서 유형 (예: 금융 리서치 리포트, 학술 논문, 기술 문서, 사업 계획서 등)",
  "overall_summary": "전체 문서의 핵심 내용을 3-5줄로 요약",
  "sections": [
    {"title": "섹션 제목", "summary": "해당 섹션의 핵심 내용 요약 (2-3줄)"}
  ],
  "key_data": [
    {"item": "항목명", "value": "수치/데이터 값"}
  ]
}

key_data에는 매출, 성장률, 목표가, 날짜, 통계 수치 등 중요한 데이터를 포함하세요.
sections는 실제 문서의 주요 섹션을 기반으로 작성하세요."""


def analyze(extracted: Dict, model: str = DEFAULT_MODEL, api_key: str = None) -> Dict:
    """
    추출된 PDF 텍스트를 LLM으로 분석한다.

    Args:
        extracted: pdf_extractor.extract()의 반환값
        model: Gemini 모델명
        api_key: Gemini API 키 (None이면 환경변수 사용)

    Returns:
        {
            "doc_type": "...",
            "overall_summary": "...",
            "sections": [...],
            "key_data": [...]
        }
    """
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")

    client = genai.Client(api_key=key)
    full_text = extracted["full_text"]

    try:
        result = _call_api(client, model, full_text)
        return result
    except Exception as e:
        print(f"전체 분석 실패: {e}")
        print("섹션별 분석으로 전환...")
        return _analyze_in_parts(client, model, extracted)


def _call_api(client: genai.Client, model: str, text: str) -> Dict:
    response = client.models.generate_content(
        model=model,
        contents=f"다음 문서를 분석하세요:\n\n{text}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.2,
        )
    )
    return json.loads(response.text)


def _analyze_in_parts(client: genai.Client, model: str, extracted: Dict) -> Dict:
    """토큰 초과 시 섹션별로 나눠서 분석 후 합산 (fallback)"""
    pages = extracted["pages"]
    chunk_size = max(1, len(pages) // 3)
    chunks = [pages[i:i+chunk_size] for i in range(0, len(pages), chunk_size)]

    section_summaries = []
    key_data_all = []
    doc_type = "알 수 없음"
    overall_parts = []

    for idx, chunk in enumerate(chunks):
        chunk_text = "\n\n".join(
            f"[Page {p['page_num']}]\n{p['text']}" for p in chunk
        )
        if len(chunk_text) > 15000:
            chunk_text = chunk_text[:15000]

        try:
            result = _call_api(client, model, chunk_text)
            if idx == 0:
                doc_type = result.get("doc_type", doc_type)
            overall_parts.append(result.get("overall_summary", ""))
            section_summaries.extend(result.get("sections", []))
            key_data_all.extend(result.get("key_data", []))
        except Exception as e:
            print(f"  청크 {idx+1} 분석 실패: {e}")

    # key_data 중복 제거
    seen = set()
    unique_key_data = []
    for kd in key_data_all:
        key = kd.get("item", "")
        if key not in seen:
            seen.add(key)
            unique_key_data.append(kd)

    return {
        "doc_type": doc_type,
        "overall_summary": " / ".join(p for p in overall_parts if p),
        "sections": section_summaries,
        "key_data": unique_key_data
    }
