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
