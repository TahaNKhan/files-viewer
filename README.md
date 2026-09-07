# Files Viewer

Files Viewer is an authenticated, read-only web application for browsing the
local virtual roots `projects` and `hermes`. It serves directory listings and
safe previews through FastAPI, with OAuth2 Proxy providing the external login
boundary.

## Runtime

The production-shaped local stack is Docker Compose:

- `files-viewer` runs FastAPI/Uvicorn on internal port `3030`.
- `oauth2-proxy` exposes `127.0.0.1:4181` and forwards authenticated requests.
- `projects` maps to `/home/taha/projects`; `hermes` maps to `/home/taha/.hermes`.
- Source mounts are read-only. The viewer drops capabilities and uses a
  read-only filesystem with a temporary `/tmp`.

Copy [`.env.example`](.env.example) to `.env`, set the host UID/GID, OIDC issuer
and redirect URLs, and OAuth credentials, then start or rebuild the stack with:

```bash
docker compose up -d --build
docker compose ps
```

The populated `.env` contains secrets and is excluded from version control.

## URL behavior

Normal paths show the application shell and either a directory listing or one
file preview:

```text
/projects/path/to/file.md
/hermes/path/to/file.txt
```

Use `?direct` to show only rendered file content, without the Files header,
sidebar, breadcrumbs, filename heading, or listing. Use `?raw` to return the
original UTF-8 source without Markdown rendering or HTML formatting:

```text
/projects/path/to/file.md?direct
/projects/path/to/file.md?raw
```

Raw mode is also available on `/api/file/...` URLs. Text-like files are returned
as `text/plain`; binary files remain downloads. Mode flags require a file, and
invalid or duplicate values return `400`. See [`skill/SKILL.md`](skill/SKILL.md)
for Hermes link construction.

Supported previews include sanitized GitHub-flavored Markdown styled with the
vendored `github-markdown-css` library, sandboxed HTML, plain text/code, images,
and PDFs. Unsupported binaries use the download endpoint.

## Security model

The backend opens files relative to directory file descriptors with `O_NOFOLLOW`,
rejects traversal, symlinks, dotfiles, common dependency/build directories,
credential-like names, private-key extensions, and non-regular files. Additional
subtrees are configured in [`config/access.json`](config/access.json).

Responses use `nosniff`, no-referrer, and no-store headers. HTML previews use a
restrictive CSP and frontend sandbox. Markdown is rendered with raw HTML
disabled, sanitized, and given safe relative-link handling. Reads are limited by
`MAX_FILE_BYTES`; listings are limited by `MAX_LIST_ENTRIES`.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q
python -m py_compile app/main.py
git diff --check
```

Tests use temporary fixture roots and an ASGI client, so they do not require
Docker or access to the real local roots.

## Repository map

| Path | Purpose |
| --- | --- |
| `app/main.py` | FastAPI routes, safe path opening, rendering, headers |
| `static/index.html` | Application shell |
| `static/app.js` | Navigation, previews, direct mode, race protection |
| `static/styles.css` | Shell, preview, and direct-mode styles |
| `config/access.json` | Per-root excluded subtrees |
| `tests/test_app.py` | Backend and URL behavior tests |
| `skill/SKILL.md` | Hermes instructions for safe local links |
| `docs/plans/` | Feature planning and implementation notes |
| `docker-compose.yml` | Container deployment |

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `SERVE_ROOTS` | `projects:/srv/projects,hermes:/srv/hermes` | Virtual root mappings |
| `STATIC_DIR` | `static` | Frontend asset directory |
| `ACCESS_CONFIG` | `config/access.json` | Exclusion configuration |
| `MAX_FILE_BYTES` | `5242880` | Maximum file read size |
| `MAX_LIST_ENTRIES` | `2000` | Maximum visible entries |
| `SERVE_HTML` | `1` | Whether HTML previews are enabled |

Keep `.env`, OAuth secrets, and source-root contents out of commits. Review
access exclusions before exposing the proxy beyond the local machine.

This project is licensed under the [MIT License](LICENSE).
