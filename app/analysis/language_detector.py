"""Detect programming languages from file extensions / names."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from app.analysis.file_filter import SourceFile

EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".hpp": "C++",
    ".cs": "C#",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".swift": "Swift",
    ".scala": "Scala",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
    ".xml": "XML",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".dart": "Dart",
    ".lua": "Lua",
    ".r": "R",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".hs": "Haskell",
    ".clj": "Clojure",
    ".tf": "Terraform",
    ".gradle": "Gradle",
}

BASENAME_LANGUAGE_MAP: dict[str, str] = {
    "Dockerfile": "Dockerfile",
    "Makefile": "Makefile",
    "Gemfile": "Ruby",
    "Rakefile": "Ruby",
    "CMakeLists.txt": "CMake",
}


class LanguageDetector:
    """Assign languages to source files and compute repository language stats."""

    def detect_file(self, path: Path | str) -> str | None:
        path_obj = Path(path)
        if path_obj.name in BASENAME_LANGUAGE_MAP:
            return BASENAME_LANGUAGE_MAP[path_obj.name]
        if path_obj.name.lower() == "dockerfile":
            return "Dockerfile"
        return EXTENSION_LANGUAGE_MAP.get(path_obj.suffix.lower())

    def annotate(self, files: list[SourceFile]) -> list[SourceFile]:
        annotated: list[SourceFile] = []
        for source in files:
            language = self.detect_file(source.relative_path)
            annotated.append(
                SourceFile(
                    relative_path=source.relative_path,
                    absolute_path=source.absolute_path,
                    size_bytes=source.size_bytes,
                    language=language,
                )
            )
        return annotated

    def languages(self, files: list[SourceFile]) -> list[str]:
        counter: Counter[str] = Counter()
        for source in files:
            lang = source.language or self.detect_file(source.relative_path)
            if lang:
                counter[lang] += 1
        return [name for name, _ in counter.most_common()]

    def statistics(self, files: list[SourceFile]) -> dict:
        total_lines = 0
        for source in files:
            try:
                text = source.absolute_path.read_text(encoding="utf-8", errors="ignore")
                total_lines += text.count("\n") + (1 if text and not text.endswith("\n") else 0)
            except OSError:
                continue
        return {
            "files_analyzed": len(files),
            "languages": self.languages(files),
            "total_lines": total_lines,
        }
