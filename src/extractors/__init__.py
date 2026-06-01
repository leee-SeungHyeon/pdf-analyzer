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
