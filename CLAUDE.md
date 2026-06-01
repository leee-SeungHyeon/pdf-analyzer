# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

임의의 PDF를 입력받아 Gemini API로 분석하고 한국어 분석 리포트(`.docx`)를 생성하는
범용 CLI 도구. 문서 유형 자동 감지 → 전체 요약 → 핵심 인사이트 → 섹션별 분석을
수행하며, PDF 원본의 테이블·이미지는 결과물에 그대로 삽입한다.

## 명령어

```bash
# 환경 설정
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # .env에 GEMINI_API_KEY 입력

# 실행
python main.py input.pdf                          # output/<stem>_분석_<YYYYMMDD>.docx
python main.py input.pdf -o output/result.docx    # 출력 경로 지정
python main.py input.pdf --model gemini-2.5-flash # 모델 변경 (기본 gemini-2.5-flash-lite)

# Docker
docker build -t pdf-analyzer .
docker run --rm -e GEMINI_API_KEY=$KEY \
  -v /path/to/input.pdf:/input/input.pdf -v $(pwd)/output:/app/output \
  pdf-analyzer /input/input.pdf
```

아직 테스트 스위트는 없다.

## 아키텍처

`main.py`가 오케스트레이션하는 3단계 단방향 파이프라인이다:

```
PDF → extract (src/extractors/) → analyze (src/llm_analyzer.py) → write (src/docx_writer.py) → .docx
```

1. **추출** (`src/extractors/`): 플러그형 백엔드. `get_extractor(name)` 디스패처가
   `marker`(marker-pdf) 또는 `docling`(docling) 백엔드의 `extract`를 반환한다
   (`--extractor`, 기본 marker). 각 백엔드는 PDF를 마크다운+이미지로 만들고,
   공용 `base.build_result()`가 마크다운을 `#`/`##` 헤딩 기준 섹션으로 파싱한다.
   결과는 `output/_extract/<stem>/`에 저장. 백엔드는 모두 동일한 출력 계약을 지킨다.
2. **분석** (`llm_analyzer.py`): Gemini에 전체 텍스트를 보내 고정된 JSON 스키마
   (`doc_type`/`overall_summary`/`key_insights`/`sections`)로 분석 결과를 받는다.
   토큰 초과 등으로 전체 분석 실패 시, 섹션을 ~15,000자 청크로 쪼개 분석 후
   합산하는 폴백(`_analyze_in_chunks`)이 있다.
3. **생성** (`docx_writer.py`): 분석 결과를 docx로 렌더링. 섹션별로
   "LLM 줄글 → 원본 테이블 → 원본 이미지" 순. LLM이 돌려준 섹션 제목과 추출된
   원문 섹션을 정확/부분 일치로 매칭(`_find_doc_section`)해 표·이미지를 끼워 넣는다.

### 핵심 불변식: 추출기 출력 계약

세 단계를 잇는 가장 중요한 약속은 추출기가 반환하는 dict 구조다. 이걸 바꾸면
`llm_analyzer`와 `docx_writer` 양쪽이 깨진다 — 추출 로직을 손볼 때 반드시 유지할 것:

```python
{
    "doc_sections": [{"title": str, "text": str, "tables": list[str], "images": list[str]}],
    "full_text": str,        # 50,000자 초과 시 잘라냄
    "extract_dir": str,
}
```

- `tables`는 마크다운 표 문자열, `images`는 파일 경로 문자열. **이미지 경로
  불변식**: 마크다운이 참조하는 경로 == 실제 저장 경로여야 `docx_writer`가 이미지를
  찾는다.
- `full_text`는 분석용(원문 마크다운), `doc_sections`는 청크 폴백·docx 렌더링용.
- **암묵적 결합 주의**: `docx_writer`는 표·이미지를 `_find_doc_section`으로 LLM 섹션
  제목 ↔ 추출 섹션 제목을 매칭해 재부착한다. 추출기가 섹션을 잘게 쪼개 제목이 LLM
  요약 제목과 안 맞으면 표·이미지가 docx에서 누락된다 (Docling에서 관측됨). 새 추출기
  추가 시 이 매칭 가정을 점검할 것.

### LLM 분석 규칙

- 시스템 프롬프트(`llm_analyzer.py`)는 영어로 작성하되 **모든 출력값은 한국어**로
  강제한다. JSON 스키마를 바꾸면 `docx_writer`의 키 접근부도 함께 맞춰야 한다.
- 한글 폰트는 docx에서 "맑은 고딕"으로 설정된다(`_set_default_font`).

## 실행 환경 / 모델

- 추출 백엔드는 첫 실행 시 ML 모델을 자동 다운로드(수백MB~1GB)하고, 매 실행마다
  모델을 로드한다. Apple Silicon에서 torch가 MPS로 멈추면 `TORCH_DEVICE=cpu`를
  앞에 붙여 실행한다(추출 ~6분/CPU).
- 설계·구현 기록: `docs/superpowers/specs|plans/2026-06-01-*pluggable*.md`
