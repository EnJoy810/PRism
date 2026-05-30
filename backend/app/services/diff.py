import re


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
                position += 1
            elif line.startswith(" "):
                new_line += 1
                position += 1
            # 其他行（空行、No newline at end of file 等）跳过

    return result
