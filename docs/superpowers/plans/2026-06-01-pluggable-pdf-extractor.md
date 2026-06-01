# 플러그형 PDF 추출 레이어 (Marker / Docling) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PDF 추출 레이어를 `opendataloader-pdf` 단일 구현에서 Marker/Docling 두 백엔드로 갈아끼울 수 있는 구조로 교체한다.

**Architecture:** `src/extractors/` 패키지를 신설한다. `base.py`가 공용 출력 계약과 마크다운→섹션 파서를 제공하고, `marker_extractor.py`/`docling_extractor.py`가 각 도구로 "마크다운 + 이미지 파일"을 생성한 뒤 공용 파서를 호출한다. `__init__.py`의 `get_extractor(name)`가 백엔드를 디스패치한다. 출력 계약(`doc_sections`/`full_text`/`extract_dir`)은 그대로 유지되어 `llm_analyzer`·`docx_writer`는 무수정.

**Tech Stack:** Python 3.10+, marker-pdf, docling, python-docx, google-genai, pytest

관련 spec: `docs/superpowers/specs/2026-06-01-pluggable-pdf-extractor-design.md`

---

## 파일 구조

- `src/extractors/__init__.py` — 신규. `get_extractor(name)` 디스패처 + 레지스트리.
- `src/extractors/base.py` — 신규. 공용 `parse_sections`, `build_result`, 섹션 헬퍼.
- `src/extractors/marker_extractor.py` — 신규. Marker 백엔드 `extract(pdf_path)`.
- `src/extractors/docling_extractor.py` — 신규. Docling 백엔드 `extract(pdf_path)`.
- `src/pdf_extractor.py` — 삭제 (로직은 base.py로 이전).
- `main.py` — 수정. `--extractor` 인자 추가, 디스패처 호출.
- `requirements.txt` — 수정. `opendataloader-pdf` 제거, `marker-pdf`/`docling` 추가.
- `README.md` — 수정. Java 요구사항 삭제, 모델 다운로드/MPS 안내, `--extractor` 사용법.
- `tests/test_base_parser.py` — 신규. 마크다운 파서 단위 테스트.
- `tests/test_dispatcher.py` — 신규. 디스패처 단위 테스트.

### 공용 출력 계약 (모든 백엔드 동일)

```python
{
    "doc_sections": [{"title": str, "text": str, "tables": list[str], "images": list[str]}],
    "full_text": str,        # 50,000자 초과 시 잘라냄
    "extract_dir": str,
}
```

각 백엔드 모듈은 `extract(pdf_path: str) -> dict`를 노출한다.

---

## Task 1: 현재 파서에 대한 특성화 테스트 (안전망)

리팩터링 전에 기존 `_parse_sections` 동작을 테스트로 고정한다.

**Files:**
- Create: `tests/test_base_parser.py`
- Reference: `src/pdf_extractor.py:45-110`

- [ ] **Step 1: pytest 설치**

Run: `pip install pytest`
Expected: 설치 성공 (이후 `pytest --version` 동작)

- [ ] **Step 2: 기존 `_parse_sections`에 대한 실패 테스트 작성**

`tests/test_base_parser.py`:

```python
import os
from src.pdf_extractor import _parse_sections


def test_splits_on_h1_and_h2_headings(tmp_path):
    md = "# 제목 A\n본문 1\n## 제목 B\n본문 2"
    sections = _parse_sections(md, str(tmp_path))
    titles = [s["title"] for s in sections]
    assert "제목 A" in titles
    assert "제목 B" in titles


def test_h3_is_not_a_section_boundary(tmp_path):
    md = "# 제목 A\n### 소제목\n본문"
    sections = _parse_sections(md, str(tmp_path))
    assert len(sections) == 1
    assert "### 소제목" in sections[0]["text"]


def test_markdown_table_collected(tmp_path):
    md = "# 제목\n| a | b |\n|---|---|\n| 1 | 2 |"
    sections = _parse_sections(md, str(tmp_path))
    assert len(sections[0]["tables"]) == 1
    assert "| a | b |" in sections[0]["tables"][0]


def test_inline_image_collected_when_file_exists(tmp_path):
    (tmp_path / "img1.png").write_bytes(b"fake")
    md = "# 제목\n![alt](img1.png)"
    sections = _parse_sections(md, str(tmp_path))
    assert sections[0]["images"] == [os.path.join(str(tmp_path), "img1.png")]


def test_missing_image_is_skipped(tmp_path):
    md = "# 제목\n![alt](nope.png)"
    sections = _parse_sections(md, str(tmp_path))
    assert sections[0]["images"] == []
```

