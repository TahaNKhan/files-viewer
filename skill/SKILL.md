---
name: files-viewer-links
description: Create safe direct or raw Files Viewer links for files under a deployed viewer's configured roots. Use when Hermes needs to cite, open, or share a local file through Files Viewer.
metadata:
  short-description: Link Hermes to local files safely
---

# Files Viewer links

Use this skill when Hermes needs to point a person to a local file through the
Files Viewer. The viewer is read-only and authenticated; a link does not grant
access to a file the user could not already browse.

## First-use configuration

Hermes stores the public viewer URL in `~/.config/file-viewer.json` so Telegram
requests can produce clickable links without asking the Telegram user for a
hostname. Use this configuration shape:

```json
{"base_url":"https://files.example.test"}
```

On every invocation:

1. Read `~/.config/file-viewer.json`.
2. If it is missing, invalid, or has no `base_url`, ask the operator for the
   public Files Viewer URL. Do not invent a hostname or return a fake clickable
   link.
3. Validate that the value is an absolute `http` or `https` URL, then normalize
   one trailing slash away.
4. After the operator supplies it, create `~/.config` if needed and persist the
   JSON with user-only permissions (`0700` for the directory and `0600` for the
   file). Keep the file limited to the viewer URL; never store OAuth secrets.

This is Hermes-local bootstrap configuration and is separate from the viewer
service's `.env` file. Once configured, use `base_url` for future Telegram links.

The virtual root names and route prefixes come from the deployment's
`SERVE_ROOTS` configuration or the authenticated viewer's `/api/roots` response.
After the URL is configured, call `<base_url>/api/roots` when available; it
reports route names and container-side source paths without exposing host bind
directories. Do not assume that roots are called `projects` or `hermes`, and do
not infer filesystem mount paths from a root name. A deployment may expose any
set of named roots.

Build links from the configured base URL, virtual root, and relative path, never
from a raw host filesystem path:

```text
<viewer-base>/<virtual-root>/<encoded-relative-path>
```

Use `?direct` when the recipient should see only file content without the Files
navigation shell. Use `?raw` when the recipient needs original UTF-8 source
without Markdown or HTML formatting. Preserve an existing fragment after the
query string.

For example, if an operator configures the base URL as
`https://files.example.test` and exposes a root named `workspace`:

```text
https://files.example.test/workspace/docs/README.md?direct
https://files.example.test/workspace/notes/today.md?raw
```

URL-encode each path segment separately. Keep `/` between segments. Do not put a
whole filesystem path into a query parameter or concatenate an untrusted path
into the URL.

If a requested path is outside the configured roots, do not manufacture a link.
Ask for a valid viewer-relative path or explain that it cannot be linked through
this service. If the user gives a host filesystem path, resolve it to a virtual
root only when the deployment mapping is known.

## Access and safety checks

Before creating a link, preserve the requested path and check that it:

- is a regular file beneath one of the configured virtual roots;
- contains no `..`, backslash, NUL, or traversal component;
- does not expose dotfiles, credentials, secrets, private keys, dependency/build
  directories, or an excluded subtree;
- uses the correct file name and extension.

Rely on the viewer's current access rules for excluded subtrees rather than
embedding a deployment's private exclusion list in this skill. If the path is
ambiguous, do not guess between similarly named files; ask for the relative path.

Do not use `/api/download` when the user asked to view a file. Do not claim that
`?raw` formats or prettifies content: it returns original UTF-8 bytes as plain
text for text-like files. Binary files remain downloads.

## Response style

When the user asks for a link, provide the clickable URL and a short label with
the virtual path. If several files are requested, provide one link per file and
keep the order from the request. Mention `direct` or `raw` only when it explains
the chosen URL.
