from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from .models import ProblemArtifact


class ProblemProviderError(RuntimeError):
    """Base exception for problem providers."""


class ProblemNotFoundError(ProblemProviderError):
    """Raised when a requested problem cannot be found."""


@dataclass(frozen=True)
class _QuestionSummary:
    frontend_question_id: str
    title: str
    title_cn: str
    title_slug: str


class _LeetCodeHtmlToMarkdownParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._list_stack: list[dict[str, int]] = []
        self._in_pre = False
        self._in_code = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"p", "div", "section", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._ensure_blank_line()
            return
        if tag == "br":
            self._append("\n")
            return
        if tag == "pre":
            self._ensure_blank_line()
            self._append("```text\n")
            self._in_pre = True
            return
        if tag == "code" and not self._in_pre:
            self._append("`")
            self._in_code = True
            return
        if tag == "ul":
            self._ensure_blank_line()
            self._list_stack.append({"type": "ul", "index": 0})
            return
        if tag == "ol":
            self._ensure_blank_line()
            self._list_stack.append({"type": "ol", "index": 0})
            return
        if tag == "li":
            self._ensure_line_start()
            depth = max(len(self._list_stack) - 1, 0)
            indent = "  " * depth
            if self._list_stack and self._list_stack[-1]["type"] == "ol":
                self._list_stack[-1]["index"] += 1
                marker = f"{self._list_stack[-1]['index']}. "
            else:
                marker = "- "
            self._append(f"{indent}{marker}")
            return
        if tag == "sup":
            self._append("^")
            return
        if tag == "sub":
            self._append("_")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "section", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._ensure_blank_line()
            return
        if tag == "pre":
            if self._parts and not self._parts[-1].endswith("\n"):
                self._append("\n")
            self._append("```\n\n")
            self._in_pre = False
            return
        if tag == "code" and self._in_code and not self._in_pre:
            self._append("`")
            self._in_code = False
            return
        if tag == "li":
            self._append("\n")
            return
        if tag in {"ul", "ol"}:
            if self._list_stack:
                self._list_stack.pop()
            self._ensure_blank_line()

    def handle_data(self, data: str) -> None:
        if not data:
            return
        text = data.replace("\xa0", " ")
        if self._in_pre:
            self._append(text)
            return
        compact = re.sub(r"\s+", " ", text)
        if compact:
            self._append(compact)

    def get_markdown(self) -> str:
        text = "".join(self._parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _append(self, text: str) -> None:
        if not text:
            return
        if self._in_pre:
            self._parts.append(text)
            return

        if text == "\n":
            if not self._parts:
                return
            if self._parts[-1].endswith("\n"):
                return
            self._parts.append("\n")
            return

        if self._parts:
            previous = self._parts[-1]
            if previous.endswith("\n") and text.startswith(" "):
                text = text.lstrip()
            if previous and not previous.endswith((" ", "\n", "`", "^", "_")) and not text.startswith((" ", "\n", ".", ",", "。", "，", "：", "；", "！", "？", "`", "^", "_")):
                self._parts.append(" ")
        self._parts.append(text)

    def _ensure_blank_line(self) -> None:
        if not self._parts:
            return
        tail = "".join(self._parts[-2:]) if len(self._parts) >= 2 else self._parts[-1]
        if tail.endswith("\n\n"):
            return
        if tail.endswith("\n"):
            self._parts.append("\n")
            return
        self._parts.append("\n\n")

    def _ensure_line_start(self) -> None:
        if not self._parts:
            return
        if self._parts[-1].endswith("\n"):
            return
        self._parts.append("\n")


def leetcode_html_to_markdown(html: str) -> str:
    parser = _LeetCodeHtmlToMarkdownParser()
    parser.feed(html)
    parser.close()
    return parser.get_markdown()


class LeetCodeCNProvider:
    graphql_url = "https://leetcode.cn/graphql/"
    source_name = "leetcode.cn"

    _QUESTION_LIST_QUERY = """
    query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
      problemsetQuestionList(categorySlug: $categorySlug, limit: $limit, skip: $skip, filters: $filters) {
        total
        questions {
          frontendQuestionId
          title
          titleCn
          titleSlug
        }
      }
    }
    """

    _QUESTION_DETAIL_QUERY = """
    query questionData($titleSlug: String!) {
      question(titleSlug: $titleSlug) {
        questionId
        questionFrontendId
        title
        titleSlug
        translatedTitle
        content
        translatedContent
        difficulty
        isPaidOnly
        topicTags {
          name
          slug
          translatedName
        }
      }
    }
    """

    def __init__(self, timeout_sec: float = 15.0, page_size: int = 100):
        self.timeout_sec = timeout_sec
        self.page_size = max(20, page_size)

    def fetch_by_frontend_id(self, problem_id: str) -> ProblemArtifact:
        normalized_problem_id = self._normalize_problem_id(problem_id)
        if not normalized_problem_id:
            raise ProblemProviderError("题号不能为空")

        summary = self._find_question_summary(normalized_problem_id)
        if summary is None:
            raise ProblemNotFoundError(f"在 LeetCode 中文站题库中未找到题号 {normalized_problem_id}")

        detail = self._fetch_question_detail(summary.title_slug)
        title = str(detail.get("translatedTitle") or summary.title_cn or detail.get("title") or summary.title).strip()
        content_html = str(detail.get("translatedContent") or detail.get("content") or "").strip()
        if not title or not content_html:
            raise ProblemProviderError(f"LeetCode 中文站返回了不完整的题面数据，题号: {normalized_problem_id}")

        statement_markdown = self._build_problem_markdown(normalized_problem_id, title, content_html)
        topic_tags = detail.get("topicTags") or []
        metadata: dict[str, Any] = {
            "provider": "leetcode.cn/graphql",
            "question_id": str(detail.get("questionId") or ""),
            "title_slug": str(detail.get("titleSlug") or summary.title_slug),
            "difficulty": str(detail.get("difficulty") or ""),
            "is_paid_only": bool(detail.get("isPaidOnly")),
            "topic_tags": [
                {
                    "name": str(item.get("name") or ""),
                    "slug": str(item.get("slug") or ""),
                    "translated_name": str(item.get("translatedName") or ""),
                }
                for item in topic_tags
                if isinstance(item, dict)
            ],
        }

        return ProblemArtifact(
            problem_id=str(detail.get("questionFrontendId") or normalized_problem_id),
            title=title,
            slug=str(detail.get("titleSlug") or summary.title_slug),
            source=self.source_name,
            language="zh-CN",
            statement_markdown=statement_markdown,
            metadata=metadata,
        )

    def _find_question_summary(self, problem_id: str) -> _QuestionSummary | None:
        if problem_id.isdigit():
            approximate_skip = max(int(problem_id) - (self.page_size // 2) - 1, 0)
            candidates = self._fetch_question_summaries(skip=approximate_skip, limit=self.page_size)
            match = self._find_summary_match(problem_id, candidates)
            if match is not None:
                return match

        total = 0
        skip = 0
        while skip == 0 or skip < total:
            questions, total = self._fetch_question_summaries(skip=skip, limit=self.page_size, with_total=True)
            match = self._find_summary_match(problem_id, questions)
            if match is not None:
                return match
            if not questions:
                break
            skip += len(questions)
        return None

    def _fetch_question_summaries(
        self,
        *,
        skip: int,
        limit: int,
        with_total: bool = False,
    ) -> tuple[list[_QuestionSummary], int] | list[_QuestionSummary]:
        payload = self._graphql(
            self._QUESTION_LIST_QUERY,
            {
                "categorySlug": "",
                "skip": skip,
                "limit": limit,
                "filters": {},
            },
        )
        node = payload.get("problemsetQuestionList") or {}
        questions_raw = node.get("questions") or []
        questions = [
            _QuestionSummary(
                frontend_question_id=self._normalize_problem_id(str(item.get("frontendQuestionId") or "")),
                title=str(item.get("title") or ""),
                title_cn=str(item.get("titleCn") or ""),
                title_slug=str(item.get("titleSlug") or ""),
            )
            for item in questions_raw
            if isinstance(item, dict)
        ]
        if with_total:
            return questions, int(node.get("total") or 0)
        return questions

    def _fetch_question_detail(self, title_slug: str) -> dict[str, Any]:
        payload = self._graphql(self._QUESTION_DETAIL_QUERY, {"titleSlug": title_slug})
        question = payload.get("question")
        if not isinstance(question, dict):
            raise ProblemProviderError(f"LeetCode 中文站未返回题目详情，slug: {title_slug}")
        return question

    def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        request_body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        request = urllib.request.Request(
            self.graphql_url,
            data=request_body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": "https://leetcode.cn",
                "Referer": "https://leetcode.cn/problemset/",
                "User-Agent": "Mozilla/5.0 (compatible; leetanim/0.1.0)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ProblemProviderError(f"LeetCode 中文站 HTTP {exc.code}: {body}") from exc
        except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
            raise ProblemProviderError(f"连接 LeetCode 中文站失败: {exc}") from exc

        payload = json.loads(raw)
        errors = payload.get("errors") or []
        if errors:
            message = "; ".join(str(item.get("message") or item) for item in errors)
            raise ProblemProviderError(f"LeetCode 中文站 GraphQL 错误: {message}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ProblemProviderError(f"LeetCode 中文站返回了无法识别的数据: {payload}")
        return data

    @staticmethod
    def _build_problem_markdown(problem_id: str, title: str, content_html: str) -> str:
        body = leetcode_html_to_markdown(content_html)
        body = body.strip()
        return f"# {problem_id}. {title}\n\n{body}\n"

    @staticmethod
    def _find_summary_match(problem_id: str, questions: list[_QuestionSummary]) -> _QuestionSummary | None:
        for question in questions:
            if question.frontend_question_id == problem_id:
                return question
        return None

    @staticmethod
    def _normalize_problem_id(problem_id: str) -> str:
        cleaned = str(problem_id).strip()
        if cleaned.isdigit():
            return str(int(cleaned))
        return re.sub(r"\s+", " ", cleaned)