- [ ] **Step 3: 테스트 실행해 통과 확인 (기존 코드 대상)**

Run: `pytest tests/test_base_parser.py -v`
Expected: 5개 테스트 모두 PASS (기존 구현이 이미 이 동작을 한다)

- [ ] **Step 4: 커밋**

```bash
git add tests/test_base_parser.py
git commit -m "test: 마크다운 섹션 파서 특성화 테스트 추가"
```

---

## Task 2: `base.py`로 파서 이전 + 공용 `build_result`

**Files:**
- Create: `src/extractors/__init__.py` (빈 패키지 마커, 다음 태스크에서 채움)
- Create: `src/extractors/base.py`
- Modify: `tests/test_base_parser.py` (import 경로 변경)

- [ ] **Step 1: 빈 패키지 파일 생성**

`src/extractors/__init__.py`:

```python
```

(이 태스크에서는 빈 파일. Task 3에서 디스패처를 채운다.)

- [ ] **Step 2: `base.py` 작성 (기존 로직 이전 + build_result 추가)**

`src/extractors/base.py`:

```python
import os
import re
from typing import Dict, List

MAX_FULL_TEXT = 50000


def build_result(markdown_content: str, extract_dir: str) -> Dict:
    """마크다운에서 공용 출력 계약 dict를 만든다. 모든 백엔드가 이걸 호출한다."""
    doc_sections = parse_sections(markdown_content, extract_dir)
    full_text = markdown_content
    if len(full_text) > MAX_FULL_TEXT:
        full_text = full_text[:MAX_FULL_TEXT] + "\n\n[... 이하 내용 생략 ...]"
    return {
        "doc_sections": doc_sections,
        "full_text": full_text,
        "extract_dir": extract_dir,
    }


def parse_sections(markdown_content: str, extract_dir: str) -> List[Dict]:
    """마크다운을 섹션 단위로 파싱한다. (# / ## 만 섹션 분리)"""
    lines = markdown_content.split("\n")
    sections = []
    current = _new_section("")

    i = 0
    while i < len(lines):
        line = lines[i]

        if re.match(r'^#{1,2}\s', line):
            title = line.lstrip("#").strip()
            if current["title"] or current["text_parts"]:
                sections.append(_finalize(current))
            current = _new_section(title)
            i += 1
            continue

        if line.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1
            table_str = "\n".join(table_lines)

            img_match = re.search(r'!\[.*?\]\((.*?)\)', table_str)
            if img_match and len(table_lines) <= 3:
                img_path = os.path.join(extract_dir, img_match.group(1))
                if os.path.exists(img_path):
                    current["images"].append(img_path)
            else:
                current["tables"].append(table_str)
            continue

        img_match = re.search(r'!\[.*?\]\((.*?)\)', line)
        if img_match:
            img_path = os.path.join(extract_dir, img_match.group(1))
            if os.path.exists(img_path):
                current["images"].append(img_path)
            i += 1
            continue

        current["text_parts"].append(line)
        i += 1

    if current["title"] or current["text_parts"]:
        sections.append(_finalize(current))

    return sections


def _new_section(title: str) -> Dict:
    return {"title": title, "text_parts": [], "tables": [], "images": []}


def _finalize(section: Dict) -> Dict:
    return {
        "title": section["title"],
        "text": "\n".join(section["text_parts"]).strip(),
        "tables": section["tables"],
        "images": section["images"],
    }
```

