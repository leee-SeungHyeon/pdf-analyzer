import pytest
from src.extractors import get_extractor


def test_unknown_backend_raises():
    with pytest.raises(ValueError, match="알 수 없는 추출기"):
        get_extractor("nope")


def test_known_backends_return_callable():
    for name in ("marker", "docling"):
        extractor = get_extractor(name)
        assert callable(extractor)
