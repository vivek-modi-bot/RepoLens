"""Split source files into LLM-sized chunks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.analysis.file_filter import SourceFile
from app.core.config import Settings, get_settings


@dataclass(slots=True, frozen=True)
class CodeChunk:
    chunk_id: str
    files: list[str]
    content: str
    language: str | None = None
    char_count: int = 0


class CodeChunker:
    """Create bounded text chunks for LLM review prompts."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def chunk_files(self, files: list[SourceFile]) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        current_parts: list[str] = []
        current_files: list[str] = []
        current_size = 0
        chunk_index = 0
        max_chars = self._settings.max_chunk_chars
        max_chunks = self._settings.max_chunks

        for source in files:
            if len(chunks) >= max_chunks:
                break
            file_block = self._format_file(source)
            if not file_block:
                continue

            # Oversized single file: split by lines.
            if len(file_block) > max_chars:
                if current_parts:
                    chunks.append(
                        self._build_chunk(chunk_index, current_files, current_parts)
                    )
                    chunk_index += 1
                    current_parts, current_files, current_size = [], [], 0

                for part in self._split_large_block(file_block, max_chars):
                    if len(chunks) >= max_chunks:
                        break
                    chunks.append(
                        CodeChunk(
                            chunk_id=f"chunk-{chunk_index}",
                            files=[source.relative_path],
                            content=part,
                            language=source.language,
                            char_count=len(part),
                        )
                    )
                    chunk_index += 1
                continue

            if current_size + len(file_block) > max_chars and current_parts:
                chunks.append(
                    self._build_chunk(chunk_index, current_files, current_parts)
                )
                chunk_index += 1
                current_parts, current_files, current_size = [], [], 0
                if len(chunks) >= max_chunks:
                    break

            current_parts.append(file_block)
            current_files.append(source.relative_path)
            current_size += len(file_block)

        if current_parts and len(chunks) < max_chunks:
            chunks.append(self._build_chunk(chunk_index, current_files, current_parts))

        return chunks[:max_chunks]

    def _format_file(self, source: SourceFile) -> str:
        try:
            content = source.absolute_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""
        language = source.language or Path(source.relative_path).suffix.lstrip(".")
        return (
            f"### File: {source.relative_path}\n"
            f"Language: {language}\n"
            f"```\n{content}\n```\n"
        )

    def _split_large_block(self, block: str, max_chars: int) -> list[str]:
        lines = block.splitlines(keepends=True)
        parts: list[str] = []
        current: list[str] = []
        size = 0
        for line in lines:
            if size + len(line) > max_chars and current:
                parts.append("".join(current))
                current = []
                size = 0
            current.append(line)
            size += len(line)
        if current:
            parts.append("".join(current))
        return parts

    def _build_chunk(
        self, index: int, files: list[str], parts: list[str]
    ) -> CodeChunk:
        content = "\n".join(parts)
        return CodeChunk(
            chunk_id=f"chunk-{index}",
            files=list(files),
            content=content,
            char_count=len(content),
        )
