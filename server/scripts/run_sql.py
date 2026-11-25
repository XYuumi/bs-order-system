"""执行 sql/ 目录下的 SQL 迁移文件（逐句执行，打印每句结果，遇错默认继续到末尾汇总）。

用法：server 目录
  .venv/Scripts/python.exe scripts/run_sql.py sql/migrate_fks.sql [--stop]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: run_sql.py <sql文件> [--stop]")
        return 2
    sql_file = Path(sys.argv[1])
    stop_on_error = "--stop" in sys.argv
    if not sql_file.exists():
        print(f"文件不存在: {sql_file}")
        return 2

    statements = []
    for chunk in sql_file.read_text(encoding="utf-8").split(";"):
        # 去掉每段开头的注释行（-- ...）后再判断是否为空语句
        lines = [ln for ln in chunk.split("\n") if ln.strip() and not ln.strip().startswith("--")]
        if lines:
            statements.append("\n".join(lines).strip())
    ok = err = 0
    with engine.begin() as conn:
        for i, stmt in enumerate(statements, 1):
            head = " ".join(stmt.split())[:76]
            try:
                conn.exec_driver_sql(stmt)
                ok += 1
                print(f"  [{i:02d}] OK   {head}")
            except Exception as exc:  # noqa: BLE001 —— 已存在约束等错误继续
                err += 1
                print(f"  [{i:02d}] FAIL {head}  →  {str(exc)[:90]}")
                if stop_on_error:
                    break
    print(f"\n完成：成功 {ok}，失败 {err}（失败多为约束已存在，可忽略）")
    return 1 if (err and stop_on_error) else 0


if __name__ == "__main__":
    sys.exit(main())
