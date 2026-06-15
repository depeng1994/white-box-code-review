#!/usr/bin/env python3
"""Collect merged GitCode PR review data and serve the review dashboard."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


API_BASE = "https://api.gitcode.com/api/v5"
DEFAULT_OWNER = "cann"
DEFAULT_REPO = "torchtitan-npu"
DEFAULT_DB = Path("data/review_board.sqlite3")
DEFAULT_STATIC_DIR = Path("demo")
MR_EVAL_KEYWORD = "【MR评价】"
LGTM_PATTERN = re.compile(r"(?im)(^|\s)/lgtm(?=$|\s|[。；;,.，、])")
EVALUATION_DIMENSION_PATTERN = re.compile(
    r"(编码规范遵守度|代码设计|DT质量|测试质量|功能质量|性能|安全|可维护性)\s*[:：]"
)
TZ = ZoneInfo("Asia/Shanghai")
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
class RepoRef:
    owner: str
    repo: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(TZ)


def iso(dt: datetime) -> str:
    return dt.astimezone(TZ).isoformat()


def now_tz() -> datetime:
    return datetime.now(TZ)


def month_window(month: str | None) -> tuple[datetime, datetime]:
    if month:
        start = datetime.strptime(month, "%Y-%m").replace(tzinfo=TZ)
    else:
        current = now_tz()
        start = datetime(current.year, current.month, 1, tzinfo=TZ)
    if start.month == 12:
        end = datetime(start.year + 1, 1, 1, tzinfo=TZ)
    else:
        end = datetime(start.year, start.month + 1, 1, tzinfo=TZ)
    return start, end


def day_window(day: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=TZ)
    return start, start + timedelta(days=1)


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


def extract_score(body: str) -> float | None:
    match = re.search(r"评价分数[:：]\s*([0-9]+(?:\.[0-9]+)?)", body)
    return float(match.group(1)) if match else None


def is_lgtm_body(body: str) -> bool:
    return LGTM_PATTERN.search(body) is not None


def evaluation_opinion_empty(body: str) -> bool:
    match = re.search(r"评价意见\s*[:：]\s*(.*)", body)
    if not match:
        return False
    tail = match.group(1)
    dimension = EVALUATION_DIMENSION_PATTERN.search(tail)
    opinion = tail[: dimension.start()] if dimension else tail
    opinion = re.sub(r"[\s,，;；。:：、-]+", "", opinion)
    return not opinion


def score_value(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def extract_position(detail: dict[str, Any]) -> tuple[str, int | None]:
    position = detail.get("position")
    if not isinstance(position, dict):
        return str(detail.get("path") or ""), None

    path = position.get("new_path") or position.get("old_path") or detail.get("path") or ""
    line = position.get("new_line")
    if line is None:
        line = position.get("old_line")
    return str(path), int(line) if line is not None else None


class GitCodeClient:
    def __init__(self, token: str) -> None:
        self.token = token
        self.min_interval = 0.75
        self._last_request_at = 0.0

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = dict(params or {})
        query["access_token"] = self.token
        url = f"{API_BASE}{path}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        for attempt in range(4):
            self._throttle()
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if exc.code in {400, 429} and "429" in detail and attempt < 3:
                    time.sleep(65)
                    continue
                raise RuntimeError(f"GitCode API HTTP {exc.code}: {detail}") from exc
        raise RuntimeError("GitCode API retry exhausted")

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_at = time.monotonic()

    def list_merged_pulls(self, repo: RepoRef, start: datetime, end: datetime) -> list[dict[str, Any]]:
        pulls: list[dict[str, Any]] = []
        page = 1
        while True:
            items = self.get(
                f"/repos/{repo.owner}/{repo.repo}/pulls",
                {
                    "state": "merged",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": 100,
                    "page": page,
                },
            )
            if not isinstance(items, list):
                raise RuntimeError(f"unexpected pulls response: {items!r}")
            if not items:
                break

            page_has_window_item = False
            page_has_newer_item = False
            for item in items:
                merged_at = parse_dt(item.get("merged_at"))
                if merged_at is None:
                    continue
                if merged_at >= start:
                    page_has_newer_item = True
                if start <= merged_at < end:
                    pulls.append(item)
                    page_has_window_item = True

            if len(items) < 100:
                break
            if not page_has_window_item and not page_has_newer_item:
                break
            page += 1
        return sorted(pulls, key=lambda item: item.get("merged_at") or "")

    def list_comments(self, repo: RepoRef, pr_number: int) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        page = 1
        while True:
            items = self.get(
                f"/repos/{repo.owner}/{repo.repo}/pulls/{pr_number}/comments",
                {"per_page": 100, "page": page},
            )
            if not isinstance(items, list):
                raise RuntimeError(f"unexpected comments response: {items!r}")
            if not items:
                break
            comments.extend(items)
            if len(items) < 100:
                break
            page += 1
        return comments

    def comment_detail(self, repo: RepoRef, comment_id: int) -> dict[str, Any]:
        detail = self.get(f"/repos/{repo.owner}/{repo.repo}/pulls/comments/{comment_id}")
        if not isinstance(detail, dict):
            raise RuntimeError(f"unexpected comment detail for {comment_id}: {detail!r}")
        return detail


class ReviewStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS pull_requests (
                    repo TEXT NOT NULL,
                    pr_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT NOT NULL,
                    state TEXT NOT NULL,
                    html_url TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT,
                    merged_at TEXT NOT NULL,
                    added_lines INTEGER NOT NULL DEFAULT 0,
                    removed_lines INTEGER NOT NULL DEFAULT 0,
                    raw_json TEXT NOT NULL,
                    PRIMARY KEY (repo, pr_number)
                );

                CREATE TABLE IF NOT EXISTS review_comments (
                    repo TEXT NOT NULL,
                    pr_number INTEGER NOT NULL,
                    comment_id INTEGER PRIMARY KEY,
                    author TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT,
                    file_path TEXT,
                    line INTEGER,
                    body TEXT NOT NULL,
                    is_system_comment INTEGER NOT NULL DEFAULT 0,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mr_evaluations (
                    repo TEXT NOT NULL,
                    pr_number INTEGER NOT NULL,
                    comment_id INTEGER PRIMARY KEY,
                    author TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT,
                    score REAL,
                    body TEXT NOT NULL,
                    is_system_comment INTEGER NOT NULL DEFAULT 0,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS lgtm_comments (
                    repo TEXT NOT NULL,
                    pr_number INTEGER NOT NULL,
                    comment_id INTEGER PRIMARY KEY,
                    author TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT,
                    body TEXT NOT NULL,
                    is_system_comment INTEGER NOT NULL DEFAULT 0,
                    raw_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    window_start TEXT NOT NULL,
                    window_end TEXT NOT NULL,
                    status TEXT NOT NULL,
                    pr_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_pr_merged_at ON pull_requests (merged_at);
                CREATE INDEX IF NOT EXISTS idx_pr_author ON pull_requests (author);
                CREATE INDEX IF NOT EXISTS idx_review_pr ON review_comments (repo, pr_number);
                CREATE INDEX IF NOT EXISTS idx_review_author ON review_comments (author);
                CREATE INDEX IF NOT EXISTS idx_eval_pr ON mr_evaluations (repo, pr_number);
                CREATE INDEX IF NOT EXISTS idx_eval_author ON mr_evaluations (author);
                CREATE INDEX IF NOT EXISTS idx_lgtm_pr ON lgtm_comments (repo, pr_number);
                CREATE INDEX IF NOT EXISTS idx_lgtm_author ON lgtm_comments (author);
                """
            )
            self._migrate_score_column(conn)
            self.refresh_scores_from_bodies(conn)
        self.checkpoint()

    def checkpoint(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def _migrate_score_column(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"]: row for row in conn.execute("PRAGMA table_info(mr_evaluations)")}
        if columns.get("score") and str(columns["score"]["type"]).upper() == "REAL":
            return
        conn.executescript(
            """
            ALTER TABLE mr_evaluations RENAME TO mr_evaluations_old;

            CREATE TABLE mr_evaluations (
                repo TEXT NOT NULL,
                pr_number INTEGER NOT NULL,
                comment_id INTEGER PRIMARY KEY,
                author TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT,
                score REAL,
                body TEXT NOT NULL,
                is_system_comment INTEGER NOT NULL DEFAULT 0,
                raw_json TEXT NOT NULL
            );

            INSERT INTO mr_evaluations (
                repo, pr_number, comment_id, author, created_at, updated_at,
                score, body, is_system_comment, raw_json
            )
            SELECT
                repo, pr_number, comment_id, author, created_at, updated_at,
                score, body, is_system_comment, raw_json
            FROM mr_evaluations_old;

            DROP TABLE mr_evaluations_old;
            CREATE INDEX IF NOT EXISTS idx_eval_pr ON mr_evaluations (repo, pr_number);
            CREATE INDEX IF NOT EXISTS idx_eval_author ON mr_evaluations (author);
            """
        )

    def refresh_scores_from_bodies(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT comment_id, body FROM mr_evaluations").fetchall()
        for row in rows:
            score = extract_score(row["body"])
            conn.execute("UPDATE mr_evaluations SET score = ? WHERE comment_id = ?", (score, row["comment_id"]))

    def begin_sync(self, repo: RepoRef, start: datetime, end: datetime) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO sync_runs (repo, started_at, window_start, window_end, status)
                VALUES (?, ?, ?, ?, 'running')
                """,
                (repo.full_name, iso(now_tz()), iso(start), iso(end)),
            )
            return int(cur.lastrowid)

    def finish_sync(self, run_id: int, status: str, pr_count: int, error: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET finished_at = ?, status = ?, pr_count = ?, error = ?
                WHERE id = ?
                """,
                (iso(now_tz()), status, pr_count, error, run_id),
            )
        self.checkpoint()

    def upsert_pr(self, conn: sqlite3.Connection, repo: RepoRef, pr: dict[str, Any]) -> None:
        author = ""
        if isinstance(pr.get("user"), dict):
            author = str(pr["user"].get("login") or pr["user"].get("name") or "")
        conn.execute(
            """
            INSERT OR REPLACE INTO pull_requests (
                repo, pr_number, title, author, state, html_url, created_at, updated_at,
                merged_at, added_lines, removed_lines, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                repo.full_name,
                int(pr["number"]),
                str(pr.get("title") or ""),
                author,
                str(pr.get("state") or ""),
                str(pr.get("html_url") or pr.get("web_url") or ""),
                str(pr.get("created_at") or ""),
                str(pr.get("updated_at") or ""),
                str(pr.get("merged_at") or ""),
                int(pr.get("added_lines") or 0),
                int(pr.get("removed_lines") or 0),
                json.dumps(pr, ensure_ascii=False),
            ),
        )

    def replace_pr_comments(
        self,
        conn: sqlite3.Connection,
        repo: RepoRef,
        pr_number: int,
        reviews: list[dict[str, Any]],
        evaluations: list[dict[str, Any]],
        lgtms: list[dict[str, Any]],
    ) -> None:
        conn.execute("DELETE FROM review_comments WHERE repo = ? AND pr_number = ?", (repo.full_name, pr_number))
        conn.execute("DELETE FROM mr_evaluations WHERE repo = ? AND pr_number = ?", (repo.full_name, pr_number))
        conn.execute("DELETE FROM lgtm_comments WHERE repo = ? AND pr_number = ?", (repo.full_name, pr_number))

        conn.executemany(
            """
            INSERT INTO review_comments (
                repo, pr_number, comment_id, author, created_at, updated_at,
                file_path, line, body, is_system_comment, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    repo.full_name,
                    pr_number,
                    item["comment_id"],
                    item["author"],
                    item["created_at"],
                    item["updated_at"],
                    item["file_path"],
                    item["line"],
                    item["body"],
                    int(item["is_system_comment"]),
                    json.dumps(item["raw"], ensure_ascii=False),
                )
                for item in reviews
            ],
        )

        conn.executemany(
            """
            INSERT INTO mr_evaluations (
                repo, pr_number, comment_id, author, created_at, updated_at,
                score, body, is_system_comment, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    repo.full_name,
                    pr_number,
                    item["comment_id"],
                    item["author"],
                    item["created_at"],
                    item["updated_at"],
                    item["score"],
                    item["body"],
                    int(item["is_system_comment"]),
                    json.dumps(item["raw"], ensure_ascii=False),
                )
                for item in evaluations
            ],
        )

        conn.executemany(
            """
            INSERT INTO lgtm_comments (
                repo, pr_number, comment_id, author, created_at, updated_at,
                body, is_system_comment, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    repo.full_name,
                    pr_number,
                    item["comment_id"],
                    item["author"],
                    item["created_at"],
                    item["updated_at"],
                    item["body"],
                    int(item["is_system_comment"]),
                    json.dumps(item["raw"], ensure_ascii=False),
                )
                for item in lgtms
            ],
        )


