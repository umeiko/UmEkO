"""Build/check the public admin Skill ZIP with native 7-Zip; no live data."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from umeko.archives import archive_members, extract_archive, write_zip
from umeko.server.admin_automation import SKILL_ARCHIVE, SKILL_FILES, SKILL_ROOT


def check_archive(archive: Path) -> None:
    expected = {"umeko-server-admin/" + name for name in SKILL_FILES}
    actual = {item.name.replace("\\", "/") for item in archive_members(archive) if not item.directory}
    if actual != expected:
        raise ValueError("Admin Skill ZIP file list differs from the public manifest")
    # Extract only the checked, bundled archive using the native archive backend.
    with tempfile.TemporaryDirectory(prefix="umeko-admin-skill-check-") as temporary:
        copied = Path(temporary) / "bundle.zip"
        shutil.copyfile(archive, copied)
        extracted = extract_archive(copied)
        if any((extracted / name).read_bytes() != (SKILL_ROOT / name).read_bytes() for name in SKILL_FILES):
            raise ValueError("Admin Skill ZIP is out of date; run scripts/build_admin_skill.py")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check_archive(SKILL_ARCHIVE)
        print("Admin Skill ZIP checked.")
        return
    with tempfile.TemporaryDirectory(prefix="umeko-admin-skill-build-") as temporary:
        source = Path(temporary) / "umeko-server-admin"
        for name in SKILL_FILES:
            destination = source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SKILL_ROOT / name, destination)
        archive = write_zip(source, Path(temporary) / "bundle.zip")
        check_archive(archive)
        shutil.copyfile(archive, SKILL_ARCHIVE)
    print("Admin Skill ZIP built.")


if __name__ == "__main__":
    main()
