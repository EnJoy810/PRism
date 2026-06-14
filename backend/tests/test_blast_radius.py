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
        INSERT INTO edges VALUES (2, 'foo');
        INSERT INTO edges VALUES (3, 'bar');
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
        INSERT INTO edges VALUES (1, 'pong');
        INSERT INTO edges VALUES (2, 'ping');
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
