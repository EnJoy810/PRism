"""BFS blast radius computation from call graph.

Given a set of changed function names, finds all callers up to depth=2.
Respects a token budget: total context <= 50% of diff token count.

Supports two backends:
- "builtin": tree-sitter + SQLite BFS (default)
- "codegraph": subprocess call to `codegraph callers --json`
"""

import json
import logging
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DEPTH = 2

# AST patterns that indicate a function parameter is used in a "sensitive sink":
# dict key, array index, attribute access, or direct pass to another call.
# These are the patterns where an unexpected None / wrong type causes a runtime error.
_UNSAFE_SINK_PATTERNS = [
    # dict key: d[key], cache[key], counters[value]
    re.compile(r'\b(\w+)\s*\['),
    # attribute access on a parameter: obj.attr, result.value
    re.compile(r'\b(\w+)\s*\.'),
    # getattr call: getattr(obj, key)
    re.compile(r'\bgetattr\s*\('),
    # setattr call
    re.compile(r'\bsetattr\s*\('),
    # format / join using param: f"{key}", "".join(items)
    re.compile(r'f["\'].*\{(\w+)\}'),
]


def detect_unsafe_param_sinks(fn_diff_chunk: str) -> bool:
    """Return True if the changed function body contains a 'sensitive sink':
    a pattern where a parameter is used as a dict key, array index, or
    attribute access without a prior None/type guard.

    This is Layer 1 of the caller-aware analysis: a cheap deterministic AST
    filter that decides whether a caller scan is worth doing. Only functions
    that pass this gate should trigger an LLM caller-parameter check.

    Uses regex over the diff chunk (+ lines only) rather than full tree-sitter
    parsing, because we only need a heuristic signal, not perfect precision.
    If the function body is short enough to be ambiguous, we err on the side
    of triggering the scan (false positives here are cheap; false negatives are not).
    """
    added_lines = [
        line[1:]  # strip the leading '+'
        for line in fn_diff_chunk.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    if not added_lines:
        return False

    fn_body = "\n".join(added_lines)

    # Check for explicit None guard or type check — if the function already
    # validates its input, the risk is lower and we skip the caller scan.
    has_guard = bool(re.search(
        r'\bif\s+\w+\s+is\s+(not\s+)?None\b'
        r'|\bisinstance\s*\('
        r'|\bif\s+not\s+\w+\b'
        r'|\bAssert\b|\bassert\b',
        fn_body,
    ))
    if has_guard:
        return False

    return any(pat.search(fn_body) for pat in _UNSAFE_SINK_PATTERNS)


def find_new_callers_in_diff(diff: str) -> list[dict]:
    """从 diff 里直接找新函数的调用点。

    当 PR 同时新增了一个函数和调用它的代码时，graph BFS 依赖 import
    解析，解析失败时 caller_groups=0。本函数直接扫 diff 的 + 行，
    不依赖图索引，作为 BFS 的补充。

    返回格式与 compute_blast_radius 一致：
    [{"changed_fn": "file:name", "from_diff": True, "callers": [...]}]
    """
    # Step 1: extract new/changed function names from + lines
    fn_patterns = [
        re.compile(r"^\+\s*(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE),
        re.compile(
            r"^\+\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
            re.MULTILINE,
        ),
        re.compile(
            r"^\+\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?\(",
            re.MULTILINE,
        ),
    ]
    _SKIP_NAMES = {
        "if", "for", "while", "switch", "catch", "return", "throw",
        "new", "delete", "typeof", "void", "await", "yield",
    }
    new_fns: set[str] = set()
    for pat in fn_patterns:
        new_fns.update(m.group(1) for m in pat.finditer(diff))
    new_fns -= _SKIP_NAMES
    new_fns = {n for n in new_fns if len(n) > 1}
    if not new_fns:
        return []

    # Step 2: build per-file added-line index {file: [(line_num, content)]}
    added_lines: dict[str, list[tuple[int, str]]] = {}
    fn_definition_file: dict[str, str] = {}  # fn_name -> file where it's defined
    current_file: str | None = None
    current_line = 0

    for raw in diff.split("\n"):
        if raw.startswith("+++ b/"):
            current_file = raw[6:]
            current_line = 0
            added_lines.setdefault(current_file, [])
        elif raw.startswith("@@") and current_file is not None:
            m = re.search(r"\+(\d+)", raw)
            if m:
                current_line = int(m.group(1)) - 1
        elif current_file is not None:
            if raw.startswith("+") and not raw.startswith("+++"):
                current_line += 1
                content = raw[1:]
                added_lines[current_file].append((current_line, content))
                # Track where each new function is defined
                for fn_name in new_fns:
                    if fn_name not in fn_definition_file:
                        if re.search(
                            r'(?:async\s+)?def\s+' + re.escape(fn_name) + r'\s*\('
                            r'|(?:async\s+)?function\s+' + re.escape(fn_name) + r'\s*\('
                            r'|(?:const|let)\s+' + re.escape(fn_name) + r'\s*=\s*(?:async\s+)?\(',
                            content,
                        ):
                            fn_definition_file[fn_name] = current_file
            elif raw.startswith(" "):
                current_line += 1

    # Step 3: for each new function, scan added lines of OTHER files for call sites
    results: list[dict] = []
    for fn_name in sorted(new_fns):
        def_file = fn_definition_file.get(fn_name, "")
        call_pat = re.compile(r'\b' + re.escape(fn_name) + r'\s*\(')
        def_pat = re.compile(
            r'(?:async\s+)?def\s+' + re.escape(fn_name) + r'\s*\('
            r'|(?:async\s+)?function\s+' + re.escape(fn_name) + r'\s*\('
            r'|(?:const|let)\s+' + re.escape(fn_name) + r'\s*=\s*(?:async\s+)?\('
        )

        call_sites: list[dict] = []
        for file, entries in added_lines.items():
            for line_num, content in entries:
                if not call_pat.search(content):
                    continue
                if def_pat.search(content):
                    continue  # skip the definition line itself
                call_sites.append({
                    "file": file,
                    "fn": f"<call at line {line_num}>",
                    "start_line": line_num,
                    "code": content.rstrip(),
                })

        if call_sites:
            changed_fn_key = f"{def_file}:{fn_name}" if def_file else fn_name
            results.append({
                "changed_fn": changed_fn_key,
                "from_diff": True,
                "callers": call_sites,
            })
            logger.debug(
                "find_new_callers_in_diff: %s → %d call sites",
                changed_fn_key, len(call_sites),
            )

    return results


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
