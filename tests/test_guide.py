"""The bundled handbook follows each surface and the configured public base."""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import pytest
from fastapi.testclient import TestClient

from umeko.config import ModelConfig, Settings
from umeko.server.admin import create_admin_app
from umeko.server.app import create_app
from umeko.server.guide import GUIDE_DIR


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        value = attrs.get("src") if tag in {"script", "img"} else attrs.get("href") if tag == "link" else None
        if value and not value.startswith("#"):
            self.paths.append(value)


@pytest.mark.parametrize("user_prefix,admin_prefix", [("", ""), ("/teams/demo/workbench", "/operations/console")])
@pytest.mark.parametrize("configured", [False, True])
def test_bundled_handbook_prefix_and_public_links(tmp_path, user_prefix, admin_prefix, configured):
    public = "https://agents.example.internal" + user_prefix if configured else None
    settings = Settings(ModelConfig("test", "key", "https://models.example.invalid/v1"),
                        base_path=user_prefix, admin_base_path=admin_prefix, public_url=public)
    app = create_app(settings, data_root=tmp_path / "data", workspace_root=tmp_path / "output")
    service = app.state.agent_service
    admin_app = create_admin_app(settings, service, app.state.store)
    try:
        for surface, prefix in [(app, user_prefix), (admin_app, admin_prefix)]:
            with TestClient(surface) as client:
                expected = (public or prefix) + "/guide/"
                assert f'name="umeko-guide-url" content="{expected}"' in client.get(prefix + "/").text
                assert client.get(prefix + "/guide", follow_redirects=False).status_code == 307
                for relative in ("", "architecture/", "admin/models/", "integration/mcp/", "integration/lifecycle/"):
                    url = prefix + "/guide/" + relative
                    page = client.get(url)
                    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
                    resources = Resources()
                    resources.feed(page.text)
                    assert resources.paths
                    for path in resources.paths:
                        resolved = urlsplit(urljoin("http://testserver" + url, path))
                        assert resolved.netloc == "testserver", "No runtime CDN dependencies"
                        assert resolved.path.startswith(prefix + "/guide/")
                        assert client.get(resolved.path).status_code == 200
                assert client.get(prefix + "/guide/search/search_index.json").status_code == 200
                for path in (GUIDE_DIR / "assets/screenshots").glob("*.jpg"):
                    assert client.get(prefix + "/guide/assets/screenshots/" + path.name).status_code == 200
                assert client.get(prefix + "/guide/not-a-page/").status_code == 404
                assert client.get(prefix + "/guide/assets/%2e%2e/%2e%2e/%2e%2e/ui.py").status_code == 404
                assert client.get(prefix + ("/v1/sessions" if surface is app else "/admin/v1/users")).status_code == 401
                if surface is app:
                    temporary = client.get(user_prefix + "/TMP/synthetic-token").text
                    assert f'name="umeko-guide-url" content="{(public or user_prefix) + "/guide/"}"' in temporary
                    assert "synthetic-token/guide" not in temporary
                    assert client.get(user_prefix + "/guidebook").status_code == 404
    finally:
        service.run_manager.shutdown()
