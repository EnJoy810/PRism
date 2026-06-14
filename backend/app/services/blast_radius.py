"""BFS blast radius computation from call graph.

Given a set of changed function names, finds all callers up to depth=2.
Respects a token budget: total context <= 50% of diff token count.
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DEPTH = 2


def compute_blast_radius(
    db_path: Path,
    changed_fn_names: set[str],
    diff_token_estimate: int,
    depth: int = DEFAULT_DEPTH,
) -> list[dict]:
    if not db_path.exists():
        return []

    token_budget = diff_token_estimate // 2
    used_tokens = 0
    results = []

    try:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        for fn_name in changed_fn_names:
            callers = _bfs_callers(conn, fn_name, depth)
            if not callers:
                continue

            caller_list = []
            for caller in callers:
                snippet_tokens = len(caller["code"]) // 4
                if used_tokens + snippet_tokens > token_budget:
                    break
                caller_list.append(caller)
                used_tokens += snippet_tokens

            if caller_list:
                results.append({
                    "changed_fn": fn_name,
                    "callers": caller_list,
                })

            if used_tokens >= token_budget:
                logger.info("blast radius token budget exhausted at %d tokens", used_tokens)
                break

        conn.close()
    except Exception as e:
        logger.warning("blast radius failed: %s", e)
        return []

    return results


def _bfs_callers(
    conn: sqlite3.Connection,
    start_fn_name: str,
    max_depth: int,
) -> list[dict]:
    visited: set[int] = set()
    queue: list[tuple[int, int]] = []
    result: list[dict] = []

    start_nodes = conn.execute(
        "SELECT id FROM nodes WHERE name = ?", (start_fn_name,)
    ).fetchall()

    for row in start_nodes:
        queue.append((row["id"], 0))
        visited.add(row["id"])

    while queue:
        node_id, current_depth = queue.pop(0)
        if current_depth >= max_depth:
            continue

        node_name = conn.execute(
            "SELECT name FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if not node_name:
            continue

        callers = conn.execute(
            """
            SELECT n.id, n.file, n.name, n.start_line, n.code
            FROM edges e
            JOIN nodes n ON n.id = e.caller_id
            WHERE e.callee_name = ?
            """,
            (node_name["name"],),
        ).fetchall()

        for caller in callers:
            if caller["id"] in visited:
                continue
            visited.add(caller["id"])
            result.append({
                "file": caller["file"],
                "fn": caller["name"],
                "start_line": caller["start_line"],
                "code": caller["code"],
            })
            queue.append((caller["id"], current_depth + 1))

    return result
