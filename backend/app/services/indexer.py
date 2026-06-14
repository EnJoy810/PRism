"""Tree-sitter based call graph builder.

Scans a local repository and builds a SQLite call graph:
  nodes: function definitions (file, name, lines, code, hash)
  edges: caller -> callee_name (static call sites only)

Dynamic calls (getattr, reflection) are NOT tracked — accepted limitation.
"""

import hashlib
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_SKIP_DIRS = {
    "node_modules", "vendor", "dist", "build",
    ".git", "__pycache__", ".venv", "venv",
}
_SKIP_FILE_PATTERNS = {
    "test_", "_test.", ".test.", ".spec.",
}
_MAX_FILE_BYTES = 500 * 1024

_LANG_EXTENSIONS: dict[str, list[str]] = {
    "python": [".py"],
    "javascript": [".js", ".mjs"],
    "typescript": [".ts", ".tsx"],
}


def _get_parser(lang: str):
    try:
        from tree_sitter import Language, Parser
        if lang == "python":
            import tree_sitter_python as m
        elif lang == "javascript":
            import tree_sitter_javascript as m
        elif lang == "typescript":
            import tree_sitter_typescript as m
            return Parser(Language(m.language_typescript())), Language(m.language_typescript())
        else:
            return None
        language = Language(m.language())
        return Parser(language), language
    except Exception as e:
        logger.debug("parser init failed for %s: %s", lang, e)
        return None


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _should_skip_file(path: Path) -> bool:
    name = path.name
    if path.stat().st_size > _MAX_FILE_BYTES:
        return True
    return any(pat in name for pat in _SKIP_FILE_PATTERNS)


def _should_skip_dir(name: str) -> bool:
    return name in _SKIP_DIRS or name.startswith(".")


def _extract_python(source: bytes, tree) -> tuple[list[dict], list[dict]]:
    functions = []
    calls = []
    lines = source.decode("utf-8", errors="replace").splitlines()

    def visit(node, current_fn=None):
        if node.type in ("function_definition", "async_function_definition"):
            name_node = node.child_by_field_name("name")
            fn_name = name_node.text.decode() if name_node else "<anonymous>"
            start = node.start_point[0]
            end = node.end_point[0]
            code = "\n".join(lines[start:end + 1])
            functions.append({
                "name": fn_name,
                "start_line": start + 1,
                "end_line": end + 1,
                "code": code[:2000],
            })
            for child in node.children:
                visit(child, fn_name)
        elif node.type == "call" and current_fn:
            fn_node = node.child_by_field_name("function")
            if fn_node:
                callee = fn_node.text.decode()
                if "." in callee:
                    callee = callee.rsplit(".", 1)[-1]
                calls.append({"caller_name": current_fn, "callee_name": callee})
        else:
            for child in node.children:
                visit(child, current_fn)

    visit(tree.root_node)
    return functions, calls


def _extract_js_ts(source: bytes, tree) -> tuple[list[dict], list[dict]]:
    functions = []
    calls = []
    lines = source.decode("utf-8", errors="replace").splitlines()

    FN_TYPES = {
        "function_declaration",
        "function_expression",
        "arrow_function",
        "method_definition",
    }

    def visit(node, current_fn=None):
        if node.type in FN_TYPES:
            name_node = node.child_by_field_name("name")
            fn_name = name_node.text.decode() if name_node else "<anonymous>"
            start = node.start_point[0]
            end = node.end_point[0]
            code = "\n".join(lines[start:end + 1])
            functions.append({
                "name": fn_name,
                "start_line": start + 1,
                "end_line": end + 1,
                "code": code[:2000],
            })
            for child in node.children:
                visit(child, fn_name)
        elif node.type == "call_expression" and current_fn:
            fn_node = node.child_by_field_name("function")
            if fn_node:
                callee = fn_node.text.decode()
                if "." in callee:
                    callee = callee.rsplit(".", 1)[-1]
                calls.append({"caller_name": current_fn, "callee_name": callee})
            for child in node.children:
                visit(child, current_fn)
        else:
            for child in node.children:
                visit(child, current_fn)

    visit(tree.root_node)
    return functions, calls


