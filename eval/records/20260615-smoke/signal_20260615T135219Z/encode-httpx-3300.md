# encode-httpx-3300

PR: https://github.com/encode/httpx/pull/3300
Summary: Add support for custom JSON encoders/decoders.
Risk: MEDIUM
Recommendation: COMMENT
Issues: 2

## Findings

### 1. 全局可变状态可能导致并发问题
- severity: WARNING
- file: httpx/_content.py:48
- confidence: 0.8
- description: `register_json_encoder` 和 `register_json_decoder` 通过模块级全局变量（`json_encoder`、`json_decoder`）存储自定义编/解码函数。这种设计会导致在多线程/多协程环境下不同请求之间相互干扰：一个线程调用 `register_*` 可能立即影响另一个线程正在进行的 `encode_json` 或 `decode_json` 调用，从而使用错误的编/解码器。同时，测试框架也依赖全局状态，测试之间可能互相影响（尽管当前测试使用 try/finally 恢复，但若其他测试未妥善处理，仍可能造成污染）。改进方向：将编/解码器设计为请求级别或客户端级别的配置，例如在 `Client` 对象上设置，而非全局注册。
- evidence:     json_encoder = json_encode_callable  # type: ignore,     json_decoder = json_decode_callable  # type: ignore,     body = json_encoder(json),     return json_decoder(json_data, **kwargs)
- human_label: TODO
- label_reason: TODO

### 2. register_json_decoder 类型签名不准确，可能导致类型检查失败和运行时错误
- severity: WARNING
- file: httpx/_content.py:48
- confidence: 0.9
- description: `register_json_decoder` 的类型标注为 `Callable[[bytes, Any], Any]`，强制要求解码函数接受两个位置参数（`bytes` 和 `Any`）。实际上，解码函数应通过 `**kwargs` 接受任意关键字参数（如 `object_hook`、`parse_float` 等）。当前签名会导致：1) 用户提供仅接受一个 `bytes` 参数的纯函数时，mypy 等类型检查工具报错（参数数量不匹配）；2) 若用户提供的函数不接受关键字参数（仅 `bytes`），而 `response.json()` 传入非空的 `**kwargs`，则运行时引发 `TypeError`。改进方向：将签名改为 `Callable[..., Any]` 或使用 `Protocol` 描述 `(bytes, **Any) -> Any`。
- evidence:     json_decode_callable: Callable[,         [bytes, Any],,         Any,,     ],
- human_label: TODO
- label_reason: TODO
