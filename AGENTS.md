# Contributor guidance

## Scope

This repository is a read-only, authenticated file viewer. Keep changes focused
on safe browsing, preview behavior, deployment, and documentation. Do not add
write, delete, upload, shell-execution, or arbitrary proxy capabilities.

## Architecture

- `app/main.py` owns path validation, file-descriptor traversal, access
  exclusions, file classification, rendering, and response security headers.
- `static/app.js` owns client navigation and preview composition. A navigation
  request must replace previous viewer content and must not allow an older
  asynchronous response to commit after a newer request.
- `static/index.html` and `static/styles.css` define the shell and direct mode.
- Compose mounts `/home/taha/projects` as `projects` and `/home/taha/.hermes` as
  `hermes`, both read-only.

## Safety invariants

Preserve these invariants when changing the backend:

- Open paths beneath configured roots with `O_NOFOLLOW`; reject traversal,
  symlinks, hidden names, denied names, excluded subtrees, and non-regular files.
- Keep file-size and listing limits enforced server-side.
- Keep authentication delegated to OAuth2 Proxy; do not add unauthenticated
  file routes.
- Keep HTML sandbox/CSP behavior and Markdown sanitization intact.
- Do not expose raw bytes through a route that bypasses path and access checks.
  `?raw` changes representation, not authorization.
- Keep `/api/download/...` attachment semantics even if a query includes `raw`.

## Development checks

```bash
PYTHONPATH=. .venv/bin/pytest -q
python -m py_compile app/main.py
git diff --check
```

For container changes, rebuild rather than only restarting an old image:

```bash
docker compose up -d --build
docker compose ps
```

Add tests for every new route or representation. Include denied paths, traversal,
oversized files, invalid UTF-8, HEAD behavior, and stale frontend navigation
where relevant.

## Documentation and links

Use [`skill/SKILL.md`](skill/SKILL.md) when a task asks for a Hermes-facing link
to a local file. Use virtual-root URLs, URL-encode each path segment, and never
turn an arbitrary filesystem path into a link without checking that it is under
one of the configured roots and is not excluded.
