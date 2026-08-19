import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = PROJECT_ROOT / "docs"
MARKDOWN_LINK = re.compile(r"\[[^]]*]\(([^)]+)\)")
REMOVED_API_PATH = re.compile(r"/api/(?:index|users|community|sync)(?:/|\b)")


def documentation_files() -> list[Path]:
    return [PROJECT_ROOT / "README.md", *sorted(DOCS_ROOT.rglob("*.md"))]


def test_documentation_has_the_expected_information_architecture() -> None:
    assert {path.name for path in DOCS_ROOT.iterdir()} == {
        "architecture.md",
        "deployment.md",
        "development.md",
    }


def test_documentation_internal_links_resolve() -> None:
    missing: list[str] = []
    for document in documentation_files():
        for target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            target = target.split("#", 1)[0]
            if not target or "://" in target or target.startswith(("/", "mailto:")):
                continue
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                missing.append(f"{document.relative_to(PROJECT_ROOT)} -> {target}")

    assert missing == []


def test_documentation_does_not_advertise_removed_api_roots() -> None:
    violations = [
        str(document.relative_to(PROJECT_ROOT))
        for document in documentation_files()
        if REMOVED_API_PATH.search(document.read_text(encoding="utf-8"))
    ]

    assert violations == []
