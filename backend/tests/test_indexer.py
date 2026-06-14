import sqlite3

import pytest

from app.services.indexer import build_index


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
