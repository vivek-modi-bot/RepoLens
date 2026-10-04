"""Generate code fixes for findings and optionally open GitHub PRs."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    FindingNotFoundError,
    FixNotFoundError,
    GitHubWriteError,
    LLMResponseError,
    ReviewNotFoundError,
)
from app.core.token_crypto import decrypt_secret
from app.github.client import GitHubClient
from app.github.pr_client import GitHubPRClient
from app.github.validator import parse_github_url
from app.llm.base import LLMProvider, build_llm_provider
from app.models.finding_fix import FindingFix
from app.models.review import Review
from app.models.user import User
from app.schemas.fix import (
    CreatePullRequestRequest,
    FixSuggestionResponse,
    PullRequestResponse,
)
from app.services.llm_response_parser import extract_json_object
from app.services.prompt_service import PromptService

logger = logging.getLogger(__name__)


class FixService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings | None = None,
        llm_provider: LLMProvider | None = None,
        prompt_service: PromptService | None = None,
    ) -> None:
        self._db = db
        self._settings = settings or get_settings()
        self._llm = llm_provider or build_llm_provider(self._settings)
        self._prompts = prompt_service or PromptService()

    async def generate_fix(
        self,
        *,
        review_id: UUID,
        issue_index: int,
        user: User,
    ) -> FixSuggestionResponse:
        review = await self._get_owned_review(review_id, user)
        issue = self._get_issue(review, issue_index)
        file_path = str(issue.get("file") or "").strip()
        if not file_path or file_path == "unknown":
            raise GitHubWriteError(
                "This finding has no usable file path for a code fix"
            )

        parsed_url = parse_github_url(f"https://github.com/{review.repository}")
        async with GitHubClient(self._settings) as github:
            original = await github.get_file_text(
                parsed_url, file_path, review.branch
            )

        prompt = self._prompts.build_fix_prompt(
            repository=review.repository,
            branch=review.branch,
            issue=issue,
            original_content=original,
        )
        raw = ""
        try:
            # Avoid Ollama format=json for large file-rewrite prompts (can 500).
            raw = await self._llm.generate_fix(prompt)
            parsed = self._parse_fix_response(raw, fallback_path=file_path)
            if parsed["updated_content"].strip() == original.strip():
                raise LLMResponseError("Model returned unchanged content")
        except LLMResponseError:
            logger.warning("Retrying fix generation with simpler prompt")
            retry_prompt = self._prompts.build_fix_retry_prompt(
                file_path=file_path,
                issue=issue,
                original_content=original,
                previous_response=raw,
            )
            raw = await self._llm.generate_fix(retry_prompt)
            parsed = self._parse_fix_response(raw, fallback_path=file_path)
        finally:
            await self._llm.aclose()

        updated = parsed["updated_content"]
        if updated.strip() == original.strip():
            raise LLMResponseError(
                "Model returned an unchanged file. Try asking in chat for guidance first."
            )

        fix = FindingFix(
            review_id=str(review_id),
            issue_index=issue_index,
            file_path=parsed["file_path"],
            original_content=original,
            updated_content=updated,
            explanation=parsed["explanation"],
            commit_message=parsed["commit_message"][:255],
            created_at=datetime.now(UTC),
        )
        self._db.add(fix)
        await self._db.commit()
        await self._db.refresh(fix)
        return self._to_fix_response(fix, review_id)

    async def get_latest_fix(
        self,
        *,
        review_id: UUID,
        issue_index: int,
        user: User,
    ) -> FixSuggestionResponse:
        await self._get_owned_review(review_id, user)
        fix = await self._latest_fix(review_id, issue_index)
        if fix is None:
            raise FixNotFoundError()
        return self._to_fix_response(fix, review_id)

    async def create_pull_request(
        self,
        *,
        review_id: UUID,
        issue_index: int,
        user: User,
        payload: CreatePullRequestRequest,
    ) -> PullRequestResponse:
        review = await self._get_owned_review(review_id, user)
        issue = self._get_issue(review, issue_index)

        if payload.fix_id:
            result = await self._db.execute(
                select(FindingFix).where(
                    FindingFix.id == payload.fix_id,
                    FindingFix.review_id == str(review_id),
                    FindingFix.issue_index == issue_index,
                )
            )
            fix = result.scalar_one_or_none()
        else:
            fix = await self._latest_fix(review_id, issue_index)
        if fix is None:
            raise FixNotFoundError(
                "Generate a fix for this finding before opening a pull request"
            )

        github_token = (payload.github_token or "").strip() or None
        if not github_token and user.github_token_encrypted:
            github_token = decrypt_secret(user.github_token_encrypted)
        if not github_token:
            raise GitHubWriteError(
                "No GitHub token available. Save one in your profile, or provide it for this request."
            )

        owner, repo = review.repository.split("/", 1)
        slug = re.sub(r"[^a-zA-Z0-9-_]+", "-", str(issue.get("title") or "fix"))
        slug = slug.strip("-").lower()[:40] or "fix"
        branch_name = (
            payload.branch_name
            or f"repolens/{issue_index}-{slug}"
        )[:120]
        title = payload.pr_title or fix.commit_message
        body = payload.pr_body or (
            f"## RepoLens suggested fix\n\n"
            f"**Finding:** {issue.get('title')}\n\n"
            f"{fix.explanation}\n\n"
            f"**File:** `{fix.file_path}`\n\n"
            f"_Generated from a static AI review. Please verify before merging._"
        )

        async with GitHubPRClient(github_token, self._settings) as github:
            base_sha = await github.get_branch_sha(owner, repo, review.branch)
            await github.create_branch(owner, repo, branch_name, base_sha)
            # Fetch current sha on target branch/path for update.
            try:
                _, file_sha = await github.get_file_content(
                    owner, repo, fix.file_path, branch_name
                )
            except Exception:  # noqa: BLE001
                file_sha = None
            commit_sha = await github.commit_file(
                owner=owner,
                repo=repo,
                path=fix.file_path,
                content=fix.updated_content,
                message=fix.commit_message,
                branch=branch_name,
                current_sha=file_sha,
            )
            pr = await github.create_pull_request(
                owner=owner,
                repo=repo,
                title=title,
                body=body,
                head=branch_name,
                base=review.branch,
            )

        pr_url = pr.get("html_url") or ""
        pr_number = int(pr.get("number") or 0)
        fix.pr_url = pr_url
        fix.pr_number = pr_number
        await self._db.commit()

        return PullRequestResponse(
            fix_id=fix.id,
            review_id=str(review_id),
            issue_index=issue_index,
            branch_name=branch_name,
            pr_number=pr_number,
            pr_url=pr_url,
            commit_sha=commit_sha,
        )

    async def _get_owned_review(self, review_id: UUID, user: User) -> Review:
        result = await self._db.execute(
            select(Review).where(
                Review.id == str(review_id),
                Review.user_id == user.id,
            )
        )
        review = result.scalar_one_or_none()
        if review is None:
            raise ReviewNotFoundError()
        return review

    def _get_issue(self, review: Review, issue_index: int) -> dict:
        issues = list(review.issues or [])
        if issue_index < 0 or issue_index >= len(issues):
            raise FindingNotFoundError(
                f"Finding index {issue_index} is not available on this review"
            )
        issue = issues[issue_index]
        if not isinstance(issue, dict):
            raise FindingNotFoundError("Invalid finding payload")
        return issue

    async def _latest_fix(
        self, review_id: UUID, issue_index: int
    ) -> FindingFix | None:
        result = await self._db.execute(
            select(FindingFix)
            .where(
                FindingFix.review_id == str(review_id),
                FindingFix.issue_index == issue_index,
            )
            .order_by(FindingFix.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _parse_fix_response(self, raw: str, *, fallback_path: str) -> dict[str, str]:
        if not raw or not raw.strip():
            raise LLMResponseError("Model returned an empty fix response")

        # 1) Prefer labeled + fenced format (works better on small local models).
        explanation = self._extract_labeled_value(raw, "EXPLANATION") or "AI suggested fix"
        commit_message = (
            self._extract_labeled_value(raw, "COMMIT")
            or f"fix: address finding in {fallback_path}"
        )
        fenced = self._extract_code_fence(raw)
        if fenced and fenced.strip():
            return {
                "file_path": fallback_path,
                "updated_content": fenced,
                "explanation": explanation[:4000],
                "commit_message": commit_message[:255],
            }

        # 2) JSON object (strict or repaired).
        data = extract_json_object(raw)
        if data is not None:
            updated = (
                data.get("updated_content")
                or data.get("content")
                or data.get("code")
                or data.get("fixed_content")
            )
            if isinstance(updated, str) and updated.strip():
                file_path = data.get("file") or data.get("file_path") or fallback_path
                explanation = (
                    data.get("explanation")
                    or data.get("summary")
                    or explanation
                )
                commit_message = (
                    data.get("commit_message")
                    or data.get("message")
                    or commit_message
                )
                return {
                    "file_path": str(file_path),
                    "updated_content": updated,
                    "explanation": str(explanation)[:4000],
                    "commit_message": str(commit_message)[:255],
                }

        # 3) Salvage updated_content from broken JSON via regex.
        salvaged = self._extract_json_string_field(raw, "updated_content")
        if not salvaged:
            salvaged = self._extract_json_string_field(raw, "content")
        if salvaged and salvaged.strip():
            return {
                "file_path": fallback_path,
                "updated_content": salvaged,
                "explanation": explanation[:4000],
                "commit_message": commit_message[:255],
            }

        logger.warning(
            "Unable to parse fix response: %s",
            raw[:300].replace("\n", " "),
        )
        raise LLMResponseError(
            "Model did not return a usable code fix. Try Generate code fix again."
        )

    @staticmethod
    def _extract_labeled_value(text: str, label: str) -> str | None:
        match = re.search(
            rf"^{label}\s*:\s*(.+)$",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if not match:
            return None
        return match.group(1).strip().strip("`").strip()

    @staticmethod
    def _extract_code_fence(text: str) -> str | None:
        matches = re.findall(r"```(?:[\w.+-]*)\s*\n([\s\S]*?)\n```", text)
        if not matches:
            # Unclosed fence: take everything after the opening fence.
            open_match = re.search(r"```(?:[\w.+-]*)\s*\n([\s\S]+)$", text)
            if open_match:
                return open_match.group(1).strip()
            return None
        # Prefer the longest fenced block (likely the full file).
        return max(matches, key=len).strip()

    @staticmethod
    def _extract_json_string_field(text: str, field: str) -> str | None:
        pattern = rf'"{re.escape(field)}"\s*:\s*"'
        match = re.search(pattern, text)
        if not match:
            return None
        idx = match.end()
        chars: list[str] = []
        escape = False
        while idx < len(text):
            ch = text[idx]
            if escape:
                mapping = {
                    "n": "\n",
                    "t": "\t",
                    "r": "\r",
                    '"': '"',
                    "\\": "\\",
                }
                chars.append(mapping.get(ch, ch))
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                return "".join(chars)
            else:
                chars.append(ch)
            idx += 1
        # Truncated string — still useful if we got content.
        return "".join(chars) if chars else None

    def _to_fix_response(
        self, fix: FindingFix, review_id: UUID
    ) -> FixSuggestionResponse:
        return FixSuggestionResponse(
            fix_id=fix.id,
            review_id=str(review_id),
            issue_index=fix.issue_index,
            file_path=fix.file_path,
            original_content=fix.original_content,
            updated_content=fix.updated_content,
            explanation=fix.explanation,
            commit_message=fix.commit_message,
            pr_url=fix.pr_url,
            pr_number=fix.pr_number,
            created_at=fix.created_at,
        )
