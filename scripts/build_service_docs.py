"""Build/check the independent handbook bundled with wheels, source and exe."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tempfile

from mkdocs.commands.build import build
from mkdocs.config import load_config

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "umeko/server/static/guide"


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="umeko-handbook-") as temporary:
        output = Path(temporary) / "site"
        config = load_config(str(ROOT / "mkdocs.service.yml"), site_dir=str(output), strict=True)
        # The public base is configured at runtime. An absolute sitemap would
        # be empty, and its gzip build date makes cross-day checks unstable.
        build(config)
        for name in ("sitemap.xml", "sitemap.xml.gz"):
            (output / name).unlink(missing_ok=True)
        generated = files(output)
        current = files(DESTINATION) if DESTINATION.exists() else {}
        changed = sorted(k for k in generated.keys() | current.keys() if generated.get(k) != current.get(k))
        if args.check:
            if changed:
                raise SystemExit("Handbook build is out of date: " + ", ".join(changed[:15]))
            print("Service handbook checked.")
            return
        # Only the dedicated generated directory is writable. Never clean a
        # caller-provided path or follow a symlink out of the package directory.
        expected = ROOT.resolve() / "umeko/server/static/guide"
        if DESTINATION.resolve() != expected or any(p.is_symlink() for p in DESTINATION.rglob("*")):
            raise SystemExit("Unsafe handbook output directory")
        DESTINATION.mkdir(parents=True, exist_ok=True)
        for name in current.keys() - generated.keys():
            (DESTINATION / name).unlink()
        shutil.copytree(output, DESTINATION, dirs_exist_ok=True)
        for path in sorted(DESTINATION.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        print(f"Service handbook built: {len(generated)} files.")


if __name__ == "__main__":
    main()
