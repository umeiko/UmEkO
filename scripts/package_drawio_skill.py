"""Build an UmEkO-native skill ZIP from the bundled, model-free sources."""
from __future__ import annotations

import argparse
from pathlib import Path
import zipfile


def package_skill(output: Path) -> Path:
    assets = Path(__file__).resolve().parents[1] / "umeko" / "builtin_skills"
    sources = sorted((assets / "drawio-flowchart").rglob("*"))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sources:
            if source.is_file() and source.suffix in {".md", ".py", ".json", ".sh", ".txt"}:
                info = zipfile.ZipInfo(source.relative_to(assets).as_posix(), date_time=(2026, 10, 12, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, source.read_bytes())
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="打包 draw.io 默认 Skill（不调用模型）")
    parser.add_argument("--output", type=Path, default=Path("dist/skills/drawio-flowchart.zip"))
    print(package_skill(parser.parse_args().output))