- [ ] **Step 3: 테스트 import 경로를 base로 변경**

`tests/test_base_parser.py` 상단의 import 한 줄을 교체:

```python
from src.extractors.base import parse_sections as _parse_sections
```

(나머지 테스트 본문은 그대로. 함수 동작이 동일하므로 통과해야 한다.)

- [ ] **Step 4: 테스트 실행해 통과 확인**

Run: `pytest tests/test_base_parser.py -v`
Expected: 5개 모두 PASS

- [ ] **Step 5: `build_result` 절단 테스트 추가**

`tests/test_base_parser.py` 끝에 추가:

```python
from src.extractors.base import build_result


def test_build_result_truncates_long_text(tmp_path):
    md = "x" * 60000
    result = build_result(md, str(tmp_path))
    assert "[... 이하 내용 생략 ...]" in result["full_text"]
    assert result["extract_dir"] == str(tmp_path)
    assert "doc_sections" in result
```

- [ ] **Step 6: 테스트 실행**

Run: `pytest tests/test_base_parser.py -v`
Expected: 6개 모두 PASS

- [ ] **Step 7: 커밋**

```bash
git add src/extractors/__init__.py src/extractors/base.py tests/test_base_parser.py
git commit -m "refactor: 마크다운 파서를 extractors/base.py로 이전하고 build_result 추가"
```

---

## Task 3: 디스패처 `get_extractor(name)`

**Files:**
- Modify: `src/extractors/__init__.py`
- Create: `tests/test_dispatcher.py`

- [ ] **Step 1: 디스패처 실패 테스트 작성**

`tests/test_dispatcher.py`:

```python
import pytest
from src.extractors import get_extractor


def test_unknown_backend_raises():
    with pytest.raises(ValueError, match="알 수 없는 추출기"):
        get_extractor("nope")


def test_known_backends_return_callable():
    for name in ("marker", "docling"):
        extractor = get_extractor(name)
        assert callable(extractor)
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `pytest tests/test_dispatcher.py -v`
Expected: FAIL (`get_extractor`가 아직 없음 → ImportError)

- [ ] **Step 3: 디스패처 구현**

`src/extractors/__init__.py` (빈 파일을 다음으로 교체):

```python
import importlib
from typing import Callable, Dict

# 백엔드 이름 → (모듈경로, 함수명). 모듈은 lazy import 하여
# 한 백엔드의 무거운 의존성이 다른 백엔드 사용을 막지 않게 한다.
_BACKENDS: Dict[str, tuple] = {
    "marker": ("src.extractors.marker_extractor", "extract"),
    "docling": ("src.extractors.docling_extractor", "extract"),
}


def get_extractor(name: str) -> Callable[[str], dict]:
    if name not in _BACKENDS:
        valid = ", ".join(sorted(_BACKENDS))
        raise ValueError(f"알 수 없는 추출기: {name!r} (가능: {valid})")
    module_path, func_name = _BACKENDS[name]
    module = importlib.import_module(module_path)
    return getattr(module, func_name)
```

- [ ] **Step 4: 빈 백엔드 모듈 stub 생성 (import 성공용)**

`src/extractors/marker_extractor.py`:

```python
def extract(pdf_path: str) -> dict:
    raise NotImplementedError
```

`src/extractors/docling_extractor.py`:

```python
def extract(pdf_path: str) -> dict:
    raise NotImplementedError
