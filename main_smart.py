# main_smart.py - Smart PDF Translator with LLM Analysis
import asyncio
import argparse
from pathlib import Path
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

from src.smart_pdf_translator import SmartPDFTranslator
from src.llm_block_analyzer import LLMBlockAnalyzer
from translation_api import OpenAITranslationAPI


async def main():
    parser = argparse.ArgumentParser(
        description="Smart PDF Translator - LLM-guided translation"
    )

    parser.add_argument("input", help="Input PDF file")
    parser.add_argument("-o", "--output", help="Output PDF file")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model for translation (default: gpt-4o-mini)")
    parser.add_argument("--analyzer-model", default="gpt-4o-mini", help="OpenAI model for analysis (default: gpt-4o-mini)")
    parser.add_argument("--font", help="Korean font file path")
    parser.add_argument("--font-dir", default="font", help="Korean font directory (default: font/)")

    args = parser.parse_args()

    # Input 확인
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Error: File not found: {args.input}")
        return

    # Output 경로
    if args.output:
        output_path = Path(args.output)
    else:
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = output_dir / f"{input_path.stem}_smart_{timestamp}.pdf"

    # Font 확인
    font_path = None
    font_dir = None

    if args.font:
        font_file = Path(args.font)
        if not font_file.exists():
            print(f"⚠ Warning: Font file not found: {args.font}")
        else:
            font_path = str(font_file)

    if args.font_dir:
        font_directory = Path(args.font_dir)
        if not font_directory.exists():
            print(f"⚠ Warning: Font directory not found: {args.font_dir}")
        else:
            font_dir = str(font_directory)

    # API Key 확인
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: OPENAI_API_KEY not found in environment")
        return

    print(f"Using OpenAI API")
    print(f"Translation model: {args.model}")
    print(f"Analysis model: {args.analyzer_model}\n")

    # API 초기화
    translation_api = OpenAITranslationAPI(api_key=api_key, model=args.model)
    llm_analyzer = LLMBlockAnalyzer(api_key=api_key, model=args.analyzer_model)

    # 번역 실행
    try:
        async with translation_api:
            translator = SmartPDFTranslator(
                translation_api=translation_api,
                llm_analyzer=llm_analyzer,
                font_path=font_path,
                font_dir=font_dir
            )

            await translator.translate_pdf(
                input_pdf=str(input_path),
                output_pdf=str(output_path),
                source_lang="en",
                target_lang="ko"
            )
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
