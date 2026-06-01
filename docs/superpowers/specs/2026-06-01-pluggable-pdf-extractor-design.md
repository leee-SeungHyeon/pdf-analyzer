# 설계: 플러그형 PDF 추출 레이어 (Marker / Docling)

- 날짜: 2026-06-01
- 상태: 승인됨 (구현 계획 대기)

## 배경 / 동기

현재 `pdf-analyzer`는 `opendataloader-pdf`(JVM 기반) 하나로 PDF를 마크다운으로
추출한 뒤, Gemini로 분석하고 docx 리포트를 생성한다. 추출 품질을 끌어올리고
싶다 — 특히 **논문류의 reading order(읽는 순서), 수식, 이미지** 추출이 약하다.

추가로, "여러 PDF 파싱 도구를 직접 써보고 트레이드오프를 비교한 경험" 자체가
목표다. 따라서 단일 도구로 교체하는 대신, **추출기를 갈아끼울 수 있는 구조**로
만들어 같은 PDF를 여러 도구로 직접 돌려보고 체감할 수 있게 한다.

## 목표

- PDF의 텍스트·이미지·수식·reading order를 잘 추출한다.
- 추출 백엔드를 **Marker / Docling** 두 가지로 갈아끼울 수 있다.
- 같은 PDF를 두 백엔드로 직접 돌려보고 비교(체감)할 수 있다.
- LLM 분석(`llm_analyzer.py`)과 docx 생성(`docx_writer.py`)은 **수정하지 않는다**.

## 비목표 (명시적 제외)

- 자동 비교/벤치마크 리포트 생성 — 직접 돌려 통계를 눈으로 비교하는 것으로 충분.
- docx에서 LaTeX 수식 렌더링 — 수식은 텍스트(`$...$`)로 그대로 둔다.
- OCR 전용 파이프라인 — Marker/Docling이 스캔 PDF를 자동 OCR 폴백하므로 별도 처리 X.
- 추출기 인터페이스 추상화를 2개 이상 백엔드 이상으로 일반화하는 것(YAGNI).

## 도구 선택 근거

| 도구 | 수식 | reading order | 이미지/표 | Mac(MPS) | 라이선스 | 비고 |
|---|---|---|---|---|---|---|
| Marker | 강 | 강 | 강 | 좋음 | 제한적(매출 임계값)* | 수식·균형 강점 |
| Docling | 중(개선중) | 강 | 강(TableFormer) | 좋음 | MIT* | 표·라이선스·설치 강점 |

\* 라이선스 조항은 변동될 수 있고 코드/모델 가중치가 다를 수 있어, 상업·배포 전
실제 조건을 직접 확인한다. 본 프로젝트(로컬 학습/포트폴리오)에서는 두 도구 모두
사용 가능.

선정 이유: 두 도구의 트레이드오프가 가장 선명하다 — "수식은 Marker, 표·속도·
라이선스(MIT)는 Docling". 둘 다 순수 Python이고 Apple Silicon에서 동작한다.

## 아키텍처

기존 flat 구조(`src/*.py`)를 유지하되, 백엔드가 2개로 늘어난 추출 레이어만
작은 패키지로 분리한다.

```
src/
  extractors/
    __init__.py          # get_extractor(name) 디스패처 + 레지스트리
    base.py              # 출력 계약 정의 + 공용 마크다운→섹션 파서
    marker_extractor.py  # Marker → markdown + 이미지 파일 → 공용 파서
    docling_extractor.py # Docling → markdown + 이미지 파일 → 공용 파서
  llm_analyzer.py        # 무변경
  docx_writer.py         # 무변경
```

기존 `src/pdf_extractor.py`는 제거하고, 그 안의 `_parse_sections` / `_new_section`
/ `_finalize` 로직을 `base.py`로 옮겨 두 백엔드가 공유한다.

### 출력 계약 (변경 없음)

모든 백엔드는 동일한 구조를 반환한다. `llm_analyzer`·`docx_writer`가 이 형태를
기대하므로 절대 바뀌면 안 된다.

```python
{
    "doc_sections": [
        {"title": str, "text": str, "tables": list[str], "images": list[str]}
    ],
    "full_text": str,        # 50,000자 초과 시 잘라냄 (기존 로직 유지)
    "extract_dir": str,
}
```

### 데이터 흐름

