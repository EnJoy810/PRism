from pathlib import Path

from app.services.verifier import (
    ImportedSymbolRef,
    VerificationStatus,
    build_dependency_index,
    extract_imported_symbols_from_diff,
    extract_imports_from_diff,
    import_exists,
    package_dependency_exists,
    verify_diff_imports,
    verify_imported_symbol,
)


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_extract_imports_from_diff_ignores_removed_lines():
    diff = """
diff --git a/src/App.tsx b/src/App.tsx
@@ -1,2 +1,3 @@
-import OldButton from './OldButton'
+import Button from './components/Button'
+import { Search } from 'lucide-react'
 const x = 1
"""

    imports = extract_imports_from_diff(diff)

    assert [ref.module for ref in imports] == ["./components/Button", "lucide-react"]
    assert imports[0].file_path == "src/App.tsx"
    assert imports[0].line == 1


def test_import_exists_for_relative_tsx_file(tmp_path):
    repo = tmp_path
    _write(repo / "src/App.tsx", "import Button from './components/Button'\n")
    _write(repo / "src/components/Button.tsx", "export function Button() {}\n")
    ref = extract_imports_from_diff(
        """
diff --git a/src/App.tsx b/src/App.tsx
@@ -1,0 +1,1 @@
+import Button from './components/Button'
"""
    )[0]

    result = import_exists(repo, ref)

    assert result.status == VerificationStatus.PASS
    assert result.detail.endswith("src/components/Button.tsx")


def test_import_exists_for_relative_index_file(tmp_path):
    repo = tmp_path
    _write(repo / "src/App.tsx", "import ui from './components'\n")
    _write(repo / "src/components/index.ts", "export const ui = {}\n")
    ref = extract_imports_from_diff(
        """
diff --git a/src/App.tsx b/src/App.tsx
@@ -1,0 +1,1 @@
+import ui from './components'
"""
    )[0]

    result = import_exists(repo, ref)

    assert result.status == VerificationStatus.PASS
    assert result.detail.endswith("src/components/index.ts")


def test_import_exists_for_missing_relative_file(tmp_path):
    repo = tmp_path
    _write(repo / "src/App.tsx", "import Missing from './Missing'\n")
    ref = extract_imports_from_diff(
        """
diff --git a/src/App.tsx b/src/App.tsx
@@ -1,0 +1,1 @@
+import Missing from './Missing'
"""
    )[0]

    result = import_exists(repo, ref)

    assert result.status == VerificationStatus.FAIL
    assert "not found" in result.detail


def test_import_exists_for_tsconfig_path_alias(tmp_path):
    repo = tmp_path
    _write(
        repo / "tsconfig.json",
        '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}',
    )
    _write(repo / "src/components/Button.tsx", "export function Button() {}\n")
    ref = extract_imports_from_diff(
        """
diff --git a/src/App.tsx b/src/App.tsx
@@ -1,0 +1,1 @@
+import Button from '@/components/Button'
"""
    )[0]

    result = import_exists(repo, ref)

    assert result.status == VerificationStatus.PASS
    assert result.detail.endswith("src/components/Button.tsx")


def test_import_exists_for_unconfigured_alias_is_unknown(tmp_path):
    repo = tmp_path
    ref = extract_imports_from_diff(
        """
diff --git a/src/App.tsx b/src/App.tsx
@@ -1,0 +1,1 @@
+import Button from '@/components/Button'
"""
    )[0]

    result = import_exists(repo, ref)

    assert result.status == VerificationStatus.UNKNOWN
    assert "path alias" in result.detail


def test_package_dependency_exists_for_declared_dependency(tmp_path):
    repo = tmp_path
    _write(
        repo / "package.json",
        '{"dependencies":{"lucide-react":"^0.468.0"},"devDependencies":{}}',
    )
    index = build_dependency_index(repo)

    result = package_dependency_exists(repo, "lucide-react", index)

    assert result.status == VerificationStatus.PASS
    assert result.detail == "dependencies"


def test_package_dependency_exists_for_scoped_dependency(tmp_path):
    repo = tmp_path
    _write(repo / "package.json", '{"devDependencies":{"@vitejs/plugin-react":"latest"}}')
    index = build_dependency_index(repo)

    result = package_dependency_exists(repo, "@vitejs/plugin-react/jsx-runtime", index)

    assert result.status == VerificationStatus.PASS
    assert result.detail == "devDependencies"


def test_package_dependency_exists_for_missing_dependency(tmp_path):
    repo = tmp_path
    _write(repo / "package.json", '{"dependencies":{"react":"latest"}}')
    index = build_dependency_index(repo)

    result = package_dependency_exists(repo, "lucide-react", index)

    assert result.status == VerificationStatus.FAIL
    assert "not declared" in result.detail


def test_package_dependency_exists_unknown_without_package_json(tmp_path):
    result = package_dependency_exists(tmp_path, "lucide-react")

    assert result.status == VerificationStatus.UNKNOWN
    assert "package.json" in result.detail


def test_verify_diff_imports_checks_relative_and_package_imports(tmp_path):
    repo = tmp_path
    _write(repo / "src/components/Button.tsx", "export function Button() {}\n")
    _write(repo / "package.json", '{"dependencies":{"lucide-react":"latest"}}')
    diff = """
diff --git a/src/App.tsx b/src/App.tsx
@@ -1,0 +1,2 @@
+import Button from './components/Button'
+import { Search } from 'lucide-react'
"""

    result = verify_diff_imports(repo, diff)

    assert len(result["imports"]) == 2
    assert {item["module"]: item["status"] for item in result["imports"]} == {
        "./components/Button": "pass",
        "lucide-react": "pass",
    }


