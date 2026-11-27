"""Copy a frontend release into the bundled Python distribution."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil

DESTINATION = Path(__file__).resolve().parents[1] / "umeko/server/static/ui"


def files(directory: Path) -> dict[str, bytes]:
    result = {}
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"前端成品不支持符号链接 {path}")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = path.read_bytes()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="前端仓发布的 dist 目录")
    parser.add_argument("--check", action="store_true", help="只比较打包的前端与指定成品")
    args = parser.parse_args()
    source = args.source.resolve()
    destination = DESTINATION.resolve()
    if destination != DESTINATION.absolute() or source == destination or source in destination.parents or destination in source.parents:
        parser.error("前端成品与内置资源目录必须相互独立，目标不能是符号链接")
    incoming = files(source)
    if not {"index.html", "admin.html"} <= incoming.keys() or not any(name.startswith("assets/") for name in incoming):
        parser.error("前端成品须包含 index.html、admin.html 和 assets/")
    current = files(destination)
    changed = sorted(name for name in incoming.keys() | current.keys() if incoming.get(name) != current.get(name))
    if args.check:
        if changed:
            raise SystemExit("内置前端与成品不同 " + ", ".join(changed[:12]))
        print("Bundled frontend matches the release.")
        return
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    for name in current.keys() - incoming.keys():
        (destination / name).unlink()
    for directory in sorted(destination.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    print(f"Bundled frontend installed ({len(incoming)} files).")


if __name__ == "__main__":
    main()
