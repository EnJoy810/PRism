"""BFS blast radius computation from call graph.

Given a set of changed function names, finds all callers up to depth=2.
Respects a token budget: total context <= 50% of diff token count.

Supports two backends:
- "builtin": tree-sitter + SQLite BFS (default)
- "codegraph": subprocess call to `codegraph callers --json`
"""

import json
import logging
import shutil
import sqlite3
import subprocess
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
        conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30)
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
                    # Always use "file:name" format so _run_impact_verification can key by file.
                    # from_diff_line=False means the node was found via name-match fallback (lower
                    # confidence), but the file is still reliably available from the nodes table.
                    "changed_fn": f"{changed['file']}:{changed['name']}",
                    "from_diff_line": changed["from_diff_line"],
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


def compute_blast_radius_codegraph(
    repo_path: Path,
    changed_fn_names: set[str],
    diff_token_estimate: int,
) -> list[dict]:
    """CodeGraph backend: subprocess `codegraph callers --json`.

    Falls back to empty list if codegraph CLI is not installed or init fails.
    """
    if not shutil.which("codegraph"):
        logger.warning("codegraph CLI not found, skipping codegraph backend")
        return []

    if not changed_fn_names:
        return []

    # initialise index if not already done
    codegraph_dir = repo_path / ".codegraph"
    if not codegraph_dir.exists():
        try:
            subprocess.run(
                ["codegraph", "init", str(repo_path)],
                capture_output=True, text=True, timeout=120, check=True,
            )
            logger.info("codegraph init complete: %s", repo_path)
        except subprocess.CalledProcessError as e:
            logger.warning("codegraph init failed: %s", e.stderr[:500])
            return []
        except subprocess.TimeoutExpired:
            logger.warning("codegraph init timed out")
            return []

    token_budget = diff_token_estimate // 2
    used_tokens = 0
    results = []

    for fn_name in sorted(changed_fn_names):
        if used_tokens >= token_budget:
            break
        try:
            proc = subprocess.run(
                ["codegraph", "callers", fn_name, "--json", "--limit", "50",
                 "--path", str(repo_path)],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                continue
            data = json.loads(proc.stdout)
            callers_raw = data.get("callers", [])
            if not callers_raw:
                continue

            caller_list = []
            for c in callers_raw:
                file_path = c.get("filePath", "")
                # read code snippet from file
                code = _read_snippet(Path(file_path), c.get("startLine", 1))
                snippet_tokens = len(code) // 4
                if used_tokens + snippet_tokens > token_budget:
                    break
                caller_list.append({
                    "file": file_path,
                    "fn": c.get("name", ""),
                    "start_line": c.get("startLine", 0),
                    "code": code,
                })
                used_tokens += snippet_tokens

            if caller_list:
                results.append({
                    "changed_fn": fn_name,
                    "callers": caller_list,
                })
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
            logger.warning("codegraph callers failed for %s: %s", fn_name, e)
            continue

    logger.info(
        "codegraph blast radius: %d changed fns, %d caller groups found",
        len(changed_fn_names), len(results),
    )
    return results


def _read_snippet(file_path: Path, start_line: int, context_lines: int = 20) -> str:
    """Read up to context_lines lines starting from start_line."""
    try:
        lines = file_path.read_text(errors="replace").splitlines()
        start = max(0, start_line - 1)
        end = min(len(lines), start + context_lines)
        return "\n".join(lines[start:end])
    except OSError:
        return ""


def _caller_rows(conn: sqlite3.Connection, callee_id: int, callee_name: str) -> list[sqlite3.Row]:
    """Return only import-verified callers (edges where callee_id was resolved via import graph).

    Intentionally omits callee_name / callee_short_name fallbacks.  Those do a
    global function-name search with no import verification, producing false
    positives that degrade LLM precision ("garbage in, garbage out").  If
    callee_id is NULL (import resolution didn't succeed), we return nothing —
    better to provide no context than unverified context.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(edges)").fetchall()}
    if "callee_id" not in columns:
        return []

    verified = conn.execute(
        """
        SELECT n.id, n.file, n.name, n.start_line, n.code
        FROM edges e
        JOIN nodes n ON n.id = e.caller_id
        WHERE e.callee_id = ?
        ORDER BY n.file, n.start_line, n.name
        """,
        (callee_id,),
    ).fetchall()

    if not verified:
        # Log how many unverified candidates exist so we know when import resolution
        # is failing and how much signal we're leaving on the table.
        unverified_count = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE callee_name = ? AND callee_id IS NULL",
            (callee_name,),
        ).fetchone()[0]
        if unverified_count:
            logger.debug(
                "caller_rows[%s]: 0 verified, %d unverified dropped (no import resolution)",
                callee_name, unverified_count,
            )

    return verified
