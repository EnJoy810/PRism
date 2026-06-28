import re

# 每个 chunk 的 token 估算上限（4 chars ≈ 1 token）
_CHUNK_CHAR_LIMIT = 4800  # ~1200 tokens


def chunk_diff_by_file(diff: str) -> list[dict]:
    """把 unified diff 按文件切分，每个文件一个 chunk。

    超过 _CHUNK_CHAR_LIMIT 的单文件 diff 进一步按 hunk 切分，
    保证每个 chunk 在模型的有效注意力范围内。

    返回 list[{"file": str, "diff": str}]。
    """
    if not diff:
        return []

    # 先按文件边界切
    file_diffs: list[dict] = []
    current_file: str | None = None
    current_lines: list[str] = []

    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            if current_file and current_lines:
                file_diffs.append({"file": current_file, "diff": "\n".join(current_lines)})
            current_file = None
            current_lines = [line]
        elif line.startswith("+++ b/") and current_lines:
            current_file = line[6:]
            current_lines.append(line)
        else:
            current_lines.append(line)

    if current_file and current_lines:
        file_diffs.append({"file": current_file, "diff": "\n".join(current_lines)})

    # 超大文件按 hunk 切
    result: list[dict] = []
    for fd in file_diffs:
        if len(fd["diff"]) <= _CHUNK_CHAR_LIMIT:
            result.append(fd)
            continue

        # 拆 hunk：找到所有 @@ 行作为切割点
        header_lines: list[str] = []
        hunks: list[list[str]] = []
        lines = fd["diff"].split("\n")
        current_hunk: list[str] = []
        in_hunk = False

        for line in lines:
            if line.startswith("@@"):
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = [line]
                in_hunk = True
            elif not in_hunk:
                header_lines.append(line)
            else:
                current_hunk.append(line)
        if current_hunk:
            hunks.append(current_hunk)

        header = "\n".join(header_lines)
        # 把多个 hunk 合并直到超限，超限就切一个 chunk
        batch: list[str] = []
        batch_len = len(header)
        for hunk in hunks:
            hunk_text = "\n".join(hunk)
            if batch and batch_len + len(hunk_text) > _CHUNK_CHAR_LIMIT:
                result.append({"file": fd["file"], "diff": header + "\n" + "\n".join(batch)})
                batch = [hunk_text]
                batch_len = len(header) + len(hunk_text)
            else:
                batch.append(hunk_text)
                batch_len += len(hunk_text)
        if batch:
            result.append({"file": fd["file"], "diff": header + "\n" + "\n".join(batch)})

    return result


def build_position_map(diff: str) -> dict[str, dict[int, int]]:
    """
    解析 unified diff，返回 {文件路径: {新文件行号: diff内position偏移量}}。

    GitHub Pull Request Review API 要求 inline comment 携带 position，
    即从每个文件第一个 hunk 头（@@ 行）开始的累计行偏移量。

    规则：
    - '+++ b/xxx'        → 切换文件，重置 position=0, new_line=0
    - '@@ ... +N,... @@' → new_line = N-1，position += 1（hunk 头本身占一个 position）
    - '+' 行             → new_line += 1，position += 1，记录映射
    - '-' 行             → position += 1（被删行不增加 new_line）
    - ' ' 行（context） → new_line += 1，position += 1
    - 其他行             → 跳过（diff --git、index、--- 行等）

    边界情况处理：
    - 同一文件出现多个 hunk：position 在文件内连续累加，不重置
    - 文件路径含空格：+++ b/ 之后直接截取，不做额外分割
    - 空 diff 或纯删除文件：返回空 dict
    - hunk 头解析失败（格式异常）：跳过该 hunk，不崩溃
    """
    result: dict[str, dict[int, int]] = {}
    current_file: str | None = None
    position = 0
    new_line = 0

    for line in diff.split("\n"):
        if line.startswith("+++ b/"):
            current_file = line[6:]
            position = 0
            new_line = 0
            result[current_file] = {}
        elif line.startswith("@@") and current_file is not None:
            m = re.search(r"\+(\d+)", line)
            if m:
                new_line = int(m.group(1)) - 1
            position += 1
        elif current_file is not None:
            if line.startswith("+"):
                new_line += 1
                position += 1
                result[current_file][new_line] = position
            elif line.startswith("-"):
                new_line += 1
                position += 1
            elif line.startswith(" "):
                new_line += 1
                position += 1
            # 其他行（空行、No newline at end of file 等）跳过

    return result
