import sqlite3

import pytest

from app.services.blast_radius import compute_blast_radius


@pytest.fixture
def sample_db(tmp_path):
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            file TEXT, name TEXT,
            start_line INTEGER, end_line INTEGER,
            code TEXT, file_hash TEXT
        );
        CREATE TABLE edges (caller_id INTEGER, callee_name TEXT);
        INSERT INTO nodes VALUES (1, 'a.py', 'foo', 1, 5, 'def foo(): pass', 'h1');
        INSERT INTO nodes VALUES (2, 'b.py', 'bar', 1, 5, 'def bar(): foo()', 'h2');
        INSERT INTO nodes VALUES (3, 'c.py', 'baz', 1, 5, 'def baz(): bar()', 'h3');
        INSERT INTO edges (caller_id, callee_name) VALUES (2, 'foo');
        INSERT INTO edges (caller_id, callee_name) VALUES (3, 'bar');
    """)
    conn.commit()
    conn.close()
    return db


def test_finds_direct_caller(sample_db):
    result = compute_blast_radius(sample_db, {"foo"}, diff_token_estimate=10000)
    assert len(result) == 1
    assert result[0]["changed_fn"] == "foo"
    caller_fns = {c["fn"] for c in result[0]["callers"]}
    assert "bar" in caller_fns


def test_finds_two_hop_caller(sample_db):
    result = compute_blast_radius(sample_db, {"foo"}, diff_token_estimate=10000, depth=2)
    caller_fns = {c["fn"] for c in result[0]["callers"]}
    assert "bar" in caller_fns
    assert "baz" in caller_fns


def test_no_infinite_loop_on_cycle(tmp_path):
    db = tmp_path / "cycle.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE nodes (id INTEGER PRIMARY KEY, file TEXT, name TEXT,
            start_line INTEGER, end_line INTEGER, code TEXT, file_hash TEXT);
        CREATE TABLE edges (caller_id INTEGER, callee_name TEXT);
        INSERT INTO nodes VALUES (1, 'a.py', 'ping', 1, 3, 'def ping(): pong()', 'h1');
        INSERT INTO nodes VALUES (2, 'a.py', 'pong', 5, 7, 'def pong(): ping()', 'h2');
        INSERT INTO edges (caller_id, callee_name) VALUES (1, 'pong');
        INSERT INTO edges (caller_id, callee_name) VALUES (2, 'ping');
    """)
    conn.commit()
    conn.close()
    result = compute_blast_radius(db, {"ping"}, diff_token_estimate=10000)
    assert isinstance(result, list)


def test_token_budget_limits_output(sample_db):
    result = compute_blast_radius(sample_db, {"foo"}, diff_token_estimate=4)
    assert isinstance(result, list)


def test_missing_db_returns_empty(tmp_path):
    result = compute_blast_radius(tmp_path / "nonexistent.db", {"foo"}, 1000)
    assert result == []


