# pydantic-10500

PR: https://github.com/pydantic/pydantic/pull/10500
Summary: Support constraints for `Base64Bytes` with core schema fix
Risk: HIGH
Recommendation: REQUEST_CHANGES
Issues: 2

## Findings

### 1. 重复的测试函数名导致原有参数化测试被覆盖
- severity: ERROR
- file: tests/test_types.py:7020
- confidence: 0.95
- description: 新增的 `test_base64_with_invalid_min_length` 函数与同一文件中已存在的同名函数（定义于约 7219 行）冲突。Python 允许后定义的函数覆盖前一个，导致原有的参数化测试（覆盖 `Base64Bytes`、`Base64Str`、`Base64UrlBytes`、`Base64UrlStr` 四种类型）被完全替换，`Base64Str` 和 `Base64UrlStr` 的约束验证不再被执行。后果是在未来重构时，这两个类型的 `min_length`/`max_length` 异常路径将失去测试覆盖，可能出现行为回归而无法被及时发现。
- evidence: def test_base64_with_invalid_min_length() -> None:,     """Check that an error is raised when the length of the base64,     value is less or more than the min_length and max_length""", ,     class Model(BaseModel):,         base64_value: Base64Bytes = Field(min_length=3, max_length=5), ,     with pytest.raises(ValidationError):,         Model(**{'base64_value': b''}), ,     with pytest.raises(ValidationError):,         Model(**{'base64_value': b'123456'})
- human_label: TODO
- label_reason: TODO

### 2. 调用 `handler(source)` 可能引发无限递归（当 source 为 `EncodedBytes` 子类时）
- severity: WARNING
- file: pydantic/types.py:2481
- confidence: 0.7
- description: 在 `EncodedBytes.__get_pydantic_core_schema__` 中，新增的 `schema = handler(source)` 语句会触发对当前类型的 core schema 获取。如果 `source` 是 `EncodedBytes` 的非重写子类（如 `Base64Bytes`、`Base64UrlBytes` 等），`handler` 可能会再次调用当前方法，导致递归调用栈溢出（RuntimeError: maximum recursion depth exceeded）。虽然 Pydantic 内部可能有递归检测机制，但此修改将原本直接返回 `core_schema.bytes_schema()` 的安全路径改为依赖外部处理器，增加了递归风险。一旦递归发生，验证过程会崩溃，且难以调试。
- evidence:         schema = handler(source),         if (schema_type := schema['type']) not in ('bytes', 'str'):,             raise PydanticUserError(f"'EncodedBytes' cannot annotate '{schema_type}'.", code='invalid-annotated-type')
- human_label: TODO
- label_reason: TODO
