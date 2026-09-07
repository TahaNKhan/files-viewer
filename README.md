# files-viewer

Authenticated, read-only file viewer for the `projects` and `hermes` virtual roots.

## Local development

The application is intentionally configured by environment variables. For a local fixture server, point `SERVE_ROOTS` at two temporary directories and set `STATIC_DIR=static`, `ACCESS_CONFIG=config/access.json`.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 3030 --no-proxy-headers
```

The production Compose file runs the backend without a host port and places oauth2-proxy on the only host-facing loopback port (`127.0.0.1:4181`). The `.env` file is private runtime input and is never copied into the image.

The viewer denies dotfiles, common generated/dependency directories, credential names, private key/certificate extensions, symlinks, non-regular files, traversal components, and configured subtrees. HTML is returned with a restrictive CSP and rendered only in a sandboxed iframe; Markdown is sanitized before insertion into the application shell.

File URLs support `?direct` to render only the file content without the Files
application shell, and `?raw` to return the original UTF-8 source without
Markdown or HTML formatting. These flags also work on API file URLs; they require
a file path, and invalid or duplicate flag values are rejected.

Before deployment, set `FILE_UID=1000` and `FILE_GID=1000` (or the verified source-owner IDs), populate `config/allowed-emails.txt`, review `config/access.json`, and validate the complete checklist in the planning repository's `docs/verification.md`.
