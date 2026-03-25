import argparse
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.pdf_extractor import extract
from src.llm_analyzer import analyze
from src.docx_writer import write


def main():
    parser = argparse.ArgumentParser(description="PDF 문서 분석기 - 한국어 분석 리포트 생성")
    parser.add_argument("input", help="분석할 PDF 파일 경로")
    parser.add_argument("-o", "--output", help="출력 docx 파일 경로")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Gemini 모델명 (default: gemini-2.5-flash-lite)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"오류: 파일을 찾을 수 없습니다: {args.input}")
        sys.exit(1)

    if args.output:
        output_path = args.output
    else:
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        output_path = str(output_dir / f"{input_path.stem}_분석_{date_str}.docx")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("오류: GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    print(f"PDF 추출 중: {input_path}")
    extracted = extract(str(input_path))
    print(f"  페이지 수: {len(extracted['pages'])}, 감지된 섹션: {len(extracted['sections'])}")
    print(f"  텍스트 길이: {len(extracted['full_text'])}자")

    print(f"\nLLM 분석 중 (모델: {args.model})...")
    analysis = analyze(extracted, model=args.model, api_key=api_key)
    print(f"  문서 유형: {analysis.get('doc_type', '알 수 없음')}")
    print(f"  섹션 수: {len(analysis.get('sections', []))}")
    print(f"  주요 데이터 수: {len(analysis.get('key_data', []))}")

    print(f"\nDocx 생성 중...")
    write(analysis, output_path, source_filename=str(input_path))
    print(f"\n완료: {output_path}")


if __name__ == "__main__":
    main()