```
PDF
 └─ get_extractor(name).extract(pdf_path)
      ├─ [백엔드] PDF → 마크다운 문자열 + extract_dir에 이미지 파일 저장
      └─ base.parse_sections(markdown, extract_dir) → doc_sections
   → {doc_sections, full_text, extract_dir}
 └─ llm_analyzer.analyze(...)   (무변경)
 └─ docx_writer.write(...)      (무변경)
```

**설계 핵심**: 백엔드별 책임은 "마크다운 + 이미지 파일 생성"까지만. 그 뒤 섹션
파싱은 공용 함수가 처리한다. 도구마다 다른 부분을 이 경계 안에 격리한다.

### 백엔드별 세부

- **공통**: `extract_dir = output/_extract/<pdf_stem>/`. 모델/컨버터는 모듈 레벨
  lazy-load(전역 캐시)로 두어 재호출 시 재로딩을 피한다.

- **Marker** (`marker_extractor.py`)
  - `PdfConverter(artifact_dict=create_model_dict())` 생성 (lazy, 전역 1회)
  - 변환 후 `text_from_rendered(rendered)` → `(markdown, metadata, images)`
  - `images`(파일명→PIL.Image dict)를 `extract_dir`에 저장하여 마크다운의 이미지
    참조 경로와 일치시킨다.
  - 정확한 import 경로/반환 시그니처는 구현 시 설치된 버전으로 검증.

- **Docling** (`docling_extractor.py`)
  - `DocumentConverter().convert(pdf_path)` → `result.document`
  - 이미지가 파일로 떨어지도록 설정하여 마크다운으로 내보낸다
    (예: `save_as_markdown(path, image_mode=ImageRefMode.REFERENCED)` 또는
    동등한 옵션). 이미지가 `extract_dir`에 저장되고 마크다운이 이를 참조하도록.
  - 그림 추출을 위해 변환 파이프라인 옵션(예: `generate_picture_images`)이
    필요할 수 있음 — 구현 시 설치 버전 API로 확인.

### CLI 변경 (`main.py`)

- `--extractor {marker,docling}` 인자 추가, 기본값 `marker`.
- `extract(...)` 호출을 `get_extractor(args.extractor).extract(str(input_path))`
  형태로 변경.
- 나머지 로직(통계 출력: 섹션·표·이미지 수, 텍스트 길이) 무변경 → 이 출력이 곧
  비공식 비교 지표가 된다.

### 의존성 / 문서

- `requirements.txt`: `opendataloader-pdf>=2.0.0` 제거 → `marker-pdf`, `docling` 추가.
  (torch·surya·pypdfium2 등 하위 의존성은 명시하지 않음 — 두 패키지가 끌고 옴.)
- `README.md`:
  - 요구사항에서 **Java 11+ 항목 삭제** (opendataloader 전용이었음).
  - 첫 실행 시 모델 다운로드(수백MB~1GB), Apple Silicon MPS 가속 안내 추가.
  - `--extractor` 사용법 및 두 도구 비교 의도 문서화.

## 에러 처리

- 알 수 없는 `--extractor` 값: 디스패처가 명확한 에러 메시지와 함께 종료.
- 백엔드 추출 실패: 어떤 백엔드에서 실패했는지 드러나는 메시지로 전파(조용히
  삼키지 않음). 기존 `llm_analyzer`의 청크 폴백과는 별개 — 추출 단계는 폴백 없음.
- 이미지 저장 경로가 마크다운 참조와 어긋나면 `docx_writer`가 이미지를 못 찾는다.
  → 두 백엔드 모두 "마크다운 참조 경로 = 실제 저장 경로" 불변식을 지킨다.

## 테스트 / 검증

1. **단위 테스트**: `base.parse_sections`에 대해 헤딩(`#`/`##`) 분리, 마크다운
   표 감지, 인라인/단일셀 이미지 감지가 올바른지 검증하는 작은 테스트. 픽스처는
   인라인 마크다운 문자열 사용(실제 모델 호출 없음).
2. **수동 검증**: `test_input.pdf`를 양쪽 백엔드로 실행
   - `python main.py test_input.pdf --extractor marker`
   - `python main.py test_input.pdf --extractor docling`
   - 출력 통계(섹션·표·이미지 수, 텍스트 길이) 비교, 생성된 docx를 열어 멀티컬럼
     흐름·수식·이미지가 깨지지 않는지 눈으로 확인.

## 마이그레이션 메모

- `src/pdf_extractor.py` 삭제(로직은 `extractors/`로 이전). 이를 import 하던 곳은
  `main.py` 한 곳뿐 → 디스패처 호출로 교체.
- `output/_extract/` 캐시 구조는 동일하게 유지.