def build_index(repo_path: Path, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS nodes (
            id         INTEGER PRIMARY KEY,
            file       TEXT NOT NULL,
            name       TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line   INTEGER NOT NULL,
            code       TEXT NOT NULL,
            file_hash  TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_file_name ON nodes(file, name);
        CREATE TABLE IF NOT EXISTS edges (
            caller_id   INTEGER NOT NULL,
            callee_name TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_edges_callee ON edges(callee_name);
        CREATE TABLE IF NOT EXISTS file_hashes (
            file TEXT PRIMARY KEY,
            hash TEXT NOT NULL
        );
    """)
    conn.commit()

    parsers = {}
    for lang in ("python", "javascript", "typescript"):
        result = _get_parser(lang)
        if result:
            parsers[lang] = result

    if not parsers:
        logger.warning("no tree-sitter parsers available, skipping index")
        conn.close()
        return

    ext_to_lang = {}
    for lang, exts in _LANG_EXTENSIONS.items():
        if lang in parsers:
            for ext in exts:
                ext_to_lang[ext] = lang

    for path in _iter_files(repo_path, ext_to_lang):
        rel = str(path.relative_to(repo_path))
        try:
            _index_file(conn, path, rel, ext_to_lang, parsers)
        except Exception as e:
            logger.debug("skip %s: %s", rel, e)

    conn.close()
    logger.info("index built: %s", db_path)


def _iter_files(repo_path: Path, ext_to_lang: dict):
    for p in repo_path.rglob("*"):
        if not p.is_file():
            continue
        if any(_should_skip_dir(part) for part in p.relative_to(repo_path).parts[:-1]):
            continue
        if p.suffix not in ext_to_lang:
            continue
        if _should_skip_file(p):
            continue
        yield p


def _index_file(
    conn: sqlite3.Connection,
    path: Path,
    rel: str,
    ext_to_lang: dict,
    parsers: dict,
) -> None:
    fhash = _file_hash(path)
    row = conn.execute(
        "SELECT hash FROM file_hashes WHERE file = ?", (rel,)
    ).fetchone()
    if row and row[0] == fhash:
        return

    old_ids = [r[0] for r in conn.execute(
        "SELECT id FROM nodes WHERE file = ?", (rel,)
    ).fetchall()]
    if old_ids:
        conn.execute(
            f"DELETE FROM edges WHERE caller_id IN ({','.join('?' * len(old_ids))})",
            old_ids,
        )
        conn.execute("DELETE FROM nodes WHERE file = ?", (rel,))

    lang = ext_to_lang[path.suffix]
    parser, _ = parsers[lang]
    source = path.read_bytes()

    try:
        tree = parser.parse(source)
    except Exception as e:
        raise RuntimeError(f"parse error: {e}") from e

    if lang == "python":
        functions, calls = _extract_python(source, tree)
    else:
        functions, calls = _extract_js_ts(source, tree)

    fn_name_to_id: dict[str, int] = {}
    for fn in functions:
        conn.execute(
            """INSERT OR REPLACE INTO nodes (file, name, start_line, end_line, code, file_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (rel, fn["name"], fn["start_line"], fn["end_line"], fn["code"], fhash),
        )
        node_id = conn.execute(
            "SELECT id FROM nodes WHERE file = ? AND name = ?", (rel, fn["name"])
        ).fetchone()[0]
        fn_name_to_id[fn["name"]] = node_id

    for call in calls:
        caller_id = fn_name_to_id.get(call["caller_name"])
        if caller_id:
            conn.execute(
                "INSERT INTO edges (caller_id, callee_name) VALUES (?, ?)",
                (caller_id, call["callee_name"]),
            )

    conn.execute(
        "INSERT OR REPLACE INTO file_hashes (file, hash) VALUES (?, ?)",
        (rel, fhash),
    )
    conn.commit()
