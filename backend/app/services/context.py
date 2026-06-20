"""Symbol-level context retrieval for PR diffs.

Extracts referenced symbols from diff changes and fetches their
definitions via GitHub Search API. Respects token budget:
definition context <= 50% of diff token count.
"""

import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

_IMPORT_PATTERNS = [
    re.compile(r"^\+.*?\bimport\s+(?:\w+\s*,\s*)?\{?\s*(\w+)\s*\}?\s+from\s+['\"]"),
    re.compile(r"^\+.*?\bfrom\s+['\"]\S+['\"]\s+import\s+\{?\s*(\w+)"),
    re.compile(r"^\+.*?\bimport\s+(\w+)"),
    re.compile(r"^\+.*?\buse\s+(?:\w+::)*(\w+)"),
]

_CALL_PATTERN = re.compile(r"^\+.*?\b(\w+)\s*\(")

# Python/JS 内置和标准库符号，搜了没有意义，浪费 Code Search 配额
_BUILTIN_SYMBOLS = {
    # Python builtins
    "len", "str", "int", "float", "bool", "list", "dict", "set", "tuple",
    "type", "isinstance", "issubclass", "hasattr", "getattr", "setattr",
    "print", "range", "enumerate", "zip", "map", "filter", "sorted",
    "min", "max", "sum", "abs", "round", "open", "super", "object",
    "property", "classmethod", "staticmethod", "next", "iter",
    "any", "all", "not", "and", "or", "in", "is",
    # asyncio
    "gather", "create_task", "sleep", "run",
    # logging
    "debug", "info", "warning", "error", "critical", "getLogger",
    # common stdlib
    "json", "os", "re", "sys", "time", "math", "Path", "datetime",
    # JS builtins
    "console", "Promise", "Array", "Object", "JSON", "Math",
    "setTimeout", "setInterval", "clearTimeout", "clearInterval",
}

_SYMBOL_CACHE: dict[str, str] = {}  # symbol_name -> definition_snippet
_RATE_LIMITED = object()  # sentinel：区分"没找到"和"被限速"


def _extract_symbols_from_diff(diff: str) -> list[str]:
    symbols: set[str] = set()

    for line in diff.split("\n"):
        if not line.startswith("+"):
            continue

        for pat in _IMPORT_PATTERNS:
            m = pat.search(line)
            if m:
                name = m.group(1)
                if name not in _BUILTIN_SYMBOLS:
                    symbols.add(name)

    # Also extract function calls from added lines
    _KEYWORD_SKIP = {"if", "for", "while", "switch", "return", "import",
                     "from", "throw", "await", "yield", "case", "catch",
                     "new", "this", "typeof", "describe", "it", "test",
                     "expect", "assert", "true", "false", "null", "undefined"}
    for line in diff.split("\n"):
        if not line.startswith("+"):
            continue
        m = _CALL_PATTERN.search(line)
        if m:
            name = m.group(1)
            if name not in _KEYWORD_SKIP and name not in _BUILTIN_SYMBOLS:
                symbols.add(name)

    return list(symbols)


async def _fetch_symbol_definition(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    symbol: str,
    headers: dict,
):
    cached = _SYMBOL_CACHE.get(symbol)
    if cached:
        return cached

    try:
        resp = await client.get(
            "https://api.github.com/search/code",
            params={
                "q": f"{symbol} in:file repo:{owner}/{repo}",
                "per_page": 3,
            },
            headers=headers,
        )
        if resp.status_code in (403, 429):
            logger.debug("symbol context: rate limited on '%s' (%d)", symbol, resp.status_code)
            return _RATE_LIMITED
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("items", [])[:1]:
            file_path = item["path"]
            file_resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}",
                headers=headers,
            )
            if file_resp.status_code != 200:
                continue

            file_data = file_resp.json()
            import base64
            content = base64.b64decode(file_data["content"]).decode("utf-8", errors="replace")
            lines = content.split("\n")

            line_numbers = {
                m.start() + 1: i + 1
                for i, m_line in enumerate(lines)
                for m in [re.search(rf'\b{re.escape(symbol)}\b', m_line)]
                if m
            }
            if not line_numbers:
                continue

            definition_line = min(line_numbers.values())
            start = max(0, definition_line - 3)
            end = min(len(lines), definition_line + 5)
            definition = "\n".join(
                f"{i + 1}:{lines[i]}"
                for i in range(start, end)
            )
            result = f"// {symbol} defined in {file_path}:{definition_line}\n{definition}"
            _SYMBOL_CACHE[symbol] = result
            return result

    except Exception as e:
        logger.debug("Failed to fetch definition for symbol '%s': %s", symbol, e)

    return None


async def fetch_symbol_context(
    owner: str,
    repo: str,
    ref: str,
    changed_files: list[str],
    diff: str,
    token: str | None = None,
) -> dict[str, str]:
    if not diff:
        return {}

    effective_token = token or os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if effective_token:
        headers["Authorization"] = f"Bearer {effective_token}"

    symbols = _extract_symbols_from_diff(diff)
    if not symbols:
        return {}

    diff_token_estimate = len(diff) // 4
    max_definition_tokens = diff_token_estimate // 2

    async with httpx.AsyncClient() as client:
        # 串行搜索，遇到速率限制立刻停，避免把配额全打光
        results = []
        for sym in symbols[:10]:
            result = await _fetch_symbol_definition(client, owner, repo, sym, headers)
            results.append(result)
            if result is _RATE_LIMITED:
                logger.debug("symbol context: rate limited, stopping early")
                break

    definitions: dict[str, str] = {}
    total_tokens = 0

    for symbol, snippet in zip(symbols[:10], results):
        if snippet is None or snippet is _RATE_LIMITED:
            continue
        snippet_tokens = len(snippet) // 4
        if total_tokens + snippet_tokens > max_definition_tokens:
            continue
        definitions[symbol] = snippet
        total_tokens += snippet_tokens

    return definitions
