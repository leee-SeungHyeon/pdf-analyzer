import os
import json
from typing import Dict, List
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "gemini-2.5-flash-lite"

SYSTEM_PROMPT = """당신은 전문 문서 분석가입니다. 어떤 유형의 PDF 문서든 한국어로 분석합니다.

문서 유형을 먼저 파악하고, 그에 맞게 분석하세요.
문서에 테이블이 있다면 수치를 반드시 분석에 반영하세요.

반드시 아래 JSON 구조로만 응답하세요:
{
  "doc_type": "문서 유형 (예: 금융 리서치 리포트, 학술 논문, 기술 문서, 사업 계획서, 계약서 등)",
  "overall_summary": "전체 문서의 핵심 내용을 3-5줄로 요약",
  "key_insights": [
    "핵심 인사이트를 서술형 문장으로 작성 (문서 유형에 따라 중요 수치, 결론, 주장 등 포함)"
  ],
  "sections": [
    {
      "title": "원문 섹션 제목 그대로",
      "summary": "해당 섹션 핵심 내용 2-3줄 분석 (테이블 수치가 있으면 반드시 언급)"
    }
  ]
}"""


def analyze(extracted: Dict, model: str = DEFAULT_MODEL, api_key: str = None) -> Dict:
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")

    client = genai.Client(api_key=key)

    try:
        return _call_api(client, model, extracted["full_text"])
    except Exception as e:
        print(f"전체 분석 실패: {e}")
        print("청크 분석으로 전환...")
        return _analyze_in_chunks(client, model, extracted["doc_sections"])


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


def _analyze_in_chunks(client: genai.Client, model: str, doc_sections: List[Dict]) -> Dict:
    """토큰 초과 시 청크별 분석 후 합산 (fallback)"""
    chunks = []
    current_chunk = ""
    for section in doc_sections:
        section_text = f"## {section['title']}\n{section['text']}\n"
        for table in section["tables"]:
            section_text += table + "\n"
        if len(current_chunk) + len(section_text) > 15000:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = section_text
        else:
            current_chunk += section_text
    if current_chunk:
        chunks.append(current_chunk)

    doc_type = "알 수 없음"
    overall_parts = []
    all_insights = []
    all_sections = []

    for idx, chunk in enumerate(chunks):
        try:
            result = _call_api(client, model, chunk)
            if idx == 0:
                doc_type = result.get("doc_type", doc_type)
            overall_parts.append(result.get("overall_summary", ""))
            all_insights.extend(result.get("key_insights", []))
            all_sections.extend(result.get("sections", []))
        except Exception as e:
            print(f"  청크 {idx+1} 분석 실패: {e}")

    return {
        "doc_type": doc_type,
        "overall_summary": " ".join(p for p in overall_parts if p),
        "key_insights": all_insights,
        "sections": all_sections,
    }