```

- [ ] **Step 5: 테스트 실행해 통과 확인**

Run: `pytest tests/test_dispatcher.py -v`
Expected: 2개 PASS (`callable` 확인 — stub이라도 callable)

- [ ] **Step 6: 커밋**

```bash
git add src/extractors/__init__.py src/extractors/marker_extractor.py src/extractors/docling_extractor.py tests/test_dispatcher.py
git commit -m "feat: get_extractor 디스패처와 백엔드 stub 추가"
```

---

## Task 4: 의존성 교체 및 설치

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: `requirements.txt` 수정**

전체 내용을 다음으로 교체:

```
python-dotenv==1.1.0
google-genai==1.33.0
marker-pdf>=1.0.0
docling>=2.0.0
python-docx>=1.1.0
```

- [ ] **Step 2: 설치**

Run: `pip install -r requirements.txt`
Expected: 설치 성공 (torch·surya·pypdfium2 등 하위 의존성 자동 설치, 수 분 소요 가능). 실패 시 에러 메시지를 그대로 보고하고 중단.

- [ ] **Step 3: import 스모크 확인**

Run:
```bash
python -c "from marker.converters.pdf import PdfConverter; from marker.models import create_model_dict; from marker.output import text_from_rendered; print('marker ok')"
python -c "from docling.document_converter import DocumentConverter; print('docling ok')"
```
Expected: `marker ok` / `docling ok` 출력. import 경로가 다르면 설치된 버전의 실제 경로를 확인해 Task 5·6 코드에 반영.

- [ ] **Step 4: 커밋**

```bash
git add requirements.txt
git commit -m "build: opendataloader-pdf 제거, marker-pdf/docling 추가"
```

---

## Task 5: Marker 백엔드 구현

**Files:**
- Modify: `src/extractors/marker_extractor.py`

- [ ] **Step 1: Marker 백엔드 작성**

`src/extractors/marker_extractor.py` 전체를 교체:

```python
import os
from pathlib import Path

from src.extractors import base

_converter = None


def _get_converter():
    """Marker 모델 dict는 무거우므로 프로세스당 1회만 로드한다."""
    global _converter
    if _converter is None:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        _converter = PdfConverter(artifact_dict=create_model_dict())
    return _converter


def extract(pdf_path: str) -> dict:
    from marker.output import text_from_rendered

    pdf_stem = Path(pdf_path).stem
    extract_dir = os.path.join("output", "_extract", pdf_stem)
    os.makedirs(extract_dir, exist_ok=True)

    rendered = _get_converter()(pdf_path)
    markdown, _ext, images = text_from_rendered(rendered)

    # images: {파일명: PIL.Image}. 마크다운이 참조하는 파일명 그대로 저장하여
    # base.parse_sections의 경로 해석(extract_dir + 상대경로)과 일치시킨다.
    for name, pil_image in (images or {}).items():
        out_path = os.path.join(extract_dir, name)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        pil_image.save(out_path)

    return base.build_result(markdown, extract_dir)
```

- [ ] **Step 2: `test_input.pdf`로 스모크 실행**

Run:
```bash
python -c "from src.extractors.marker_extractor import extract; r = extract('test_input.pdf'); print('섹션', len(r['doc_sections']), '텍스트', len(r['full_text']), 'extract_dir', r['extract_dir'])"
```
Expected: 첫 실행 시 모델 다운로드 후, `섹션 N 텍스트 M extract_dir output/_extract/test_input` 형태 출력. `output/_extract/test_input/`에 이미지 파일들이 생성됨. `images` 반환 시그니처가 다르면(예: 튜플 길이) 설치 버전에 맞춰 언패킹을 조정.

- [ ] **Step 3: 디스패처 테스트 재확인**

Run: `pytest tests/test_dispatcher.py -v`
Expected: PASS

- [ ] **Step 4: 커밋**

```bash
git add src/extractors/marker_extractor.py
git commit -m "feat: Marker 추출 백엔드 구현"
```

---

## Task 6: Docling 백엔드 구현

**Files:**
- Modify: `src/extractors/docling_extractor.py`

- [ ] **Step 1: Docling 백엔드 작성**

`src/extractors/docling_extractor.py` 전체를 교체:

```python
import os
from pathlib import Path

from src.extractors import base

_converter = None


def _get_converter():
    """Docling 컨버터를 프로세스당 1회만 생성한다. 그림 이미지를 파일로 추출하도록 설정."""
    global _converter
    if _converter is None:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        pipeline_options = PdfPipelineOptions()
        pipeline_options.generate_picture_images = True
        pipeline_options.images_scale = 2.0
        _converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
    return _converter


