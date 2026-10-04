"""Filter repository files for safe static analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from pathspec import PathSpec
from pathspec.patterns import GitWildMatchPattern

from app.core.config import Settings, get_settings
from app.core.exceptions import RepositoryTooLargeError

logger = logging.getLogger(__name__)

IGNORED_DIRECTORIES = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "coverage",
    "venv",
    ".venv",
    "__pycache__",
    "target",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".next",
    ".nuxt",
    "vendor",
    ".idea",
    ".vscode",
    "eggs",
    ".eggs",
    ".cache",
}

SECRET_FILENAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.staging",
    ".env.test",
    "credentials.json",
    "service-account.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    ".npmrc",
    ".pypirc",
}

SECRET_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
}

SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".kt",
    ".kts",
    ".swift",
    ".scala",
    ".m",
    ".mm",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".xml",
    ".html",
    ".css",
    ".scss",
    ".vue",
    ".svelte",
    ".dart",
    ".lua",
    ".r",
    ".pl",
    ".pm",
    ".ex",
    ".exs",
    ".erl",
    ".hs",
    ".clj",
    ".groovy",
    ".gradle",
    ".tf",
    ".dockerfile",
}

SOURCE_BASENAMES = {
    "Dockerfile",
    "Makefile",
    "Gemfile",
    "Rakefile",
    "Procfile",
    "CMakeLists.txt",
}


@dataclass(slots=True, frozen=True)
class SourceFile:
    relative_path: str
    absolute_path: Path
    size_bytes: int
    language: str | None = None


class FileFilter:
    """Select source files while excluding secrets and generated artifacts."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def collect(self, root: Path) -> list[SourceFile]:
        gitignore_spec = self._load_gitignore(root)
        selected: list[SourceFile] = []
        total_size = 0

        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue

            relative = path.relative_to(root).as_posix()
            if self._should_ignore(path, relative, gitignore_spec):
                continue

            try:
                size = path.stat().st_size
            except OSError:
                continue

            if size > self._settings.max_file_size:
                logger.debug("Skipping large file %s (%s bytes)", relative, size)
                continue

            if not self._is_source_file(path):
                continue

            if self._looks_binary(path):
                continue

            total_size += size
            if total_size > self._settings.max_repository_size:
                raise RepositoryTooLargeError(
                    "Selected source files exceed repository size limit"
                )

            selected.append(
                SourceFile(
                    relative_path=relative,
                    absolute_path=path,
                    size_bytes=size,
                )
            )

            if len(selected) >= self._settings.max_files:
                logger.info(
                    "Reached MAX_FILES=%s; truncating file list",
                    self._settings.max_files,
                )
                break

        return selected

    def _load_gitignore(self, root: Path) -> PathSpec | None:
        gitignore = root / ".gitignore"
        if not gitignore.is_file():
            return None
        try:
            lines = gitignore.read_text(encoding="utf-8", errors="ignore").splitlines()
            return PathSpec.from_lines(GitWildMatchPattern, lines)
        except OSError:
            return None

    def _should_ignore(
        self,
        path: Path,
        relative: str,
        gitignore_spec: PathSpec | None,
    ) -> bool:
        parts = Path(relative).parts
        if any(part in IGNORED_DIRECTORIES for part in parts):
            return True

        name = path.name
        lower_name = name.lower()

        if lower_name in {n.lower() for n in SECRET_FILENAMES}:
            return True
        if name.startswith(".env"):
            return True
        if path.suffix.lower() in SECRET_SUFFIXES:
            return True
        if "secret" in lower_name or "credential" in lower_name:
            return True

        if gitignore_spec is not None and gitignore_spec.match_file(relative):
            return True

        return False

    def _is_source_file(self, path: Path) -> bool:
        if path.name in SOURCE_BASENAMES:
            return True
        if path.name.lower() == "dockerfile":
            return True
        return path.suffix.lower() in SOURCE_EXTENSIONS

    def _looks_binary(self, path: Path) -> bool:
        try:
            with path.open("rb") as handle:
                chunk = handle.read(2048)
            return b"\x00" in chunk
        except OSError:
            return True
