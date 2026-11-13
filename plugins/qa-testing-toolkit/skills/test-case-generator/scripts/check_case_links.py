#!/usr/bin/env python3
"""Opt-in, read-only V3 reference checks within an explicit local content root."""
from __future__ import annotations

import argparse
import json
import os
import posixpath
import sys
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True
from test_case_contract import ValidationError, no_duplicate_keys, require, validate


def content_path(root: Path, relative: str) -> Path:
    """Reject filesystem indirection before reading any referenced content."""
    parts = PurePosixPath(relative).parts
    require(bool(parts) and not relative.startswith(("/", "-")), "文件路径无效")
    require(not any(part == ".." or part.lower() == ".git" for part in parts),
            f"文件引用越界或访问 .git：{relative}")
    current = root
    for part in parts:
        current /= part
        require(not current.is_symlink(), f"禁止符号链接：{relative}")
        if current.is_dir():
            require(not (current / ".git").exists(), f"禁止嵌套仓库或子模块：{relative}")
    return current


def reference_candidates(cases_path: str, reference: str) -> list[str]:
    require(bool(reference.strip()) and ":" not in reference and "\\" not in reference
            and not reference.startswith("/"), "文件引用必须为内容根目录内相对路径")
    require(not any(part.lower() == ".git" for part in reference.split("/")), "禁止访问 .git")
    local = posixpath.normpath(posixpath.join(str(PurePosixPath(cases_path).parent), reference))
    if reference.startswith(("./", "../")):
        return [local]
    return list(dict.fromkeys([local, posixpath.normpath(reference)]))


def resolve_reference(root: Path, cases_path: str, reference: str) -> Path:
    candidates = [content_path(root, path) for path in reference_candidates(cases_path, reference)]
    for path in candidates:
        require(not path.exists() or path.is_file(), f"引用目标必须是文件：{reference}")
    matches = [path for path in candidates if path.is_file()]
    require(len(matches) <= 1, f"文件引用有歧义，请使用 ./ 或 ../：{reference}")
    require(bool(matches), f"引用文件不存在：{reference}")
    text = matches[0].read_text(encoding="utf-8")
    require("\x00" not in text, f"关联文件必须是 UTF-8 文本：{reference}")
    return matches[0]


def check_links(cases: Path, root: Path, summary: Path | None = None) -> tuple[dict, list[str]]:
    root = root.resolve(strict=True)
    require(root.is_dir(), "内容根目录必须是目录")
    cases = Path(os.path.abspath(cases))
    require(cases.is_relative_to(root), "用例 JSON 必须位于内容根目录内")
    cases_path = cases.relative_to(root).as_posix()
    document = json.loads(content_path(root, cases_path).read_text(encoding="utf-8"),
                          object_pairs_hook=no_duplicate_keys)
    _, version, warnings = validate(document)
    require(version == "3.0", "关联文件检查仅支持 V3，请先确认历史输入迁移目标")
    metadata = document["metadata"]
    linked = {}
    target = metadata["artifacts"]["summary"]
    if target is not None:
        linked["summary"] = resolve_reference(root, cases_path, target)
    if summary is not None:
        require(target is not None, "metadata.artifacts.summary 为 null，与指定总结不一致")
        expected = Path(os.path.abspath(summary))
        require(expected.is_relative_to(root), "指定总结越出内容根目录")
        content_path(root, expected.relative_to(root).as_posix())
        require(expected == linked["summary"], "指定总结与 metadata.artifacts.summary 不一致")

    source = metadata["source"]
    if ":" in source or source.startswith(("/", "~", "\\")):
        warnings.append("metadata.source 为外部来源，仅保留来源信息，内容未捕获")
    else:
        try:
            linked["source"] = resolve_reference(root, cases_path, source)
        except ValidationError as exc:
            # Match ACM's prose exception, while keeping explicit file failures visible.
            if (str(exc).startswith("引用文件不存在：") and "/" not in source
                    and not PurePosixPath(source).suffix):
                warnings.append("metadata.source 为文字说明，仅保留来源信息，内容未捕获")
            else:
                raise
    return linked, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("--root", required=True, type=Path, help="本地内容边界；项目接入时为用例仓库根目录")
    parser.add_argument("--summary", type=Path, help="核对实际交付总结与 metadata 引用是否一致")
    args = parser.parse_args()
    try:
        linked, warnings = check_links(args.cases, args.root, args.summary)
    except (OSError, ValueError) as exc:
        print(f"关联检查失败：{exc}", file=sys.stderr)
        return 1
    for key, path in linked.items():
        print(f"{key}：{path}")
    for warning in warnings:
        print(f"提示：{warning}")
    print("本地关联检查通过。输入提交内的可读性及系统捕获状态仍需按项目接入流程核对。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
