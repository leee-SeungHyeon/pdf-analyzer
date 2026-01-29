# Smart PDF Translator

LLM을 활용한 지능형 PDF 번역 시스템

## 특징

### 🧠 LLM 기반 지능형 분석
- **자동 문서 구조 인식**: 제목, 본문, 수식, 코드, 캡션 자동 구분
- **번역 여부 자동 판단**: 수식, 코드는 번역하지 않고 보존
- **문맥 기반 병합**: 여러 블록에 걸친 문단을 자동으로 병합
- **용어 보호**: 기술 용어, 고유명사 자동 감지 및 보호

### ⚡ PyMuPDF + LLM 하이브리드
- **정확한 좌표**: PyMuPDF로 정확한 bbox 추출
- **의미 분석**: LLM으로 블록의 의미와 역할 판단
- **비용 효율**: Vision API 불필요, Text API만 사용

## 아키텍처

```
src/
├── block_metadata_extractor.py   # PyMuPDF로 블록 메타데이터 추출
├── llm_block_analyzer.py          # LLM으로 블록 분석
├── smart_pdf_translator.py        # 통합 번역 시스템
└── __init__.py
```

### 플로우

```
PDF 페이지
    ↓
[BlockMetadataExtractor]
PyMuPDF로 블록 추출 + 메타데이터
    ↓
블록 리스트 (text, bbox, font, position, ...)
    ↓
[LLMBlockAnalyzer]
LLM으로 분석 (단일 호출)
    ↓
분석 결과 (type, should_translate, merge_strategy, protected_terms)
    ↓
[SmartPDFTranslator]
병합 → 번역 → 렌더링
    ↓
번역된 PDF
```

## 사용법

### 기본 사용

```bash
python main_smart.py input.pdf
```

### 옵션 지정

```bash
python main_smart.py input.pdf \
  -o output.pdf \
  --model gpt-4o \
  --analyzer-model gpt-4o-mini \
  --font-dir font
```

### 파라미터

- `input`: 입력 PDF 파일 (필수)
- `-o, --output`: 출력 PDF 파일 (선택, 기본: `output/{filename}_smart_{timestamp}.pdf`)
- `--model`: 번역용 모델 (기본: `gpt-4o-mini`)
- `--analyzer-model`: 분석용 모델 (기본: `gpt-4o-mini`)
- `--font`: 한글 폰트 파일 경로
- `--font-dir`: 한글 폰트 디렉토리 (기본: `font/`)

## LLM 분석 예시

### Input (PyMuPDF 추출)
```json
[
  {"id": 0, "text": "Introduction", "font_size": 18, "is_bold": true},
  {"id": 1, "text": "This paper presents...", "font_size": 12},
  {"id": 2, "text": "f(x) = ∑ wᵢxᵢ", "has_special_chars": true},
  {"id": 3, "text": "Figure 1: Results", "is_italic": true}
]
```

### LLM 분석 결과
```json
{
  "blocks": [
    {
      "id": 0,
      "type": "header",
      "should_translate": true,
      "merge_strategy": "standalone",
      "reasoning": "Large bold text indicates section header",
      "protected_terms": []
    },
    {
      "id": 1,
      "type": "paragraph",
      "should_translate": true,
      "merge_strategy": "standalone",
      "reasoning": "Normal body text",
      "protected_terms": []
    },
    {
      "id": 2,
      "type": "equation",
      "should_translate": false,
      "merge_strategy": "standalone",
      "reasoning": "Mathematical equation with symbols",
      "protected_terms": []
    },
    {
      "id": 3,
      "type": "caption",
      "should_translate": true,
      "merge_strategy": "standalone",
      "reasoning": "Italic text starting with 'Figure' indicates caption",
      "protected_terms": ["Figure"]
    }
  ]
}
```

### 최종 번역 결과
- Block 0: "서론" (번역됨)
- Block 1: "본 논문은..." (번역됨)
- Block 2: "f(x) = ∑ wᵢxᵢ" (보존됨, 수식이라 번역 안함)
- Block 3: "Figure 1: 결과" (번역됨, "Figure"는 보호)

## 블록 타입

LLM이 인식하는 블록 타입:

- **title**: 문서 제목
- **header**: 섹션/서브섹션 헤더
- **paragraph**: 본문 텍스트
- **caption**: 그림/표 캡션
- **equation**: 수식
- **code**: 코드 스니펫
- **table**: 표
- **footer**: 페이지 번호, 각주
- **reference**: 참고문헌

## 병합 전략

- **standalone**: 독립적인 단위 (헤더, 수식, 캡션 등)
- **merge_next**: 다음 블록과 병합 (문단이 계속됨)
- **continue_previous**: 이전 블록의 연속

## 비용

- **페이지당 약 $0.001~0.005** (Vision API 없이 Text API만 사용)
- 예: 100페이지 PDF = $0.10~0.50

## 장점

✅ **정확성**: PyMuPDF의 정확한 bbox 사용
✅ **지능형**: LLM이 문맥을 이해하고 판단
✅ **비용 효율**: Vision API 불필요
✅ **속도**: 빠른 처리
✅ **유연성**: 다양한 문서 형식 자동 적응
✅ **디버깅**: LLM 응답에 reasoning 포함

## 환경 변수

`.env` 파일에 다음을 설정하세요:

```bash
OPENAI_API_KEY=your_api_key_here
```

## 의존성

- PyMuPDF (fitz)
- OpenAI Python SDK
- python-dotenv
