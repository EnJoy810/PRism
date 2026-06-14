from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.context import _extract_symbols_from_diff, fetch_symbol_context


class TestExtractSymbolsFromDiff:
    def test_python_import(self):
        diff = "+import os\n+from pathlib import Path\n-import old"
        symbols = _extract_symbols_from_diff(diff)
        assert "os" in symbols
        assert "Path" in symbols

    def test_js_import(self):
        diff = '+import { useState } from "react"\n+import axios from "axios"'
        symbols = _extract_symbols_from_diff(diff)
        assert "useState" in symbols
        assert "axios" in symbols

    def test_rust_use(self):
        diff = "+use std::collections::HashMap;"
        symbols = _extract_symbols_from_diff(diff)
        assert "HashMap" in symbols

    def test_function_calls(self):
        diff = "+const result = calculateTotal(items)\n+const data = await fetchData()"
        symbols = _extract_symbols_from_diff(diff)
        assert "calculateTotal" in symbols
        assert "fetchData" in symbols

    def test_keywords_filtered(self):
        diff = "+if (true) {\n+    return null\n+}"
        symbols = _extract_symbols_from_diff(diff)
        assert "if" not in symbols
        assert "return" not in symbols
        assert "true" not in symbols
        assert "null" not in symbols

    def test_empty_diff(self):
        symbols = _extract_symbols_from_diff("")
        assert symbols == []

    def test_no_added_lines(self):
        diff = "-old code\n- more old"
        symbols = _extract_symbols_from_diff(diff)
        assert symbols == []

    def test_only_context_lines(self):
        diff = " unchanged\n  also unchanged"
        symbols = _extract_symbols_from_diff(diff)
        assert symbols == []


_BASE64_FORMATDATE = (
    "ZXhwb3J0IGZ1bmN0aW9uIGZvcm1hdERhdGUoZGF0ZTogRGF0ZSk6IHN0cmluZyB7CiAg"
    "cmV0dXJuIGRhdGUudG9Mb2NhbGVEYXRlU3RyaW5nKCk7Cn0K"
)
_DECODED_FORMATDATE = (
    "export function formatDate(date: Date): string {\n"
    "  return date.toLocaleDateString();\n"
    "}\n"
)


class TestFetchSymbolContext:
    @pytest.mark.asyncio
    async def test_empty_diff(self):
        result = await fetch_symbol_context("owner", "repo", "main", [], "")
        assert result == {}

    @pytest.mark.asyncio
    async def test_no_symbols_in_diff(self):
        diff = "-old\n-only_deletions"
        result = await fetch_symbol_context("owner", "repo", "main", [], diff)
        assert result == {}

    @pytest.mark.asyncio
    async def test_symbol_definition_found(self):
        diff = "+import { formatDate } from './utils'\n" + "x" * 500
        mock_search_resp = {"items": [{"path": "src/utils.ts"}]}
        mock_content_data = {"content": _BASE64_FORMATDATE}

        async def mock_get(url, *args, **kwargs):
            resp = MagicMock()
            if "search/code" in url:
                resp.json = MagicMock(return_value=mock_search_resp)
            elif "contents" in url:
                resp.json = MagicMock(return_value=mock_content_data)
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            return resp

        with patch("httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.get = mock_get
            MockClient.return_value.__aenter__.return_value = client
            result = await fetch_symbol_context("owner", "repo", "main", [], diff)

        assert "formatDate" in result
        assert "function formatDate" in result["formatDate"]

    @pytest.mark.asyncio
    async def test_search_fails_gracefully(self):
        diff = "+import { formatDate } from './utils'"

        async def mock_get(url, *args, **kwargs):
            resp = MagicMock()
            resp.status_code = 500
            resp.raise_for_status = MagicMock(side_effect=Exception("API error"))
            return resp

        with patch("httpx.AsyncClient") as MockClient:
            client = AsyncMock()
            client.get = mock_get
            MockClient.return_value.__aenter__.return_value = client
            result = await fetch_symbol_context("owner", "repo", "main", [], diff)

        assert result == {}

    @pytest.mark.asyncio
    async def test_no_token_still_works(self):
        diff = "+import { formatDate } from './utils'\n" + "x" * 500
        mock_search_resp = {"items": [{"path": "src/utils.ts"}]}
        mock_content_data = {"content": _BASE64_FORMATDATE}

        async def mock_get(url, *args, **kwargs):
            resp = MagicMock()
            if "search/code" in url:
                resp.json = MagicMock(return_value=mock_search_resp)
            elif "contents" in url:
                resp.json = MagicMock(return_value=mock_content_data)
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            return resp

        with (
            patch("httpx.AsyncClient") as MockClient,
            patch("os.environ", {"GITHUB_TOKEN": ""}),
        ):
            client = AsyncMock()
            client.get = mock_get
            MockClient.return_value.__aenter__.return_value = client
            result = await fetch_symbol_context("owner", "repo", "main", [], diff, token=None)

        assert "formatDate" in result