def test_extract_imported_symbols_from_diff_for_named_imports():
    diff = """
diff --git a/src/App.tsx b/src/App.tsx
@@ -1,0 +1,2 @@
+import { Button, useFoo as localUseFoo } from './components/Button'
+import { Search } from 'lucide-react'
"""

    symbols = extract_imported_symbols_from_diff(diff)

    assert [(ref.module, ref.symbol) for ref in symbols] == [
        ("./components/Button", "Button"),
        ("./components/Button", "useFoo"),
    ]


def test_extract_imported_symbols_from_diff_for_alias_named_imports():
    diff = """
diff --git a/src/App.tsx b/src/App.tsx
@@ -1,0 +1,1 @@
+import { Button } from '@/components/Button'
"""

    symbols = extract_imported_symbols_from_diff(diff)

    assert [(ref.module, ref.symbol) for ref in symbols] == [("@/components/Button", "Button")]


def test_extract_imported_symbols_ignores_default_namespace_package_and_side_effect_imports():
    diff = """
diff --git a/src/App.tsx b/src/App.tsx
@@ -1,0 +1,4 @@
+import Button from './components/Button'
+import * as ButtonModule from './components/Button'
+import './global.css'
+import { Search } from 'lucide-react'
"""

    assert extract_imported_symbols_from_diff(diff) == []


def test_verify_imported_symbol_passes_export_function(tmp_path):
    repo = tmp_path
    _write(repo / "src/components/Button.tsx", "export function Button() {}\n")
    ref = ImportedSymbolRef(
        file_path="src/App.tsx",
        line=1,
        module="./components/Button",
        symbol="Button",
        import_kind="named",
        statement="import { Button } from './components/Button'",
    )

    result = verify_imported_symbol(repo, ref)

    assert result.status == VerificationStatus.PASS
    assert result.detail == "named export found"


def test_verify_imported_symbol_passes_export_const_and_type(tmp_path):
    repo = tmp_path
    _write(repo / "src/components/hooks.ts", "export const useFoo = () => null\nexport type Props = {}\n")
    refs = [
        ImportedSymbolRef("src/App.tsx", 1, "./components/hooks", "useFoo", "named", ""),
        ImportedSymbolRef("src/App.tsx", 1, "./components/hooks", "Props", "named", ""),
    ]

    results = [verify_imported_symbol(repo, ref) for ref in refs]

    assert [result.status for result in results] == [VerificationStatus.PASS, VerificationStatus.PASS]


def test_verify_imported_symbol_passes_export_list_and_default_alias(tmp_path):
    repo = tmp_path
    _write(
        repo / "src/components/index.ts",
        "const Button = () => null\nexport { Button }\nexport { default as MarketingNavbar } from './MarketingNavbar'\n",
    )
    refs = [
        ImportedSymbolRef("src/App.tsx", 1, "./components", "Button", "named", ""),
        ImportedSymbolRef("src/App.tsx", 1, "./components", "MarketingNavbar", "named", ""),
    ]

    results = [verify_imported_symbol(repo, ref) for ref in refs]

    assert [result.status for result in results] == [VerificationStatus.PASS, VerificationStatus.PASS]


def test_verify_imported_symbol_fails_missing_named_export(tmp_path):
    repo = tmp_path
    _write(repo / "src/components/Button.tsx", "export function Button() {}\n")
    ref = ImportedSymbolRef("src/App.tsx", 1, "./components/Button", "MarketingNavbar", "named", "")

    result = verify_imported_symbol(repo, ref)

    assert result.status == VerificationStatus.FAIL
    assert "MarketingNavbar" in result.detail


def test_verify_imported_symbol_unknown_for_export_star(tmp_path):
    repo = tmp_path
    _write(repo / "src/components/index.ts", "export * from './Button'\n")
    ref = ImportedSymbolRef("src/App.tsx", 1, "./components", "Button", "named", "")

    result = verify_imported_symbol(repo, ref)

    assert result.status == VerificationStatus.UNKNOWN
    assert "export *" in result.detail


def test_verify_imported_symbol_passes_tsconfig_path_alias(tmp_path):
    repo = tmp_path
    _write(
        repo / "tsconfig.json",
        '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}',
    )
    _write(repo / "src/components/Button.tsx", "export function Button() {}\n")
    ref = ImportedSymbolRef("src/App.tsx", 1, "@/components/Button", "Button", "named", "")

    result = verify_imported_symbol(repo, ref)

    assert result.status == VerificationStatus.PASS


def test_verify_diff_imports_includes_export_checks(tmp_path):
    repo = tmp_path
    _write(repo / "src/components/Button.tsx", "export function Button() {}\n")
    diff = """
diff --git a/src/App.tsx b/src/App.tsx
@@ -1,0 +1,1 @@
+import { Button, Missing } from './components/Button'
"""

    result = verify_diff_imports(repo, diff)

    assert [item["symbol"] for item in result["exports"]] == ["Button", "Missing"]
    assert {item["symbol"]: item["status"] for item in result["exports"]} == {
        "Button": "pass",
        "Missing": "fail",
    }
