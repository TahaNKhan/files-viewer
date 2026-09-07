from __future__ import annotations
import html, json, mimetypes, os, stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin
from starlette.exceptions import HTTPException as StarletteHTTPException

DEFAULT_DENIED_NAMES = {"node_modules", "target", "dist", "build", "__pycache__", ".venv", "venv"}
DEFAULT_DENIED_PATTERNS = ("id_rsa", "id_ed25519", "credentials", "secrets")
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".json", ".yaml", ".yml", ".toml", ".ini", ".conf", ".sh", ".bash", ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".htm", ".css", ".sql", ".rs", ".go", ".java", ".c", ".h", ".cpp", ".xml"}
RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

class ViewerError(Exception):
    def __init__(self, status: int, detail: str): self.status, self.detail = status, detail

@dataclass(frozen=True)
class Root:
    name: str; path: Path; label: str; fd: int

@dataclass(frozen=True)
class Settings:
    roots: dict[str, Root]; exclusions: dict[str, tuple[tuple[str, ...], ...]]; static_dir: Path; max_bytes: int; max_entries: int; serve_html: bool

def _deny_name(name: str) -> bool:
    lower = name.casefold()
    return name.startswith(".") or lower in DEFAULT_DENIED_NAMES or lower.endswith((".pem", ".key", ".p12", ".pfx")) or lower in DEFAULT_DENIED_PATTERNS or any(lower.startswith(p) for p in DEFAULT_DENIED_PATTERNS)

