import os
import json
from typing import Dict, List
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "gemini-2.5-flash-lite"

SYSTEM_PROMPT = """You are a professional document analyst. Analyze any type of PDF document and respond in Korean.

First identify the document type, then analyze accordingly.
If tables are present, you must reflect their numerical data in the analysis.

All output values must be written in Korean.
Respond strictly in the following JSON structure:
{
  "doc_type": "detected document type (e.g. research report, academic paper, technical doc, business plan, contract)",
  "overall_summary": "3-5 sentence summary of the entire document",
  "key_insights": [
    "key insight as a full sentence (include important figures, conclusions, or claims depending on doc type)"
  ],
  "sections": [
    {
      "title": "exact section title from the original document",
      "summary": "2-3 sentence analysis of the section (must mention table figures if present)"
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
