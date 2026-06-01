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
    # md_path를 절대경로로, artifacts_dir을 extract_dir에 상대적인 경로로 지정해야
    # base.parse_sections의 경로 해석(extract_dir + 상대경로)과 일치한다.
    md_path = Path(extract_dir).resolve() / f"{pdf_stem}.md"
    artifacts_dir = Path(f"{pdf_stem}_artifacts")  # extract_dir 기준 상대경로
    doc.save_as_markdown(md_path, artifacts_dir=artifacts_dir, image_mode=ImageRefMode.REFERENCED)

    with open(str(md_path), "r", encoding="utf-8") as f:
        markdown = f.read()

    return base.build_result(markdown, extract_dir)
