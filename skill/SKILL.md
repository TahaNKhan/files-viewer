---
name: files-viewer-links
description: Create safe direct or raw Files Viewer links for local files under the configured projects and hermes roots. Use when Hermes needs to cite, open, or share a local file through Files Viewer.
metadata:
  short-description: Link Hermes to local files safely
---

# Files Viewer links

Use this skill when Hermes needs to point a person to a local file through the
Files Viewer. The viewer is read-only and authenticated; a link does not grant
access to a file the user could not already browse.

## URL construction

The public viewer base is `https://files.mm.khome.dev`. Build links from the
virtual root and relative path, never from a raw host filesystem path:

```text
https://files.mm.khome.dev/projects/<encoded-relative-path>
https://files.mm.khome.dev/hermes/<encoded-relative-path>
```

Use `?direct` when the recipient should see only file content without the Files
navigation shell. Use `?raw` when the recipient needs original UTF-8 source
without Markdown or HTML formatting. Preserve an existing fragment after the
query string.

Examples:

```text
https://files.mm.khome.dev/projects/my-app/README.md?direct
https://files.mm.khome.dev/hermes/notes/today.md?raw
```

URL-encode each path segment separately. Keep `/` between segments. Do not put a
whole filesystem path into a query parameter or concatenate an untrusted path
into the URL.

## Root mapping

The deployment maps:

- `/home/taha/projects` → virtual root `projects`
- `/home/taha/.hermes` → virtual root `hermes`

If a requested path is outside those roots, do not manufacture a link. Ask for a
valid viewer-relative path or explain that it cannot be linked through this
service.

## Access and safety checks

Before creating a link, preserve the requested path and check that it:

- is a regular file beneath `projects` or `hermes`;
- contains no `..`, backslash, NUL, or traversal component;
- does not expose dotfiles, credentials, secrets, private keys,
  dependency/build directories, or an excluded subtree;
- uses the correct file name and extension.

The configured project exclusions include `file-server/.git`,
`file-server/.env`, and `files-viewer/config`. If the path is ambiguous, do not
guess between similarly named files; ask for the relative path.

Do not use `/api/download` when the user asked to view a file. Do not claim that
`?raw` formats or prettifies content: it returns original UTF-8 bytes as plain
text for text-like files. Binary files remain downloads.

## Response style

When the user asks for a link, provide the clickable URL and a short label with
the virtual path. If several files are requested, provide one link per file and
keep the order from the request. Mention `direct` or `raw` only when it explains
the chosen URL.