def extract(pdf_path: str) -> dict:
    from docling_core.types.doc import ImageRefMode

    pdf_stem = Path(pdf_path).stem
    extract_dir = os.path.join("output", "_extract", pdf_stem)
    os.makedirs(extract_dir, exist_ok=True)

    result = _get_converter().convert(pdf_path)
    doc = result.document

    # 마크다운 + 이미지를 extract_dir에 떨어뜨린다. REFERENCED 모드는 이미지를
    # 아티팩트 폴더에 저장하고 마크다운이 상대경로로 참조하게 한다.
    md_path = os.path.join(extract_dir, f"{pdf_stem}.md")
    doc.save_as_markdown(Path(md_path), image_mode=ImageRefMode.REFERENCED)

    with open(md_path, "r", encoding="utf-8") as f:
        markdown = f.read()

    return base.build_result(markdown, extract_dir)
```

- [ ] **Step 2: `test_input.pdf`로 스모크 실행**

Run:
```bash
python -c "from src.extractors.docling_extractor import extract; r = extract('test_input.pdf'); print('섹션', len(r['doc_sections']), '텍스트', len(r['full_text']), 'extract_dir', r['extract_dir'])"
```
Expected: 첫 실행 시 모델 다운로드 후 통계 출력. `output/_extract/test_input/`에 `.md`와 이미지 아티팩트 생성. `save_as_markdown`/`ImageRefMode` import 경로가 설치 버전과 다르면 조정. 이미지 참조 경로가 `extract_dir` 기준 상대경로인지 확인(아니면 base.parse_sections가 이미지를 못 찾음).

- [ ] **Step 3: 커밋**

```bash
git add src/extractors/docling_extractor.py
git commit -m "feat: Docling 추출 백엔드 구현"
```

---

## Task 7: `main.py` 배선 + `pdf_extractor.py` 삭제

**Files:**
- Modify: `main.py:10`, `main.py:15-20`, `main.py:40-41`
- Delete: `src/pdf_extractor.py`

- [ ] **Step 1: import 교체**

`main.py`의 `from src.pdf_extractor import extract` 한 줄을 삭제하고, 대신:

```python
from src.extractors import get_extractor
```

(다른 import 줄 `from src.llm_analyzer import analyze` / `from src.docx_writer import write`는 그대로.)

- [ ] **Step 2: `--extractor` 인자 추가**

`main.py`의 argparse 블록에서 `--model` 인자 정의 바로 아래에 추가:

```python
    parser.add_argument("--extractor", default="marker", choices=["marker", "docling"],
                        help="PDF 추출 백엔드 (default: marker)")
```

- [ ] **Step 3: 추출 호출 교체**

`main.py`의 다음 두 줄

```python
    print(f"PDF 추출 중: {input_path}")
    extracted = extract(str(input_path))
```

을 다음으로 교체:

```python
    print(f"PDF 추출 중: {input_path} (백엔드: {args.extractor})")
    extracted = get_extractor(args.extractor)(str(input_path))
```

- [ ] **Step 4: 기존 추출기 삭제**

Run: `git rm src/pdf_extractor.py`
Expected: 파일 삭제됨

- [ ] **Step 5: 양쪽 백엔드로 엔드투엔드 실행 확인**

Run:
```bash
python main.py test_input.pdf --extractor marker -o output/_smoke_marker.docx
python main.py test_input.pdf --extractor docling -o output/_smoke_docling.docx
```
Expected: 두 명령 모두 "완료: ..." 출력하고 docx 파일 생성. (GEMINI_API_KEY가 `.env`에 있어야 함.) 잘못된 값 테스트: `python main.py test_input.pdf --extractor bogus` → argparse가 거부.

- [ ] **Step 6: 단위 테스트 전체 재확인**

Run: `pytest -v`
Expected: 모든 테스트 PASS

- [ ] **Step 7: 커밋**

```bash
git add main.py
git commit -m "feat: --extractor 플래그 추가, pdf_extractor.py 제거"
```

(Step 4의 `git rm`이 이미 삭제를 스테이징했으므로 여기서는 `main.py`만 추가하면 된다.)

---

## Task 8: 문서 업데이트 (README)

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 요구사항에서 Java 삭제 + 모델 안내 추가**

`README.md`의 "## 요구사항" 섹션을 다음으로 교체:

```markdown
## 요구사항