def _load_settings() -> Settings:
    roots = {}
    for item in os.getenv("SERVE_ROOTS", "projects:/srv/projects,hermes:/srv/hermes").split(","):
        try: name, raw_path = item.split(":", 1)
        except ValueError: raise RuntimeError("invalid root configuration")
        if not name or name in roots or not os.path.isabs(raw_path): raise RuntimeError("invalid root configuration")
        path = Path(raw_path)
        if not path.is_dir() or path.is_symlink(): raise RuntimeError(f"root is not a directory: {name}")
        roots[name] = Root(name, path, name.title(), os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
    config_path = Path(os.getenv("ACCESS_CONFIG", "config/access.json"))
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        exclusions = {}
        for root in roots:
            values = cfg.get("excluded_subtrees", {}).get(root, [])
            if not isinstance(values, list): raise ValueError
            parsed = []
            for value in values:
                parts = tuple(value.split("/"))
                if not value or value.startswith("/") or any(not p or p in (".", "..") for p in parts): raise ValueError
                parsed.append(parts)
            exclusions[root] = tuple(parsed)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc: raise RuntimeError("invalid access configuration") from exc
    return Settings(roots, exclusions, Path(os.getenv("STATIC_DIR", "static")), int(os.getenv("MAX_FILE_BYTES", "5242880")), int(os.getenv("MAX_LIST_ENTRIES", "2000")), os.getenv("SERVE_HTML", "1") == "1")

def _parts(raw: str | None) -> list[str]:
    if raw in (None, ""): return []
    if "\x00" in raw or "\\" in raw or raw.startswith("/"): raise ViewerError(403, "invalid path")
    bits = raw.split("/")
    if any(not bit or bit in (".", "..") for bit in bits): raise ViewerError(403, "invalid path")
    if any(_deny_name(bit) for bit in bits): raise ViewerError(404, "not found")
    return bits

def _excluded(settings: Settings, root: Root, parts: list[str]) -> bool:
    return any(tuple(parts[:len(prefix)]) == prefix for prefix in settings.exclusions[root.name])

def _open_path(settings: Settings, virtual: str, *, directory=False):
    prefix, remainder = virtual.split("/", 1) if "/" in virtual else (virtual, "")
    root = settings.roots.get(prefix)
    if root is None: raise ViewerError(404, "not found")
    parts = _parts(remainder)
    if _excluded(settings, root, parts): raise ViewerError(404, "not found")
    current = os.dup(root.fd)
    try:
        for index, part in enumerate(parts):
            flags = os.O_RDONLY | os.O_NOFOLLOW | (os.O_DIRECTORY if index < len(parts)-1 or directory else 0)
            try: nxt = os.open(part, flags, dir_fd=current)
            except FileNotFoundError: raise ViewerError(404, "not found")
            except PermissionError: raise ViewerError(403, "permission denied")
            except OSError: raise ViewerError(404, "not found")
            os.close(current); current = nxt
        info = os.fstat(current)
        if directory and not stat.S_ISDIR(info.st_mode): raise ViewerError(404, "not found")
        if not directory and not stat.S_ISREG(info.st_mode): raise ViewerError(404, "not found")
        return root, parts, current
    except Exception:
        try: os.close(current)
        except OSError: pass
        raise

def _virtual(root, parts): return "/".join([root.name, *parts])
def _kind(name, is_dir):
    if is_dir: return "directory"
    ext = Path(name).suffix.casefold()
    if ext in RASTER_EXTENSIONS: return "image"
    if ext == ".pdf": return "pdf"
    if ext in {".html", ".htm"}: return "html"
    if ext in {".md", ".markdown"}: return "markdown"
    if ext in TEXT_EXTENSIONS: return "text"
    return "download"

def _headers(response):
    response.headers.update({"X-Content-Type-Options":"nosniff", "Referrer-Policy":"no-referrer", "Cache-Control":"no-store"}); return response
def _safe_attachment(name):
    clean = name.replace("\r", "").replace("\n", "").replace('"', "'") or "download"
    return f'attachment; filename="{clean.encode("ascii", "replace").decode("ascii")}"; filename*=UTF-8\'\'{quote(clean, safe="")}'
def _read_limited(fd, limit):
    if os.fstat(fd).st_size > limit: raise ViewerError(413, "file exceeds the configured size limit")
    os.lseek(fd, 0, os.SEEK_SET); data = os.read(fd, limit + 1)
    if len(data) > limit: raise ViewerError(413, "file exceeds the configured size limit")
    return data
def _safe_url(root, parts): return "/" + "/".join(quote(p, safe="") for p in [root.name, *parts])

def _mode(request: Request):
    values = {}
    for name in ("direct", "raw"):
        raw = request.query_params.getlist(name)
        if len(raw) > 1: raise ViewerError(400, f"duplicate {name} flag")
        if raw:
            value = raw[0].lower()
            if value in ("", "1", "true"): values[name] = True
            elif value in ("0", "false"): values[name] = False
            else: raise ViewerError(400, f"invalid {name} flag")
        else: values[name] = False
    return values

def _raw_response(settings, virtual_path, request):
    root, parts, fd = _open_path(settings, virtual_path)
    try:
        data = _read_limited(fd, settings.max_bytes)
        name = parts[-1]; kind = _kind(name, False); head = request.method == "HEAD"
        if kind == "html" and not settings.serve_html: raise ViewerError(404, "not found")
        if kind in ("markdown", "text", "html"):
            data.decode("utf-8")
            return Response(content=None if head else data, media_type="text/plain", headers={"Content-Disposition": "inline"})
        return Response(content=None if head else data, media_type="application/octet-stream", headers={"Content-Disposition": _safe_attachment(name)})
    except UnicodeDecodeError as exc:
        raise ViewerError(400, "file is not valid UTF-8") from exc
    finally:
        os.close(fd)

def _markdown(text, root, parts):
    md = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable("table").use(tasklists_plugin)
    rendered = md.render(text)
    try:
        import bleach
        rendered = bleach.clean(rendered, tags={"p","br","hr","h1","h2","h3","h4","h5","h6","strong","em","del","blockquote","pre","code","ol","ul","li","table","thead","tbody","tr","th","td","a","input"}, attributes={"a":["href","title","rel"], "code":["class"], "input":["type","disabled","checked"]}, protocols={"http","https","mailto"}, strip=True)
    except ImportError: rendered = html.escape(rendered)
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(rendered, "html.parser"); base = parts[:-1]
        for anchor in soup.find_all("a"):
            href = anchor.get("href", "")
            if href.startswith(("http://", "https://", "mailto:", "#")):
                if href.startswith(("http://", "https://")): anchor["rel"] = "noopener noreferrer"
                continue
            target = [x for x in (base + href.split("#", 1)[0].split("/")) if x]
            if any(x in (".", "..") for x in target) or not target: anchor.decompose(); continue
            anchor["href"] = _safe_url(root, target) + (("#" + href.split("#",1)[1]) if "#" in href else "")
        return str(soup)
    except ImportError: return rendered

def create_app(settings: Settings | None = None):
    settings = settings or _load_settings(); app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None); app.state.settings = settings
    @app.middleware("http")
    async def security(request, call_next):
        try: response = await call_next(request)
        except ViewerError as exc: response = JSONResponse({"detail": exc.detail}, status_code=exc.status)
        return _headers(response)
    @app.get("/healthz")
    async def healthz(): return {"status":"ok", "roots": sorted(settings.roots)}
    @app.get("/api/whoami")
    async def whoami(request: Request): return {"email":request.headers.get("x-forwarded-email"), "user":request.headers.get("x-forwarded-user"), "roots":[{"name":r.name,"label":r.label} for r in settings.roots.values()]}
    @app.get("/api/list/{virtual_path:path}")
    async def list_dir(virtual_path: str):
        root, parts, fd = _open_path(settings, virtual_path, directory=True)
        try:
            entries=[]
            with os.scandir(fd) as scan:
                for entry in scan:
                    if _deny_name(entry.name): continue
                    child=parts+[entry.name]
                    if _excluded(settings, root, child): continue
                    try: info=entry.stat(follow_symlinks=False)
                    except OSError: continue
                    if entry.is_symlink() or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)): continue
                    entries.append({"name":entry.name,"url":_safe_url(root,child),"kind":_kind(entry.name,stat.S_ISDIR(info.st_mode)),"size":info.st_size if stat.S_ISREG(info.st_mode) else None,"modified":info.st_mtime})
            entries.sort(key=lambda x:(x["kind"]!="directory",x["name"].casefold(),x["name"])); truncated=len(entries)>settings.max_entries
            return {"path":_virtual(root,parts),"entries":entries[:settings.max_entries],"truncated":truncated}
        finally: os.close(fd)
    @app.api_route("/api/download/{virtual_path:path}", methods=["GET","HEAD"])
    @app.api_route("/api/file/{virtual_path:path}", methods=["GET","HEAD"])
    async def file_api(request: Request, virtual_path: str):
        mode = _mode(request)
        is_download=request.url.path.startswith("/api/download/")
        if mode["raw"] and not is_download: return _headers(_raw_response(settings, virtual_path, request))
        root,parts,fd=_open_path(settings,virtual_path)
        try:
            data=_read_limited(fd,settings.max_bytes); name=parts[-1]; kind=_kind(name,False); head=request.method=="HEAD"
            if is_download or kind=="download" or Path(name).suffix.casefold() in {".svg",".xml"}: response=Response(content=None if head else data,media_type="application/octet-stream",headers={"Content-Disposition":_safe_attachment(name)})
            elif kind=="image": response=Response(content=None if head else data,media_type=mimetypes.guess_type(name)[0] or "application/octet-stream")
            elif kind=="pdf": response=Response(content=None if head else data,media_type="application/pdf")
            elif kind=="html":
                if not settings.serve_html: raise ViewerError(404,"not found")
                response=Response(content=None if head else data,media_type="text/html",headers={"Content-Security-Policy":"default-src 'none'; script-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox"})
            elif kind=="markdown": response=HTMLResponse(content=None if head else _markdown(data.decode("utf-8"),root,parts), headers={"X-Viewer-Kind":"markdown", "Content-Security-Policy":"default-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox"})
            else: response=Response(content=None if head else data.decode("utf-8"),media_type="text/plain")
            return _headers(response)
        except UnicodeDecodeError as exc: raise ViewerError(400,"file is not valid UTF-8") from exc
        finally: os.close(fd)
    @app.get("/static/{asset:path}")
    async def static_asset(asset: str):
        if not asset or any(p in (".","..") for p in asset.split("/")): raise ViewerError(404,"not found")
        path=(settings.static_dir/asset).resolve()
        try: path.relative_to(settings.static_dir.resolve())
        except ValueError: raise ViewerError(404,"not found")
        if not path.is_file() or path.is_symlink(): raise ViewerError(404,"not found")
        return _headers(FileResponse(path))
    @app.get("/{virtual_path:path}")
    async def shell(request: Request, virtual_path: str):
        mode = _mode(request)
        if virtual_path and virtual_path.split("/",1)[0] not in settings.roots: raise ViewerError(404,"not found")
        if virtual_path:
            is_directory = True
            try:
                _,_,fd=_open_path(settings,virtual_path,directory=True)
            except ViewerError as exc:
                if exc.status != 404: raise
                is_directory = False
                _,_,fd=_open_path(settings,virtual_path)
            os.close(fd)
            if is_directory and (mode["direct"] or mode["raw"]): raise ViewerError(400, "viewer mode requires a file")
            if mode["raw"]: return _headers(_raw_response(settings, virtual_path, request))
        return _headers(FileResponse(settings.static_dir/"index.html"))
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc): return _headers(JSONResponse({"detail":"not found"}, status_code=exc.status_code))
    return app

app = create_app() if os.getenv("FILES_VIEWER_EAGER_APP")=="1" else None
