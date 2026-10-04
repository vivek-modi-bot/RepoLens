"""File filtering and size-limit tests."""

from pathlib import Path

import pytest

from app.analysis.file_filter import FileFilter
from app.core.config import Settings
from app.core.exceptions import RepositoryTooLargeError


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_excludes_env_and_secrets(tmp_path: Path) -> None:
    _write(tmp_path / "app.py", "print('hi')\n")
    _write(tmp_path / ".env", "SECRET=abc\n")
    _write(tmp_path / ".env.local", "TOKEN=xyz\n")
    _write(tmp_path / "credentials.json", '{"key":"value"}\n')
    _write(tmp_path / "keys" / "server.pem", "-----BEGIN-----\n")
    _write(tmp_path / "node_modules" / "pkg" / "index.js", "module.exports=1\n")
    _write(tmp_path / "__pycache__" / "x.pyc", "binaryish")

    files = FileFilter().collect(tmp_path)
    relative = {f.relative_path for f in files}
    assert relative == {"app.py"}


def test_respects_gitignore(tmp_path: Path) -> None:
    _write(tmp_path / ".gitignore", "generated/\n*.log\n")
    _write(tmp_path / "main.py", "x=1\n")
    _write(tmp_path / "generated" / "out.py", "y=2\n")
    _write(tmp_path / "debug.log", "log\n")

    files = FileFilter().collect(tmp_path)
    assert [f.relative_path for f in files] == ["main.py"]


def test_skips_large_files(tmp_path: Path) -> None:
    settings = Settings(max_file_size=50, max_files=100, max_repository_size=10_000_000)
    _write(tmp_path / "small.py", "a=1\n")
    _write(tmp_path / "large.py", "x" * 200)

    files = FileFilter(settings).collect(tmp_path)
    assert [f.relative_path for f in files] == ["small.py"]


def test_repository_size_limit(tmp_path: Path) -> None:
    settings = Settings(max_file_size=10_000, max_files=100, max_repository_size=100)
    _write(tmp_path / "a.py", "a" * 60)
    _write(tmp_path / "b.py", "b" * 60)

    with pytest.raises(RepositoryTooLargeError):
        FileFilter(settings).collect(tmp_path)


def test_max_files_cap(tmp_path: Path) -> None:
    settings = Settings(max_file_size=10_000, max_files=2, max_repository_size=10_000_000)
    for i in range(5):
        _write(tmp_path / f"f{i}.py", f"x={i}\n")

    files = FileFilter(settings).collect(tmp_path)
    assert len(files) == 2