def test_blast_radius_starts_from_node_id_not_global_name(tmp_path):
    db = tmp_path / "same_name.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE nodes (id INTEGER PRIMARY KEY, file TEXT, name TEXT,
            start_line INTEGER, end_line INTEGER, code TEXT, file_hash TEXT);
        CREATE TABLE edges (caller_id INTEGER, callee_name TEXT, callee_id INTEGER);
        INSERT INTO nodes VALUES (1, 'a.py', 'target', 1, 3, 'def target(): pass', 'h1');
        INSERT INTO nodes VALUES (2, 'b.py', 'target', 1, 3, 'def target(): pass', 'h2');
        INSERT INTO nodes VALUES (3, 'caller_a.py', 'caller_a', 1, 3, 'def caller_a(): target()', 'h3');
        INSERT INTO nodes VALUES (4, 'caller_b.py', 'caller_b', 1, 3, 'def caller_b(): target()', 'h4');
        INSERT INTO edges (caller_id, callee_name, callee_id) VALUES (3, 'target', 1);
        INSERT INTO edges (caller_id, callee_name, callee_id) VALUES (4, 'target', 2);
    """)
    conn.commit()
    conn.close()

    result = compute_blast_radius(db, {"target"}, 10000, changed_node_ids={1})

    assert len(result) == 1
    assert result[0]["changed_fn"] == "a.py:target"
    assert {caller["fn"] for caller in result[0]["callers"]} == {"caller_a"}


def test_blast_radius_old_schema_with_node_id_does_not_fail(tmp_path):
    db = tmp_path / "old_schema_same_name.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE nodes (id INTEGER PRIMARY KEY, file TEXT, name TEXT,
            start_line INTEGER, end_line INTEGER, code TEXT, file_hash TEXT);
        CREATE TABLE edges (caller_id INTEGER, callee_name TEXT);
        INSERT INTO nodes VALUES (1, 'a.py', 'target', 1, 3, 'def target(): pass', 'h1');
        INSERT INTO nodes VALUES (2, 'b.py', 'target', 1, 3, 'def target(): pass', 'h2');
        INSERT INTO nodes VALUES (3, 'caller_a.py', 'caller_a', 1, 3, 'def caller_a(): target()', 'h3');
        INSERT INTO nodes VALUES (4, 'caller_b.py', 'caller_b', 1, 3, 'def caller_b(): target()', 'h4');
        INSERT INTO edges (caller_id, callee_name) VALUES (3, 'target');
        INSERT INTO edges (caller_id, callee_name) VALUES (4, 'target');
    """)
    conn.commit()
    conn.close()

    result = compute_blast_radius(db, {"target"}, 10000, changed_node_ids={1})

    assert len(result) == 1
    assert result[0]["changed_fn"] == "a.py:target"
    assert {caller["fn"] for caller in result[0]["callers"]} == {"caller_a", "caller_b"}


def test_bfs_output_is_deterministically_ordered(tmp_path):
    db = tmp_path / "order.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE nodes (id INTEGER PRIMARY KEY, file TEXT, name TEXT,
            start_line INTEGER, end_line INTEGER, code TEXT, file_hash TEXT);
        CREATE TABLE edges (caller_id INTEGER, callee_name TEXT);
        INSERT INTO nodes VALUES (1, 'z.py', 'target', 1, 3, 'def target(): pass', 'h1');
        INSERT INTO nodes VALUES (2, 'z.py', 'z_call', 10, 12, 'def z_call(): target()', 'h2');
        INSERT INTO nodes VALUES (3, 'a.py', 'a_call', 1, 3, 'def a_call(): target()', 'h3');
        INSERT INTO edges (caller_id, callee_name) VALUES (2, 'target');
        INSERT INTO edges (caller_id, callee_name) VALUES (3, 'target');
    """)
    conn.commit()
    conn.close()

    result = compute_blast_radius(db, {"target"}, 10000, changed_node_ids={1})

    assert [caller["file"] for caller in result[0]["callers"]] == ["a.py", "z.py"]


def test_blast_radius_merges_node_ids_and_function_name_fallback(tmp_path):
    db = tmp_path / "mixed.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE nodes (id INTEGER PRIMARY KEY, file TEXT, name TEXT,
            start_line INTEGER, end_line INTEGER, code TEXT, file_hash TEXT);
        CREATE TABLE edges (caller_id INTEGER, callee_name TEXT);
        INSERT INTO nodes VALUES (1, 'a.py', 'target', 1, 3, 'def target(): pass', 'h1');
        INSERT INTO nodes VALUES (2, 'b.py', 'new_fn', 1, 3, 'def new_fn(): pass', 'h2');
        INSERT INTO nodes VALUES (3, 'caller_a.py', 'caller_a', 1, 3, 'def caller_a(): target()', 'h3');
        INSERT INTO nodes VALUES (4, 'caller_b.py', 'caller_b', 1, 3, 'def caller_b(): new_fn()', 'h4');
        INSERT INTO edges (caller_id, callee_name) VALUES (3, 'target');
        INSERT INTO edges (caller_id, callee_name) VALUES (4, 'new_fn');
    """)
    conn.commit()
    conn.close()

    result = compute_blast_radius(db, {"new_fn"}, 10000, changed_node_ids={1})

    assert [item["changed_fn"] for item in result] == ["a.py:target", "new_fn"]
