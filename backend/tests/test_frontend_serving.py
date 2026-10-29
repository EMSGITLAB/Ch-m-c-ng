from app.frontend import install_frontend
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_compiled_frontend_preserves_api_and_never_serves_project_data(tmp_path):
    public = tmp_path / "dist"
    public.mkdir()
    (public / "index.html").write_text("<html>Local attendance</html>")
    (tmp_path / ".env").write_text("private-secret")
    app = FastAPI()

    @app.get("/api/test")
    def api():
        return {"api": True}

    assert install_frontend(app, public)
    with TestClient(app) as browser:
        assert "Local attendance" in browser.get("/").text
        assert browser.get("/api/test").json() == {"api": True}
        for path in ("/.env", "/data/private.jpg", "/%2e%2e/.env", "/api/missing"):
            assert browser.get(path).status_code == 404


def test_api_remains_usable_without_a_frontend_build(tmp_path):
    assert install_frontend(FastAPI(), tmp_path) is False
