"""HTML sanitization tests."""

from app.normalization.html_sanitizer import sanitize_html


def test_sanitize_strips_html_tags() -> None:
    result = sanitize_html("Hello<br/>World <script>alert(1)</script>")
    assert result is not None
    assert "<" not in result
    assert "Hello" in result
    assert "World" in result