class Collector:
    def __init__(self, client: GitCodeClient, store: ReviewStore, repo: RepoRef) -> None:
        self.client = client
        self.store = store
        self.repo = repo

    def sync_month(self, month: str | None = None) -> int:
        start, end = month_window(month)
        return self.sync_window(start, end)

    def sync_day(self, day: str) -> int:
        start, end = day_window(day)
        return self.sync_window(start, end)

    def sync_window(self, start: datetime, end: datetime) -> int:
        run_id = self.store.begin_sync(self.repo, start, end)
        pr_count = 0
        try:
            pulls = self.client.list_merged_pulls(self.repo, start, end)
            for pr in pulls:
                with self.store.connect() as conn:
                    pr_number = int(pr["number"])
                    self.store.upsert_pr(conn, self.repo, pr)
                    comments = self.client.list_comments(self.repo, pr_number)
                    reviews, evaluations, lgtms = self._extract_comments(pr_number, comments)
                    self.store.replace_pr_comments(conn, self.repo, pr_number, reviews, evaluations, lgtms)
                pr_count += 1
            self.store.finish_sync(run_id, "success", pr_count)
            return pr_count
        except Exception as exc:
            self.store.finish_sync(run_id, "failed", pr_count, str(exc))
            raise

    def _extract_comments(
        self,
        pr_number: int,
        comments: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        reviews: list[dict[str, Any]] = []
        evaluations: list[dict[str, Any]] = []
        lgtms: list[dict[str, Any]] = []
        for comment in comments:
            body = str(comment.get("body") or "")
            system = is_system_user(comment)

            if is_inline_review(comment):
                detail = self.client.comment_detail(self.repo, int(comment["id"]))
                detail_system = is_system_user(detail)
                if detail_system:
                    continue
                file_path, line = extract_position(detail)
                reviews.append(
                    {
                        "comment_id": int(detail.get("id") or comment["id"]),
                        "author": user_login(detail) or user_login(comment),
                        "created_at": str(detail.get("created_at") or comment.get("created_at") or ""),
                        "updated_at": str(detail.get("updated_at") or comment.get("updated_at") or ""),
                        "file_path": file_path,
                        "line": line,
                        "body": compact_text(str(detail.get("body") or body)),
                        "is_system_comment": False,
                        "raw": detail,
                    }
                )
                continue

            if MR_EVAL_KEYWORD in body and not system:
                compact = compact_text(body)
                evaluations.append(
                    {
                        "comment_id": int(comment["id"]),
                        "author": user_login(comment),
                        "created_at": str(comment.get("created_at") or ""),
                        "updated_at": str(comment.get("updated_at") or ""),
                        "score": extract_score(compact),
                        "body": compact,
                        "is_system_comment": False,
                        "raw": comment,
                    }
                )
            if is_lgtm_body(body) and not system:
                compact = compact_text(body)
                lgtms.append(
                    {
                        "comment_id": int(comment["id"]),
                        "author": user_login(comment),
                        "created_at": str(comment.get("created_at") or ""),
                        "updated_at": str(comment.get("updated_at") or ""),
                        "body": compact,
                        "is_system_comment": False,
                        "raw": comment,
                    }
                )
        return reviews, evaluations, lgtms


def period_window(period: str, range_label: str | None) -> tuple[datetime, datetime, str]:
    current = now_tz()
    if period == "month":
        start, end = month_window(range_label)
        return start, end, start.strftime("%Y-%m")
    if period == "week":
        if range_label:
            year, week = map(int, re.findall(r"\d+", range_label)[:2])
            start_date = datetime.fromisocalendar(year, week, 1).replace(tzinfo=TZ)
        else:
            today = current.date()
            start_date = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time(), TZ)
        return start_date, start_date + timedelta(days=7), f"{start_date.isocalendar().year}年第{start_date.isocalendar().week:02d}周"
    if period == "quarter":
        if range_label:
            year, quarter = map(int, re.findall(r"\d+", range_label)[:2])
            month = (quarter - 1) * 3 + 1
        else:
            year = current.year
            month = ((current.month - 1) // 3) * 3 + 1
            quarter = (month - 1) // 3 + 1
        start = datetime(year, month, 1, tzinfo=TZ)
        end_month = month + 3
        end = datetime(year + (end_month - 1) // 12, ((end_month - 1) % 12) + 1, 1, tzinfo=TZ)
        return start, end, f"{year} Q{quarter}"
    if period == "half":
        if range_label:
            year = int(re.search(r"\d{4}", range_label).group(0))  # type: ignore[union-attr]
            half = 1 if "H1" in range_label else 2
        else:
            year = current.year
            half = 1 if current.month <= 6 else 2
        start = datetime(year, 1 if half == 1 else 7, 1, tzinfo=TZ)
        end = datetime(year, 7 if half == 1 else 1, 1, tzinfo=TZ)
        if half == 2:
            end = datetime(year + 1, 1, 1, tzinfo=TZ)
        return start, end, f"{year} H{half}"
    if period == "year":
        year = int(re.search(r"\d{4}", range_label or str(current.year)).group(0))  # type: ignore[union-attr]
        return datetime(year, 1, 1, tzinfo=TZ), datetime(year + 1, 1, 1, tzinfo=TZ), f"{year} 全年"
    raise ValueError(f"unsupported period: {period}")


def score_level(score: float | None) -> str:
    if score is None:
        return "未评分"
    if score < 3:
        return "待改进"
    if score > 3:
        return "优秀"
    return "达标"


def primary_evaluation(evals: list[sqlite3.Row]) -> sqlite3.Row | None:
    if not evals:
        return None
    return sorted(evals, key=lambda row: (row["created_at"] or "", row["comment_id"] or 0))[0]


def latest_lgtm(lgtms: list[sqlite3.Row]) -> sqlite3.Row | None:
    if not lgtms:
        return None
    return sorted(lgtms, key=lambda row: (row["created_at"] or "", row["comment_id"] or 0))[-1]


def nonstandard_reason(evaluation: sqlite3.Row | None) -> str:
    if evaluation is None:
        return "只有LGTM无评分"
    score = score_value(evaluation["score"])
    if score is not None and score != 3 and evaluation_opinion_empty(str(evaluation["body"] or "")):
        return "非3分且评价意见为空"
    return ""


class DashboardQueries:
    def __init__(self, store: ReviewStore, repo: RepoRef) -> None:
        self.store = store
        self.repo = repo

    def dashboard(self, period: str, range_label: str | None) -> dict[str, Any]:
        start, end, label = period_window(period, range_label)
        with self.store.connect() as conn:
            prs = conn.execute(
                """
                SELECT * FROM pull_requests
                WHERE repo = ? AND merged_at >= ? AND merged_at < ?
                ORDER BY merged_at DESC
                """,
                (self.repo.full_name, iso(start), iso(end)),
            ).fetchall()
            pr_numbers = [int(row["pr_number"]) for row in prs]
            reviews_by_pr = self._group_rows(conn, "review_comments", pr_numbers)
            evals_by_pr = self._group_rows(conn, "mr_evaluations", pr_numbers)
            lgtms_by_pr = self._group_rows(conn, "lgtm_comments", pr_numbers)
            sync = conn.execute(
                "SELECT * FROM sync_runs WHERE repo = ? ORDER BY id DESC LIMIT 1",
                (self.repo.full_name,),
            ).fetchone()

        pr_payload = []
        contributor_map: dict[str, dict[str, Any]] = {}
        total_lines = 0
        total_reviews = 0
        rated = 0
        score_sum = 0
        poor = 0
        excellent = 0

        for pr in prs:
            number = int(pr["pr_number"])
            lines = int(pr["added_lines"] or 0) + int(pr["removed_lines"] or 0)
            total_lines += lines
            reviews = reviews_by_pr.get(number, [])
            evals = evals_by_pr.get(number, [])
            lgtms = lgtms_by_pr.get(number, [])
            evaluation = primary_evaluation(evals)
            lgtm = latest_lgtm(lgtms)
            score = score_value(evaluation["score"]) if evaluation else None
            nonstandard = nonstandard_reason(evaluation) if lgtm else ""
            nonstandard_reviewer = lgtm["author"] if lgtm and nonstandard else ""
            if score is not None:
                rated += 1
                score_sum += score
                poor += int(score < 3)
                excellent += int(score > 3)
            total_reviews += len(reviews)

            author = pr["author"]
            submitter = contributor_map.setdefault(author, empty_contributor(author))
            submitter["submit_prs"] += 1
            submitter["submit_lines"] += lines
            submitter["received_reviews"] += len(reviews)
            if score is not None:
                submitter["rated_prs"] += 1
                submitter["poor_prs"] += int(score < 3)
                submitter["excellent_prs"] += int(score > 3)

            for review in reviews:
                reviewer = contributor_map.setdefault(review["author"], empty_contributor(review["author"]))
                reviewer["review_comments"] += 1
                reviewer["review_prs_set"].add(number)

            if evaluation:
                scorer = contributor_map.setdefault(evaluation["author"], empty_contributor(evaluation["author"]))
                scorer["scored_prs"] += 1
                item_score = score_value(evaluation["score"])
                scorer["scored_poor"] += int(item_score is not None and item_score < 3)
                scorer["scored_excellent"] += int(item_score is not None and item_score > 3)

            if nonstandard_reviewer:
                owner = contributor_map.setdefault(
                    nonstandard_reviewer,
                    empty_contributor(nonstandard_reviewer),
                )
                owner["nonstandard_prs"] += 1

            pr_payload.append(
                {
                    "id": number,
                    "title": pr["title"],
                    "author": author,
                    "mergedAt": pr["merged_at"],
                    "lines": lines,
                    "reviews": len(reviews),
                    "score": score,
                    "reviewer": evaluation["author"] if evaluation else "",
                    "level": score_level(score),
                    "summary": evaluation["body"] if evaluation else "",
                    "nonstandardReviewer": nonstandard_reviewer,
                    "nonstandardReason": nonstandard,
                    "htmlUrl": pr["html_url"],
                    "detail": [
                        {
                            "type": "检视意见",
                            "author": row["author"],
                            "path": f"{row['file_path']}:{row['line']}" if row["line"] else row["file_path"],
                            "body": row["body"],
                            "createdAt": row["created_at"],
                        }
                        for row in reviews
                    ]
                    + [
                        {
                            "type": "MR评价",
                            "author": row["author"],
                            "path": "",
                            "body": row["body"],
                            "createdAt": row["created_at"],
                        }
                        for row in evals
                    ],
                }
            )

        contributors = []
        for item in contributor_map.values():
            item["review_prs"] = len(item.pop("review_prs_set"))
            contributors.append(item)
        contributors.sort(
            key=lambda item: (
                item["submit_prs"] + item["review_comments"] + item["scored_prs"],
                item["submit_lines"],
            ),
            reverse=True,
        )

        return {
            "repo": self.repo.full_name,
            "period": period,
            "range": label,
            "ranges": self.available_ranges(),
            "metrics": {
                "mergedPrs": len(prs),
                "lines": total_lines,
                "reviewComments": total_reviews,
                "ratedPrs": rated,
                "averageScore": round(score_sum / rated, 2) if rated else None,
                "poorPrs": poor,
                "excellentPrs": excellent,
            },
            "prs": pr_payload,
            "contributors": contributors,
            "lastSync": dict(sync) if sync else None,
        }

    def available_ranges(self) -> dict[str, list[str]]:
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT merged_at FROM pull_requests WHERE repo = ? ORDER BY merged_at DESC",
                (self.repo.full_name,),
            ).fetchall()
        dates = [parse_dt(row["merged_at"]) for row in rows]
        dates = [date for date in dates if date is not None]
        if not dates:
            current = now_tz()
            return {
                "week": [f"{current.isocalendar().year}年第{current.isocalendar().week:02d}周"],
                "month": [current.strftime("%Y-%m")],
                "quarter": [f"{current.year} Q{((current.month - 1) // 3) + 1}"],
                "half": [f"{current.year} H{1 if current.month <= 6 else 2}"],
                "year": [f"{current.year} 全年"],
            }
        weeks = {f"{date.isocalendar().year}年第{date.isocalendar().week:02d}周" for date in dates}
        months = {date.strftime("%Y-%m") for date in dates}
        quarters = {f"{date.year} Q{((date.month - 1) // 3) + 1}" for date in dates}
        halves = {f"{date.year} H{1 if date.month <= 6 else 2}" for date in dates}
        years = {f"{date.year} 全年" for date in dates}
        return {
            "week": sorted(weeks, reverse=True),
            "month": sorted(months, reverse=True),
            "quarter": sorted(quarters, reverse=True),
            "half": sorted(halves, reverse=True),
            "year": sorted(years, reverse=True),
        }

    def _group_rows(
        self,
        conn: sqlite3.Connection,
        table: str,
        pr_numbers: list[int],
    ) -> dict[int, list[sqlite3.Row]]:
        if not pr_numbers:
            return {}
        placeholders = ",".join("?" for _ in pr_numbers)
        rows = conn.execute(
            f"""
            SELECT * FROM {table}
            WHERE repo = ? AND pr_number IN ({placeholders})
            ORDER BY created_at ASC
            """,
            (self.repo.full_name, *pr_numbers),
        ).fetchall()
        grouped: dict[int, list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(int(row["pr_number"]), []).append(row)
        return grouped


def empty_contributor(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "submit_prs": 0,
        "submit_lines": 0,
        "received_reviews": 0,
        "rated_prs": 0,
        "poor_prs": 0,
        "excellent_prs": 0,
        "review_comments": 0,
        "review_prs_set": set(),
        "scored_prs": 0,
        "scored_poor": 0,
        "scored_excellent": 0,
        "nonstandard_prs": 0,
    }


def make_handler(static_dir: Path, queries: DashboardQueries) -> type[SimpleHTTPRequestHandler]:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(static_dir), **kwargs)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/dashboard":
                params = urllib.parse.parse_qs(parsed.query)
                period = params.get("period", ["month"])[0]
                range_label = params.get("range", [None])[0]
                try:
                    payload = queries.dashboard(period, range_label)
                    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as exc:
                    body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                    self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                return
            super().do_GET()

    return Handler


def seconds_until_midnight() -> float:
    current = now_tz()
    tomorrow = current.date() + timedelta(days=1)
    next_midnight = datetime.combine(tomorrow, datetime.min.time(), TZ)
    return max(1.0, (next_midnight - current).total_seconds())


def scheduler_loop(collector: Collector) -> None:
    while True:
        time.sleep(seconds_until_midnight())
        try:
            collector.sync_month()
        except Exception as exc:
            print(f"[scheduler] sync failed: {exc}", file=sys.stderr)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GitCode merged PR review board backend")
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--token-env", default="GITCODE_API_TOKEN")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="sync merged PRs for a month")
    sync.add_argument("--month", help="month in YYYY-MM, defaults to current month")
    sync.add_argument("--date", help="date in YYYY-MM-DD; sync only PRs merged that day")

    serve = sub.add_parser("serve", help="serve API and static dashboard")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8090)
    serve.add_argument("--static-dir", type=Path, default=DEFAULT_STATIC_DIR)
    serve.add_argument("--with-scheduler", action="store_true")

    sub.add_parser("scheduler", help="run a midnight sync loop")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    repo = RepoRef(args.owner, args.repo)
    store = ReviewStore(args.db)
    store.init_schema()

    token = os.environ.get(args.token_env)
    client = GitCodeClient(token) if token else None
    collector = Collector(client, store, repo) if client else None

    if args.command in {"sync", "scheduler"} and collector is None:
        print(f"error: missing ${args.token_env}", file=sys.stderr)
        return 2

    if args.command == "sync":
        if args.date and args.month:
            print("error: --date and --month are mutually exclusive", file=sys.stderr)
            return 2
        if args.date:
            count = collector.sync_day(args.date)  # type: ignore[union-attr]
            print(f"synced {count} merged PRs for {repo.full_name} on {args.date}")
        else:
            count = collector.sync_month(args.month)  # type: ignore[union-attr]
            print(f"synced {count} merged PRs for {repo.full_name}")
        return 0

    if args.command == "scheduler":
        print(f"scheduler started for {repo.full_name}; next sync at local midnight")
        scheduler_loop(collector)  # type: ignore[arg-type]
        return 0

    if args.command == "serve":
        if args.with_scheduler:
            if collector is None:
                print(f"error: missing ${args.token_env} for --with-scheduler", file=sys.stderr)
                return 2
            thread = threading.Thread(target=scheduler_loop, args=(collector,), daemon=True)
            thread.start()

        queries = DashboardQueries(store, repo)
        handler = make_handler(args.static_dir.resolve(), queries)
        server = ThreadingHTTPServer((args.host, args.port), handler)
        print(f"serving http://{args.host}:{args.port}/ with db {args.db}")
        server.serve_forever()
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
