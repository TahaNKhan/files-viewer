import asyncio
from pathlib import Path

import httpx

from app.main import Settings, Root, _markdown, _open_path, create_app


def make_app(tmp_path):
    projects = tmp_path / "projects"; hermes = tmp_path / "hermes"
    projects.mkdir(); hermes.mkdir()
    (projects / "readme.md").write_text("# Hello\n\n<script>alert(1)</script>", encoding="utf-8")
    (projects / "note.txt").write_text("plain", encoding="utf-8")
    (hermes / "home.txt").write_text("home", encoding="utf-8")
    roots = {n: Root(n, p, n.title(), __import__('os').open(p, __import__('os').O_RDONLY | __import__('os').O_DIRECTORY)) for n,p in (("projects", projects), ("hermes", hermes))}
    settings = Settings(roots, {"projects": (), "hermes": ()}, Path("static"), 1024, 2000, True)
    return create_app(settings)


def test_paths_and_content(tmp_path):
    app = make_app(tmp_path)
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/healthz")).status_code == 200
            roots = await client.get("/api/roots")
            assert roots.status_code == 200 and roots.json()["roots"][0]["route"] == "/projects"
            assert (await client.get("/api/list/projects")).json()["entries"][0]["name"] == "note.txt"
            md = await client.get("/api/file/projects/readme.md")
            assert md.status_code == 200 and "<script" not in md.text
            raw = await client.get("/api/file/projects/readme.md?raw")
            assert raw.status_code == 200 and raw.content == b"# Hello\n\n<script>alert(1)</script>"
            assert raw.headers["content-type"].startswith("text/plain")
            public_raw = await client.get("/projects/readme.md?raw")
            assert public_raw.status_code == 200 and public_raw.content == raw.content
            assert (await client.get("/projects?raw")).status_code == 400
            assert (await client.get("/projects?direct")).status_code == 400
            assert (await client.get("/api/file/projects/readme.md?raw=maybe")).status_code == 400
            assert (await client.get("/api/file/projects/readme.md?raw&raw")).status_code == 400
            assert (await client.get("/api/file/projects/.env")).status_code == 404
    asyncio.run(run())
    try:
        _open_path(app.state.settings, "projects/../hermes/home.txt")
    except Exception as exc:
        assert getattr(exc, "status", None) == 403
    else:
        raise AssertionError("traversal was accepted")


def test_github_flavored_markdown_is_sanitized():
    root = Root("projects", Path("/tmp"), "Projects", -1)
    rendered = _markdown("~~old~~\n\n- [x] done\n\n| A | B |\n| - | - |\n| 1 | 2 |\n\n<script>x</script>", root, ["readme.md"])
    assert "<s>old</s>" in rendered
    assert 'class="task-list-item"' in rendered
    assert "<table>" in rendered
    assert "<script" not in rendered