- Python 3.10+
- Gemini API Key ([Google AI Studio](https://aistudio.google.com/app/apikey)에서 발급)

> 추출 백엔드(Marker/Docling)는 첫 실행 시 ML 모델을 자동 다운로드한다(수백MB~1GB).
> Apple Silicon(Mac)에서는 MPS 가속을 사용한다. GPU가 없으면 CPU로 동작하며 더 느리다.
```

- [ ] **Step 2: 설치 섹션에서 Java 단계 삭제**

`README.md`의 "## 설치" 섹션에서 `brew install openjdk@17` 관련 3줄(Java 설치 블록)을 삭제하고 Python 환경 설정만 남긴다:

```markdown
## 설치

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```
```

- [ ] **Step 3: 사용법에 `--extractor` 추가**

`README.md`의 "### 로컬 실행" 코드 블록을 다음으로 교체:

```markdown
### 로컬 실행

```bash
python main.py input.pdf                          # 기본 백엔드: marker
python main.py input.pdf --extractor docling      # 추출 백엔드 선택 (marker|docling)
python main.py input.pdf -o output/result.docx
python main.py input.pdf --model gemini-2.5-flash
```

추출 백엔드는 `marker`(수식·reading order 강점)와 `docling`(표·MIT 라이선스 강점)
중 선택할 수 있다. 같은 PDF를 두 백엔드로 돌려 출력 통계(섹션·표·이미지 수)를
비교할 수 있다.
```

- [ ] **Step 4: 프로젝트 구조 블록 갱신**

`README.md`의 "## 프로젝트 구조" 코드 블록에서 추출기 부분을 갱신:

```markdown
├── src/
│   ├── extractors/      # 플러그형 추출 백엔드
│   │   ├── base.py      # 공용 출력 계약 + 마크다운→섹션 파서
│   │   ├── marker_extractor.py
│   │   └── docling_extractor.py
│   ├── llm_analyzer.py  # Gemini API 범용 분석
│   └── docx_writer.py   # docx 생성 (테이블/이미지 렌더링 포함)
```

- [ ] **Step 5: 커밋**

```bash
git add README.md
git commit -m "docs: Marker/Docling 백엔드 반영 (Java 요구사항 제거, --extractor 사용법)"
```

---

## Task 9: 최종 비교 검증 (수동)

면접 자산이 되는 직접 비교를 수행한다.

- [ ] **Step 1: 두 백엔드 통계 비교 기록**

Run:
```bash
python main.py test_input.pdf --extractor marker
python main.py test_input.pdf --extractor docling
```
각 실행이 출력하는 `섹션 N개, 테이블 M개, 이미지 K개 / 텍스트 길이 L자`를 기록.

- [ ] **Step 2: 생성된 docx 육안 비교**

`output/`의 두 결과물을 열어 확인: 멀티컬럼 본문이 읽는 순서대로 나오는지, 수식이
깨지지 않는지(LaTeX 텍스트로라도 보존), 이미지·표가 올바른 위치에 삽입됐는지.
어느 도구가 무엇을 더 잘하는지 한두 줄로 메모(면접용 트레이드오프 근거).

- [ ] **Step 3: 임시 스모크 산출물 정리**

Run: `rm -f output/_smoke_marker.docx output/_smoke_docling.docx`
Expected: Task 7에서 만든 임시 파일 제거.

(이 태스크는 커밋 없음 — 코드 변경이 아니라 검증 단계.)
