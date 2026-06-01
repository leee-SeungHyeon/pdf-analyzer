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
