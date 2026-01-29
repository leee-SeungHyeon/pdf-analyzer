# main.py - V2 Simple
import asyncio
import argparse
from pathlib import Path
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

from pdf_translator_direct_v2 import DirectPDFTranslatorV2
from translation_api import OpenAITranslationAPI, DummyTranslationAPI


async def main():
    parser = argparse.ArgumentParser(description="PDF Translator V2")

    parser.add_argument("input", help="Input PDF file")
    parser.add_argument("-o", "--output", help="Output PDF file")
    parser.add_argument("--gpt", action="store_true", help="Use OpenAI GPT (default)")
    parser.add_argument("--dummy", action="store_true", help="Use dummy translation (for testing)")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model")
    parser.add_argument("--font", help="Korean font file path (e.g., NanumGothic.ttf)")
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
        output_path = output_dir / f"{input_path.stem}_translated_{timestamp}.pdf"

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

    # API 선택
    if args.dummy:
        print("Using Dummy Translation API\n")
        api = DummyTranslationAPI()
    else:
        print(f"Using OpenAI GPT API")
        print(f"Model: {args.model}\n")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("❌ Error: OPENAI_API_KEY not found in environment")
            return
        api = OpenAITranslationAPI(api_key=api_key, model=args.model)

    # 번역하지 않을 보호 단어 설정
    protected_words = [
                        "–"
                        ]

    # 번역 실행
    try:
        async with api:
            translator = DirectPDFTranslatorV2(
                translation_api=api,
                font_path=font_path,
                font_dir=font_dir,
                protected_words=protected_words
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
