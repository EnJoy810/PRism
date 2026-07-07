"""Tests for is_line_in_non_executable_context in evidence.py."""

import textwrap

from app.services.evidence import is_line_in_non_executable_context

# ---------------------------------------------------------------------------
# 工具函数：把真实文件内容格式化成 unified diff（只有新增行）
# ---------------------------------------------------------------------------

def _make_diff(file_path: str, content: str, start_line: int = 1) -> str:
    lines = content.splitlines()
    hunk_header = f"@@ -{start_line},{len(lines)} +{start_line},{len(lines)} @@"
    added = "\n".join(f"+{line}" for line in lines)
    return f"+++ b/{file_path}\n{hunk_header}\n{added}\n"


# ---------------------------------------------------------------------------
# Python docstring 场景
# ---------------------------------------------------------------------------

def test_python_line_in_triple_double_quote_docstring():
    """Multiline docstring detection is intentionally NOT supported.

    Tracking docstring open/close via diff reconstruction is fragile: context
    lines may be missing from diffs, breaking the state machine and causing
    real findings to be dropped. LLM agents are instructed in their system
    prompts to skip docstring content directly (industry practice).

    This test documents the known limitation: a line inside a multiline
    docstring is NOT filtered by is_line_in_non_executable_context.
    """
    content = textwrap.dedent("""\
        def _extract_ts_imports(self, content: str) -> list[str]:
            \"\"\"
            Extract TypeScript imports from content.

            Supports:
                import { X, Y } from './path'
                import X from './path'
            \"\"\"
            pattern = re.compile(r'import')
    """)
    diff = _make_diff("app/services/indexer.py", content)
    # line 6: inside docstring — NOT filtered (multiline detection removed)
    assert is_line_in_non_executable_context(diff, "app/services/indexer.py", 6) is False


def test_python_line_after_docstring_is_code():
    content = textwrap.dedent("""\
        def _extract_ts_imports(self, content: str) -> list[str]:
            \"\"\"Docstring here.\"\"\"
            pattern = re.compile(r'import')
            return pattern.findall(content)
    """)
    diff = _make_diff("app/services/indexer.py", content)
    # line 3: "    pattern = re.compile(...)"  — 真实代码
    assert is_line_in_non_executable_context(diff, "app/services/indexer.py", 3) is False


def test_python_single_line_comment():
    content = textwrap.dedent("""\
        def foo():
            # This is a comment import { X } from './path'
            x = 1
    """)
    diff = _make_diff("app/foo.py", content)
    assert is_line_in_non_executable_context(diff, "app/foo.py", 2) is True


def test_python_triple_single_quote_docstring():
    """Same as above: multiline docstring detection is not supported.

    A line inside a triple-single-quote docstring is NOT filtered.
    The LLM system prompt handles this case at the source.
    """
    content = textwrap.dedent("""\
        def bar():
            '''
            Example:
                import X from './path'
            '''
            return 1
    """)
    diff = _make_diff("app/bar.py", content)
    # line 4: inside docstring — NOT filtered (multiline detection removed)
    assert is_line_in_non_executable_context(diff, "app/bar.py", 4) is False


# ---------------------------------------------------------------------------
# TypeScript / JavaScript 场景
# ---------------------------------------------------------------------------

def test_ts_jsdoc_block_comment():
    content = textwrap.dedent("""\
        /**
         * @example
         * import { X } from './path'
         */
        export function extractImports(src: string): string[] {
            return [];
        }
    """)
    diff = _make_diff("src/utils.ts", content)
    # line 1: "/**"  — JS doc opener
    assert is_line_in_non_executable_context(diff, "src/utils.ts", 1) is True
    # line 3: " * import { X } from './path'"  — 在 jsdoc 里（以 * 开头）
    assert is_line_in_non_executable_context(diff, "src/utils.ts", 3) is True
    # line 5: "export function extractImports..."  — 真实代码
    assert is_line_in_non_executable_context(diff, "src/utils.ts", 5) is False


def test_ts_single_line_comment():
    content = textwrap.dedent("""\
        // import { X } from './path'
        const x = 1;
    """)
    diff = _make_diff("src/foo.ts", content)
    assert is_line_in_non_executable_context(diff, "src/foo.ts", 1) is True
    assert is_line_in_non_executable_context(diff, "src/foo.ts", 2) is False


# ---------------------------------------------------------------------------
# 边界情况
# ---------------------------------------------------------------------------

def test_none_line_returns_false():
    diff = _make_diff("app/foo.py", "x = 1\n")
    assert is_line_in_non_executable_context(diff, "app/foo.py", None) is False


def test_file_not_in_diff_returns_false():
    diff = _make_diff("app/foo.py", "x = 1\n")
    assert is_line_in_non_executable_context(diff, "app/bar.py", 1) is False


def test_real_code_line_returns_false():
    content = textwrap.dedent("""\
        def foo():
            x = import_module('os')
            return x
    """)
    diff = _make_diff("app/foo.py", content)
    # line 2: "    x = import_module('os')"  — 真实代码（虽然有 import 字样）
    assert is_line_in_non_executable_context(diff, "app/foo.py", 2) is False


# ---------------------------------------------------------------------------
# *args / **kwargs 不应被误判为注释（旧代码 startswith("*") 的 bug 修复）
# ---------------------------------------------------------------------------

def test_python_args_not_treated_as_comment():
    content = textwrap.dedent("""\
        def foo(*args, **kwargs):
            return args
    """)
    diff = _make_diff("app/foo.py", content)
    # line 1: "def foo(*args, **kwargs):"  — 真实代码
    assert is_line_in_non_executable_context(diff, "app/foo.py", 1) is False


def test_python_kwargs_not_treated_as_comment():
    content = textwrap.dedent("""\
        def foo(**kwargs):
            return kwargs
    """)
    diff = _make_diff("app/foo.py", content)
    # line 1: "def foo(**kwargs):"  — 真实代码
    assert is_line_in_non_executable_context(diff, "app/foo.py", 1) is False


def test_jsdoc_continuation_line_with_star_is_comment():
    """A line starting with '* ' (JSDoc continuation) IS a comment."""
    content = textwrap.dedent("""\
        * This is a JSDoc continuation line
    """)
    diff = _make_diff("src/foo.ts", content)
    assert is_line_in_non_executable_context(diff, "src/foo.ts", 1) is True


def test_lone_star_is_comment():
    """A bare '*' line (JSDoc closer area) IS a comment."""
    content = "*\n"
    diff = _make_diff("src/foo.ts", content)
    assert is_line_in_non_executable_context(diff, "src/foo.ts", 1) is True
