import hashlib
import sqlite3

import pytest

from app.services.indexer import build_index, ensure_index_schema


@pytest.fixture
def python_repo(tmp_path):
    src = tmp_path / "src.py"
    src.write_text("""
def foo():
    return bar()

def bar():
    return 42
""")
    return tmp_path


def test_build_index_creates_nodes(python_repo, tmp_path):
    db = tmp_path / "test.db"
    build_index(python_repo, db)
    conn = sqlite3.connect(str(db))
    names = {r[0] for r in conn.execute("SELECT name FROM nodes").fetchall()}
    assert "foo" in names
    assert "bar" in names
    conn.close()


def test_build_index_creates_edges(python_repo, tmp_path):
    db = tmp_path / "test.db"
    build_index(python_repo, db)
    conn = sqlite3.connect(str(db))
    edges = conn.execute(
        "SELECT callee_name FROM edges WHERE caller_id = "
        "(SELECT id FROM nodes WHERE name = 'foo')"
    ).fetchall()
    assert any(e[0] == "bar" for e in edges)
    conn.close()


def test_build_index_edges_resolve_callee_id(python_repo, tmp_path):
    db = tmp_path / "test.db"
    build_index(python_repo, db)
    conn = sqlite3.connect(str(db))
    edge = conn.execute(
        """
        SELECT e.callee_id
        FROM edges e
        JOIN nodes caller ON caller.id = e.caller_id
        WHERE caller.name = 'foo' AND e.callee_name = 'bar'
        """
    ).fetchone()
    bar_id = conn.execute("SELECT id FROM nodes WHERE name = 'bar'").fetchone()[0]
    conn.close()

    assert edge[0] == bar_id


def test_build_index_migrates_old_edges_schema(python_repo, tmp_path):
    db = tmp_path / "test.db"
    src = python_repo / "src.py"
    old_hash = hashlib.sha256(src.read_bytes()).hexdigest()[:16]

    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE nodes (
            id         INTEGER PRIMARY KEY,
            file       TEXT NOT NULL,
            name       TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line   INTEGER NOT NULL,
            code       TEXT NOT NULL,
            file_hash  TEXT NOT NULL
        );
        CREATE UNIQUE INDEX idx_nodes_file_name ON nodes(file, name);
        CREATE TABLE edges (
            caller_id   INTEGER NOT NULL,
            callee_name TEXT NOT NULL
        );
        CREATE INDEX idx_edges_callee ON edges(callee_name);
        CREATE TABLE file_hashes (
            file TEXT PRIMARY KEY,
            hash TEXT NOT NULL
        );
    """)
    conn.execute(
        "INSERT INTO nodes (file, name, start_line, end_line, code, file_hash) VALUES (?, ?, ?, ?, ?, ?)",
        ("src.py", "foo", 2, 3, "def foo():\n    return bar()", old_hash),
    )
    conn.execute(
        "INSERT INTO nodes (file, name, start_line, end_line, code, file_hash) VALUES (?, ?, ?, ?, ?, ?)",
        ("src.py", "bar", 5, 6, "def bar():\n    return 42", old_hash),
    )
    conn.execute(
        "INSERT INTO edges (caller_id, callee_name) VALUES ((SELECT id FROM nodes WHERE name = 'foo'), 'bar')"
    )
    conn.execute("INSERT INTO file_hashes (file, hash) VALUES (?, ?)", ("src.py", old_hash))
    conn.commit()
    conn.close()

    build_index(python_repo, db)

    conn = sqlite3.connect(str(db))
    columns = {row[1] for row in conn.execute("PRAGMA table_info(edges)").fetchall()}
    edge = conn.execute(
        """
        SELECT e.callee_id
        FROM edges e
        JOIN nodes caller ON caller.id = e.caller_id
        WHERE caller.name = 'foo' AND e.callee_name = 'bar'
        """
    ).fetchone()
    bar_id = conn.execute("SELECT id FROM nodes WHERE name = 'bar'").fetchone()[0]
    conn.close()

    assert "callee_id" in columns
    assert edge[0] == bar_id


def test_ensure_index_schema_migrates_old_edges_schema(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE edges (
            caller_id   INTEGER NOT NULL,
            callee_name TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()

    ensure_index_schema(db)

    conn = sqlite3.connect(str(db))
    columns = {row[1] for row in conn.execute("PRAGMA table_info(edges)").fetchall()}
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(edges)").fetchall()}
    conn.close()

    assert "callee_id" in columns
    assert "idx_edges_callee_id" in indexes


def test_incremental_index_skips_unchanged(python_repo, tmp_path):
    db = tmp_path / "test.db"
    build_index(python_repo, db)

    conn = sqlite3.connect(str(db))
    count_before = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    conn.close()

    build_index(python_repo, db)

    conn = sqlite3.connect(str(db))
    count_after = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    conn.close()

    assert count_before == count_after


def test_skip_node_modules(tmp_path):
    nm = tmp_path / "node_modules" / "lib"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("function foo() { bar(); }")
    db = tmp_path / "test.db"
    build_index(tmp_path, db)
    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    conn.close()
    assert count == 0
