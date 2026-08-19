import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
APPS_ROOT = SRC_ROOT / "apps"
TESTS_ROOT = PROJECT_ROOT / "tests"


def _python_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_tests_are_layered_by_ownership() -> None:
    app_tests = {path.parent.name for path in TESTS_ROOT.glob("apps/*/test_*.py")}

    assert app_tests == {"ai", "community", "index", "sync", "users"}
    assert not list(APPS_ROOT.glob("*/tests"))
    assert (PROJECT_ROOT / "tests/integrations").is_dir()
    assert (PROJECT_ROOT / "tests/shared").is_dir()


def test_management_packages_are_importable_and_commands_stay_thin() -> None:
    management_directories = sorted(APPS_ROOT.glob("*/management"))

    assert management_directories
    for management in management_directories:
        assert (management / "__init__.py").is_file()
        commands = management / "commands"
        assert (commands / "__init__.py").is_file()
        for command in commands.glob("*.py"):
            if command.name == "__init__.py":
                continue
            tree = ast.parse(_python_source(command))
            assert (
                sum(isinstance(node, ast.FunctionDef) for node in ast.walk(tree)) <= 3
            )


def test_application_errors_have_one_shared_dependency_direction() -> None:
    assert not (SRC_ROOT / "shared/errors.py").exists()

    for exceptions_module in APPS_ROOT.glob("*/exceptions.py"):
        source = _python_source(exceptions_module)
        assert "from shared.exceptions import ApplicationError" in source
        assert "from shared.api" not in source
        assert "rest_framework" not in source


def test_infrastructure_exceptions_are_separate_from_clients() -> None:
    assert (SRC_ROOT / "integrations/ai/exceptions.py").is_file()
    assert (SRC_ROOT / "integrations/storage/exceptions.py").is_file()
    assert (APPS_ROOT / "sync/providers/exceptions.py").is_file()
