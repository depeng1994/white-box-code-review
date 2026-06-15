#!/usr/bin/env python3
"""Summarize human review comments and MR evaluations for a GitCode PR."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


API_BASE = "https://api.gitcode.com/api/v5"
MR_EVAL_KEYWORD = "【MR评价】"
DEFAULT_PER_PAGE = 100
SYSTEM_USER_MARKERS = (
    "robot",
    "bot",
    "jenkins",
    "pipeline",
    "devops",
    "system",
    "openlibingci",
    "openlibing.ci",
)


@dataclass(frozen=True)
class PullRequestRef:
    owner: str
    repo: str
    number: int


@dataclass(frozen=True)
class ReviewComment:
    comment_id: int
    author: str
    created_at: str
    updated_at: str
    path: str
    line: str
    body: str


@dataclass(frozen=True)
class MrEvaluation:
    comment_id: int
    author: str
    created_at: str
    score: str
    body: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch a GitCode PR and print human inline review comments plus "
            "PR comments containing the 【MR评价】 keyword."
        )
    )
    parser.add_argument(
        "pr",
        help=(
            "GitCode PR URL, for example "
            "https://gitcode.com/cann/torchtitan-npu/pull/350"
        ),
    )
    parser.add_argument(
        "--token-env",
        default="GITCODE_API_TOKEN",
        help="environment variable that stores the GitCode access token",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=DEFAULT_PER_PAGE,
        help="page size for the GitCode comments API",
    )
    parser.add_argument(
        "--include-system-users",
        action="store_true",
        help="include robot, CI, and other system-like users",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit JSON instead of Markdown tables",
    )
    return parser.parse_args()


def parse_pr_ref(raw: str) -> PullRequestRef:
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme and parsed.netloc:
        path = parsed.path.strip("/")
    else:
        path = raw.strip("/")

    match = re.fullmatch(r"([^/]+)/([^/]+)/pull/(\d+)", path)
    if not match:
        raise ValueError(
            "PR 参数格式不正确，应为 https://gitcode.com/<owner>/<repo>/pull/<number>"
        )

    owner, repo, number = match.groups()
    return PullRequestRef(owner=owner, repo=repo, number=int(number))


def api_get(path: str, token: str, params: dict[str, Any] | None = None) -> Any:
    query = dict(params or {})
    query["access_token"] = token
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitCode API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitCode API request failed: {exc}") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GitCode API returned non-JSON payload: {payload[:200]}") from exc


def fetch_all_comments(pr_ref: PullRequestRef, token: str, per_page: int) -> list[dict[str, Any]]:
    all_comments: list[dict[str, Any]] = []
    page = 1
    while True:
        comments = api_get(
            f"/repos/{pr_ref.owner}/{pr_ref.repo}/pulls/{pr_ref.number}/comments",
            token,
            {"per_page": per_page, "page": page},
        )
        if not isinstance(comments, list):
            raise RuntimeError(f"unexpected comments response: {comments!r}")
        if not comments:
            break
        all_comments.extend(comments)
        if len(comments) < per_page:
            break
        page += 1
    return all_comments


def fetch_comment_detail(pr_ref: PullRequestRef, token: str, comment_id: int) -> dict[str, Any]:
    detail = api_get(
        f"/repos/{pr_ref.owner}/{pr_ref.repo}/pulls/comments/{comment_id}",
        token,
    )
    if not isinstance(detail, dict):
        raise RuntimeError(f"unexpected comment detail response for {comment_id}: {detail!r}")
    return detail


def user_login(comment: dict[str, Any]) -> str:
    user = comment.get("user")
    if isinstance(user, dict):
        return str(user.get("login") or user.get("name") or user.get("id") or "")
    if isinstance(user, str):
        return user
    return ""


def is_system_user(comment: dict[str, Any]) -> bool:
    user = comment.get("user")
    values: list[str] = []
    if isinstance(user, dict):
        for key in ("login", "name", "type"):
            value = user.get(key)
            if value:
                values.append(str(value))
    elif user:
        values.append(str(user))

    haystack = " ".join(values).lower()
    if any(marker in haystack for marker in SYSTEM_USER_MARKERS):
        return True

    body = str(comment.get("body") or "").lower()
    return "【openlibing.ci】" in body


def is_inline_review(comment: dict[str, Any]) -> bool:
    return (comment.get("comment_type") or "") != "pr_comment"


def compact_text(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def extract_position(detail: dict[str, Any]) -> tuple[str, str]:
    position = detail.get("position")
    if not isinstance(position, dict):
        path = detail.get("path")
        return str(path or ""), ""

    path = position.get("new_path") or position.get("old_path") or detail.get("path") or ""
    line = position.get("new_line")
    if line is None:
        line = position.get("old_line")
    return str(path), "" if line is None else str(line)


def extract_review_comments(
    pr_ref: PullRequestRef,
    token: str,
    comments: list[dict[str, Any]],
    include_system_users: bool,
) -> list[ReviewComment]:
    reviews: list[ReviewComment] = []
    for comment in comments:
        if not is_inline_review(comment):
            continue
        if not include_system_users and is_system_user(comment):
            continue

        detail = fetch_comment_detail(pr_ref, token, int(comment["id"]))
        if not include_system_users and is_system_user(detail):
            continue

        path, line = extract_position(detail)
        reviews.append(
            ReviewComment(
                comment_id=int(detail.get("id") or comment["id"]),
                author=user_login(detail) or user_login(comment),
                created_at=str(detail.get("created_at") or comment.get("created_at") or ""),
                updated_at=str(detail.get("updated_at") or comment.get("updated_at") or ""),
                path=path,
                line=line,
                body=compact_text(str(detail.get("body") or comment.get("body") or "")),
            )
        )
    return reviews


def extract_score(body: str) -> str:
    match = re.search(r"评价分数[:：]\s*([0-9]+(?:\.[0-9]+)?)", body)
    return match.group(1) if match else ""


def extract_mr_evaluations(
    comments: list[dict[str, Any]],
    include_system_users: bool,
) -> list[MrEvaluation]:
    evaluations: list[MrEvaluation] = []
    for comment in comments:
        body = str(comment.get("body") or "")
        if MR_EVAL_KEYWORD not in body:
            continue
        if not include_system_users and is_system_user(comment):
            continue

        compact_body = compact_text(body)
        evaluations.append(
            MrEvaluation(
                comment_id=int(comment["id"]),
                author=user_login(comment),
                created_at=str(comment.get("created_at") or ""),
                score=extract_score(compact_body),
                body=compact_body,
            )
        )
    return evaluations


def markdown_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|")


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    escaped_headers = [markdown_escape(header) for header in headers]
    lines = [
        "| " + " | ".join(escaped_headers) + " |",
        "| " + " | ".join("---" for _ in escaped_headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(markdown_escape(cell) for cell in row) + " |")
    return "\n".join(lines)


def trim_for_table(value: str, width: int = 160) -> str:
    return textwrap.shorten(value, width=width, placeholder="...")


def print_markdown(pr_ref: PullRequestRef, reviews: list[ReviewComment], evaluations: list[MrEvaluation]) -> None:
    print(f"# GitCode PR 检视意见汇总")
    print()
    print(f"- PR: https://gitcode.com/{pr_ref.owner}/{pr_ref.repo}/pull/{pr_ref.number}")
    print(f"- 行内检视意见: {len(reviews)}")
    print(f"- {MR_EVAL_KEYWORD} 评论: {len(evaluations)}")
    print()

    print("## 行内检视意见")
    if reviews:
        print(
            markdown_table(
                ["ID", "作者", "时间", "文件/行号", "意见"],
                [
                    [
                        str(item.comment_id),
                        item.author,
                        item.created_at,
                        f"{item.path}:{item.line}" if item.line else item.path,
                        trim_for_table(item.body),
                    ]
                    for item in reviews
                ],
            )
        )
    else:
        print("无")
    print()

    print(f"## 带 {MR_EVAL_KEYWORD} 的 PR 评论")
    if evaluations:
        print(
            markdown_table(
                ["ID", "作者", "时间", "评分", "评价内容"],
                [
                    [
                        str(item.comment_id),
                        item.author,
                        item.created_at,
                        item.score,
                        trim_for_table(item.body),
                    ]
                    for item in evaluations
                ],
            )
        )
    else:
        print("无")


def print_json(reviews: list[ReviewComment], evaluations: list[MrEvaluation]) -> None:
    payload = {
        "review_comments": [item.__dict__ for item in reviews],
        "mr_evaluations": [item.__dict__ for item in evaluations],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    token = os.environ.get(args.token_env)
    if not token:
        print(f"error: missing ${args.token_env}", file=sys.stderr)
        return 2
    if args.per_page <= 0:
        print("error: --per-page must be positive", file=sys.stderr)
        return 2

    try:
        pr_ref = parse_pr_ref(args.pr)
        comments = fetch_all_comments(pr_ref, token, args.per_page)
        reviews = extract_review_comments(
            pr_ref,
            token,
            comments,
            include_system_users=args.include_system_users,
        )
        evaluations = extract_mr_evaluations(
            comments,
            include_system_users=args.include_system_users,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print_json(reviews, evaluations)
    else:
        print_markdown(pr_ref, reviews, evaluations)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
