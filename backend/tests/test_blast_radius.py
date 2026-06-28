import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from app.services.blast_radius import compute_blast_radius, compute_blast_radius_codegraph


@pytest.fixture
def sample_db(tmp_path):
    """Fixture with import-verified edges (callee_id set).

    foo(1) ← bar(2) ← baz(3)
    callee_id is set to the actual callee node id, simulating what
    _resolve_callee_ids() does after import-aware indexing.
    """
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY,
            file TEXT, name TEXT,
            start_line INTEGER, end_line INTEGER,
            code TEXT, file_hash TEXT
        );
        CREATE TABLE edges (caller_id INTEGER, callee_name TEXT, callee_id INTEGER);
        INSERT INTO nodes VALUES (1, 'a.py', 'foo', 1, 5, 'def foo(): pass', 'h1');
        INSERT INTO nodes VALUES (2, 'b.py', 'bar', 1, 5, 'def bar(): foo()', 'h2');
        INSERT INTO nodes VALUES (3, 'c.py', 'baz', 1, 5, 'def baz(): bar()', 'h3');
        INSERT INTO edges VALUES (2, 'foo', 1);
        INSERT INTO edges VALUES (3, 'bar', 2);
    """)
    conn.commit()
    conn.close()
    return db


def test_finds_direct_caller(sample_db):
    result = compute_blast_radius(sample_db, {"foo"}, diff_token_estimate=10000)
    assert len(result) == 1
    # changed_fn is now always "file:name" regardless of how the node was resolved
    assert result[0]["changed_fn"] == "a.py:foo"
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
        CREATE TABLE edges (caller_id INTEGER, callee_name TEXT, callee_id INTEGER);
        INSERT INTO nodes VALUES (1, 'a.py', 'ping', 1, 3, 'def ping(): pong()', 'h1');
        INSERT INTO nodes VALUES (2, 'a.py', 'pong', 5, 7, 'def pong(): ping()', 'h2');
        INSERT INTO edges VALUES (1, 'pong', 2);
        INSERT INTO edges VALUES (2, 'ping', 1);
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


def test_blast_radius_old_schema_without_callee_id_returns_empty(tmp_path):
    """Old DBs whose edges have no callee_id column return no callers.

    This is intentional: edges without callee_id were not import-verified.
    Passing unverified callers to the LLM degrades precision ("garbage in").
    The DB will be rebuilt with callee_id populated on the next full index.
    """
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

    # No callee_id column → no import-verified callers → empty result
    assert result == []


def test_bfs_output_is_deterministically_ordered(tmp_path):
    db = tmp_path / "order.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE nodes (id INTEGER PRIMARY KEY, file TEXT, name TEXT,
            start_line INTEGER, end_line INTEGER, code TEXT, file_hash TEXT);
        CREATE TABLE edges (caller_id INTEGER, callee_name TEXT, callee_id INTEGER);
        INSERT INTO nodes VALUES (1, 'z.py', 'target', 1, 3, 'def target(): pass', 'h1');
        INSERT INTO nodes VALUES (2, 'z.py', 'z_call', 10, 12, 'def z_call(): target()', 'h2');
        INSERT INTO nodes VALUES (3, 'a.py', 'a_call', 1, 3, 'def a_call(): target()', 'h3');
        INSERT INTO edges VALUES (2, 'target', 1);
        INSERT INTO edges VALUES (3, 'target', 1);
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
        CREATE TABLE edges (caller_id INTEGER, callee_name TEXT, callee_id INTEGER);
        INSERT INTO nodes VALUES (1, 'a.py', 'target', 1, 3, 'def target(): pass', 'h1');
        INSERT INTO nodes VALUES (2, 'b.py', 'new_fn', 1, 3, 'def new_fn(): pass', 'h2');
        INSERT INTO nodes VALUES (3, 'caller_a.py', 'caller_a', 1, 3, 'def caller_a(): target()', 'h3');
        INSERT INTO nodes VALUES (4, 'caller_b.py', 'caller_b', 1, 3, 'def caller_b(): new_fn()', 'h4');
        INSERT INTO edges VALUES (3, 'target', 1);
        INSERT INTO edges VALUES (4, 'new_fn', 2);
    """)
    conn.commit()
    conn.close()

    result = compute_blast_radius(db, {"new_fn"}, 10000, changed_node_ids={1})

    # both node-id-resolved and name-match-fallback nodes now always emit "file:name"
    assert [item["changed_fn"] for item in result] == ["a.py:target", "b.py:new_fn"]


