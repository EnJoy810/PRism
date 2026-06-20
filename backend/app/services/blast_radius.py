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
    changed_node_ids: set[int] | None = None,
) -> list[dict]:
    if not db_path.exists():
        return []

    token_budget = diff_token_estimate // 2
    used_tokens = 0
    results = []

    try:
        from app.services.indexer import ensure_index_schema

        ensure_index_schema(db_path)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        changed_nodes = _resolve_changed_nodes(conn, changed_fn_names, changed_node_ids)
        for changed in changed_nodes:
            callers = _bfs_callers(conn, changed["id"], depth)
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
                    "changed_fn": (
                        f"{changed['file']}:{changed['name']}"
                        if changed["from_diff_line"] else changed["name"]
                    ),
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


def _resolve_changed_nodes(
    conn: sqlite3.Connection,
    changed_fn_names: set[str],
    changed_node_ids: set[int] | None = None,
) -> list[dict]:
    rows: list[dict] = []
    seen: set[int] = set()
    resolved_names: set[str] = set()

    if changed_node_ids:
        placeholders = ",".join("?" for _ in changed_node_ids)
        id_rows = conn.execute(
            f"""
            SELECT id, file, name
            FROM nodes
            WHERE id IN ({placeholders})
            ORDER BY file, start_line, name
            """,
            tuple(sorted(changed_node_ids)),
        ).fetchall()
        rows.extend({**dict(row), "from_diff_line": True} for row in id_rows)
        seen.update(row["id"] for row in id_rows)
        resolved_names.update(row["name"] for row in id_rows)

    for fn_name in sorted(changed_fn_names):
        if fn_name in resolved_names:
            continue
        name_rows = conn.execute(
            """
            SELECT id, file, name
            FROM nodes
            WHERE name = ?
            ORDER BY file, start_line, name
            """,
            (fn_name,),
        ).fetchall()
        for row in name_rows:
            if row["id"] in seen:
                continue
            rows.append({**dict(row), "from_diff_line": False})
            seen.add(row["id"])
    return rows


def _bfs_callers(
    conn: sqlite3.Connection,
    start_node_id: int,
    max_depth: int,
) -> list[dict]:
    visited: set[int] = set()
    queue: list[tuple[int, int]] = [(start_node_id, 0)]
    result: list[dict] = []
    visited.add(start_node_id)

    while queue:
        node_id, current_depth = queue.pop(0)
        if current_depth >= max_depth:
            continue

        node_name = conn.execute(
            "SELECT name FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if not node_name:
            continue

        callers = _caller_rows(conn, node_id, node_name["name"])

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


def _caller_rows(conn: sqlite3.Connection, callee_id: int, callee_name: str) -> list[sqlite3.Row]:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(edges)").fetchall()}
    if "callee_id" in columns:
        rows = conn.execute(
            """
            SELECT n.id, n.file, n.name, n.start_line, n.code
            FROM edges e
            JOIN nodes n ON n.id = e.caller_id
            WHERE e.callee_id = ?
            ORDER BY n.file, n.start_line, n.name
            """,
            (callee_id,),
        ).fetchall()
        if rows:
            return rows

    return conn.execute(
        """
        SELECT n.id, n.file, n.name, n.start_line, n.code
        FROM edges e
        JOIN nodes n ON n.id = e.caller_id
        WHERE e.callee_name = ?
        ORDER BY n.file, n.start_line, n.name
        """,
        (callee_name,),
    ).fetchall()
