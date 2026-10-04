"""Review-type-specific prompt construction."""

from __future__ import annotations

from app.schemas.repository import ReviewType

JSON_SCHEMA_INSTRUCTIONS = """
Return ONLY one valid JSON object. No markdown. No extra text.
Example:
{"overall_score":80,"summary":"Brief summary","issues":[{"file":"app.py","line":10,"severity":"medium","category":"quality","title":"Short title","description":"What is wrong","recommendation":"How to fix"}]}

Rules:
- overall_score must be an integer 0-100
- severity must be one of: critical, high, medium, low, info
- category must be one of: bug, security, performance, maintainability, architecture, quality, style, other
- issues may be an empty array
- Keep issues concise (max 5)
- Use only files shown in the code
""".strip()

FOCUS_BY_TYPE: dict[ReviewType, str] = {
    ReviewType.FULL: """
Focus areas:
- bugs and correctness issues
- security vulnerabilities
- performance problems
- maintainability concerns
- architecture / design smells
- general code quality
""".strip(),
    ReviewType.SECURITY: """
Focus areas (security only):
- hardcoded secrets / credentials
- authentication and authorization problems
- injection risks (SQL, command, XSS, template)
- unsafe input handling
- insecure dependencies or configuration
- sensitive data exposure
""".strip(),
    ReviewType.PERFORMANCE: """
Focus areas (performance only):
- inefficient algorithms and data structures
- unnecessary database / network calls
- repeated expensive computation
- memory pressure / leaks patterns
- inefficient API usage
""".strip(),
    ReviewType.QUALITY: """
Focus areas (code quality only):
- code smells
- maintainability
- duplication
- naming clarity
- error handling
- complexity
""".strip(),
    ReviewType.ARCHITECTURE: """
Focus areas (architecture only):
- separation of concerns
- coupling and cohesion
- scalability risks
- module boundaries
- design / layering problems
""".strip(),
}


class PromptService:
    """Build prompts tailored to each review type."""

    def build_chunk_prompt(
        self,
        *,
        review_type: ReviewType,
        repository: str,
        branch: str,
        chunk_content: str,
        chunk_files: list[str],
    ) -> str:
        focus = FOCUS_BY_TYPE[review_type]
        files_list = ", ".join(chunk_files) if chunk_files else "(unknown)"
        return f"""You are an expert software engineer performing a static code review.
Repository: {repository}
Branch: {branch}
Review type: {review_type.value}
Files in this chunk: {files_list}

{focus}

Analyze ONLY the code below. Do not execute code. Do not assume missing context beyond what is shown.

CODE:
{chunk_content}

{JSON_SCHEMA_INSTRUCTIONS}
"""

    def build_retry_prompt(self, previous_response: str) -> str:
        return f"""Your previous response was not valid JSON matching the required schema.
Fix it and return ONLY valid JSON.

Previous response:
{previous_response[:4000]}

{JSON_SCHEMA_INSTRUCTIONS}
"""

    def build_ask_prompt(
        self,
        *,
        repository: str,
        branch: str,
        review_type: str,
        summary: str,
        issue: dict,
        question: str,
        history: list[tuple[str, str]],
    ) -> str:
        finding = (
            f"Severity: {issue.get('severity')}\n"
            f"Category: {issue.get('category')}\n"
            f"File: {issue.get('file')}:{issue.get('line')}\n"
            f"Title: {issue.get('title')}\n"
            f"Description: {issue.get('description')}\n"
            f"Recommendation: {issue.get('recommendation')}"
        )

        history_block = "\n".join(
            f"{role.upper()}: {content}" for role, content in history[-6:]
        ) or "(none)"

        return f"""You are RepoLens, an assistant answering questions about ONE specific code-review finding.
Stay focused on this finding only. Use the review summary only as light context.
If the answer is not supported by this finding, say you do not have enough evidence.
Do not invent files or vulnerabilities. Keep the answer concise and practical.

Repository: {repository}
Branch: {branch}
Review type: {review_type}
Review summary: {summary}

Finding under discussion:
{finding}

Recent conversation about this finding:
{history_block}

USER QUESTION: {question}

ANSWER:"""

    def build_fix_prompt(
        self,
        *,
        repository: str,
        branch: str,
        issue: dict,
        original_content: str,
    ) -> str:
        # Keep prompts bounded for small local models (context ~4k tokens).
        content = original_content
        if len(content) > 4500:
            content = content[:4500] + "\n# ... truncated for model context ...\n"

        return f"""Fix the finding below with a minimal code change.

Return EXACTLY in this format:

EXPLANATION: <one short sentence>
COMMIT: fix: <short commit message>
``` 
<full updated file contents here>
```

Rules:
- Output the COMPLETE updated file inside the code fence.
- Do not output a diff.
- Do not invent unrelated refactors.
- Keep style consistent.

Repository: {repository}
Branch: {branch}
File: {issue.get('file')}
Finding title: {issue.get('title')}
Finding description: {issue.get('description')}
Recommendation: {issue.get('recommendation')}

Original file:
```
{content}
```
"""

    def build_fix_retry_prompt(
        self,
        *,
        file_path: str,
        issue: dict,
        original_content: str,
        previous_response: str,
    ) -> str:
        content = original_content
        if len(content) > 3500:
            content = content[:3500] + "\n# ... truncated ...\n"
        return f"""Your previous answer was invalid. Try again.

Return ONLY:
EXPLANATION: ...
COMMIT: fix: ...
```
complete fixed file for {file_path}
```

Finding: {issue.get('title')} — {issue.get('recommendation')}

Original file:
```
{content}
```

Previous invalid answer (do not copy the broken format):
{(previous_response or '')[:800]}
"""
