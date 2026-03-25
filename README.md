# PDF Analyzer

PDF 문서를 분석하여 한국어 분석 리포트(docx)를 생성하는 도구입니다.

Gemini API를 사용해 문서 유형 파악, 전체 요약, 섹션별 요약, 주요 수치 추출을 수행합니다.

## 출력 예시

- 문서 유형: 금융 리서치 리포트
- 전체 요약 (3~5줄)
- 주요 수치/데이터 표
- 섹션별 요약

## 요구사항

- Python 3.11+
- Gemini API Key ([Google AI Studio](https://aistudio.google.com/app/apikey)에서 발급)

## 설치

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 환경 설정

```bash
cp .env.example .env
# .env 파일에 GEMINI_API_KEY 입력
```

## 사용법

### 로컬 실행

```bash
python main.py input.pdf
python main.py input.pdf -o output/result.docx
python main.py input.pdf --model gemini-2.0-flash
```

결과물은 `output/파일명_분석_YYYYMMDD.docx`에 저장됩니다.

### Docker 실행

```bash
# 이미지 빌드
docker build -t pdf-analyzer .

# 실행
docker run --rm \
  -e GEMINI_API_KEY=your_api_key \
  -v /path/to/input.pdf:/input/input.pdf \
  -v /path/to/output:/app/output \
  pdf-analyzer /input/input.pdf
```

## 프로젝트 구조

```
pdf-analyzer/
├── main.py              # 진입점
├── src/
│   ├── pdf_extractor.py # PyMuPDF 텍스트/구조 추출
│   ├── llm_analyzer.py  # Gemini API 분석
│   └── docx_writer.py   # docx 생성
├── Dockerfile
├── requirements.txt
└── .env.example
```

## 샘플

`examples/` 폴더에 샘플 입력과 결과물이 있습니다.

| 파일 | 설명 |
|---|---|
| `examples/sample_input.pdf` | 샘플 입력 PDF (AI 금융 활용 리서치 리포트) |
| `examples/sample_output.docx` | 생성된 한국어 분석 리포트 |

## 한계

- PDF 내 이미지는 분석하지 않습니다 (텍스트만 추출)
- 표 구조는 텍스트로 평탄화됩니다
- 전체 텍스트가 50,000자를 초과하면 잘립니다
