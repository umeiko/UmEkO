"""Documentation generation must isolate skills as well as databases and sessions."""
import importlib.util
import os
from pathlib import Path


def test_generator_ignores_and_restores_configured_skill_library(tmp_path, monkeypatch):
    filename = Path(__file__).resolve().parents[1] / "scripts/generate_api_docs.py"
    spec = importlib.util.spec_from_file_location("api_docs_fixture", filename)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    library = tmp_path / "configured-skills"
    library.mkdir()
    marker = library / "keep.txt"
    marker.write_text("unchanged", encoding="utf-8")
    monkeypatch.setenv("UMEKO_SKILL_DIR", str(library))
    create_app = generator.create_app
    seen = []

    def isolated_app(settings, **kwargs):
        actual = Path(os.environ["UMEKO_SKILL_DIR"])
        assert actual != library and actual.parent == kwargs["data_root"].parent
        seen.append(actual)
        return create_app(settings, **kwargs)

    monkeypatch.setattr(generator, "create_app", isolated_app)
    assert generator.generate()
    assert seen and not seen[0].exists()
    assert os.environ["UMEKO_SKILL_DIR"] == str(library)
    assert list(library.iterdir()) == [marker] and marker.read_text(encoding="utf-8") == "unchanged"