# ---------------------------------------------------------------------------
# CodeGraph backend tests
# ---------------------------------------------------------------------------

def _codegraph_callers_output(callers: list) -> str:
    return json.dumps({"symbol": "target", "callers": callers})


@patch("app.services.blast_radius.shutil.which", return_value="/usr/local/bin/codegraph")
@patch("app.services.blast_radius.subprocess.run")
def test_codegraph_backend_returns_caller_list(mock_run, _mock_which, tmp_path):
    """Happy path: codegraph CLI returns a caller, snippet is read and returned."""
    # create a dummy source file so _read_snippet can read it
    src_file = tmp_path / "caller.py"
    src_file.write_text("def caller_fn():\n    target()\n")

    # stub codegraph init (no .codegraph dir) and callers
    init_result = MagicMock(returncode=0)
    callers_result = MagicMock(
        returncode=0,
        stdout=_codegraph_callers_output([
            {"name": "caller_fn", "filePath": str(src_file), "startLine": 1},
        ]),
    )
    mock_run.side_effect = [init_result, callers_result]

    result = compute_blast_radius_codegraph(tmp_path, {"target"}, diff_token_estimate=10000)

    assert len(result) == 1
    assert result[0]["changed_fn"] == "target"
    assert len(result[0]["callers"]) == 1
    assert result[0]["callers"][0]["fn"] == "caller_fn"
    assert "caller_fn" in result[0]["callers"][0]["code"]


@patch("app.services.blast_radius.shutil.which", return_value=None)
def test_codegraph_backend_graceful_when_cli_missing(_mock_which, tmp_path):
    """No codegraph CLI installed → empty list, no exception."""
    result = compute_blast_radius_codegraph(tmp_path, {"target"}, diff_token_estimate=10000)
    assert result == []


@patch("app.services.blast_radius.shutil.which", return_value="/usr/local/bin/codegraph")
@patch("app.services.blast_radius.subprocess.run")
def test_codegraph_backend_returns_empty_when_no_callers(mock_run, _mock_which, tmp_path):
    """codegraph returns zero callers → result list is empty."""
    init_result = MagicMock(returncode=0)
    callers_result = MagicMock(returncode=0, stdout=_codegraph_callers_output([]))
    mock_run.side_effect = [init_result, callers_result]

    result = compute_blast_radius_codegraph(tmp_path, {"orphan_fn"}, diff_token_estimate=10000)
    assert result == []


@patch("app.services.blast_radius.shutil.which", return_value="/usr/local/bin/codegraph")
@patch("app.services.blast_radius.subprocess.run")
def test_codegraph_backend_skips_init_when_dir_exists(mock_run, _mock_which, tmp_path):
    """If .codegraph dir already exists, init is NOT called."""
    (tmp_path / ".codegraph").mkdir()
    src_file = tmp_path / "b.py"
    src_file.write_text("def b(): fn()\n")

    callers_result = MagicMock(
        returncode=0,
        stdout=_codegraph_callers_output([
            {"name": "b", "filePath": str(src_file), "startLine": 1},
        ]),
    )
    mock_run.return_value = callers_result

    result = compute_blast_radius_codegraph(tmp_path, {"fn"}, diff_token_estimate=10000)

    # only one subprocess call (callers), no init
    assert mock_run.call_count == 1
    assert result[0]["changed_fn"] == "fn"


@patch("app.services.blast_radius.shutil.which", return_value="/usr/local/bin/codegraph")
@patch("app.services.blast_radius.subprocess.run")
def test_codegraph_backend_respects_token_budget(mock_run, _mock_which, tmp_path):
    """Token budget exhausted after first function → second function skipped."""
    (tmp_path / ".codegraph").mkdir()
    src_file = tmp_path / "big.py"
    # write 200 chars to cost ~50 tokens per caller
    src_file.write_text("x" * 200)

    callers_result = MagicMock(
        returncode=0,
        stdout=_codegraph_callers_output([
            {"name": "c1", "filePath": str(src_file), "startLine": 1},
        ]),
    )
    mock_run.return_value = callers_result

    # diff_token_estimate=10 → budget=5 tokens; snippet is ~50 tokens, so second fn is skipped
    result = compute_blast_radius_codegraph(
        tmp_path, {"fn_a", "fn_b"}, diff_token_estimate=10
    )
    # at most one group returned (budget hit after first fn)
    assert len(result) <= 1
