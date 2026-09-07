# Single-file viewer and URL modes

Status: implemented; this document records the shipped behavior and validation plan.

Opening `/projects/readme.md` should replace the currently displayed file. Opening
`/projects/readme.md?direct` should show only the rendered document. Opening
`/projects/readme.md?raw` should show the original Markdown source.

## Findings from the current code

- `static/app.js`, `load()`: hides `#viewer` and clears the directory listing,
  but leaves the viewer's children in place.
- `static/app.js`, `showFile()`: appends a title and content for every file
  without replacing the previous children. This explains the reported accumulation.
- Both functions check `state.request` after `fetch()`, but some body reads
  (`r.json()` and `r.text()`) happen afterward without another check. A stale
  response can therefore commit content after a newer navigation.
- Successful file rendering does not clear the loading message.
- Navigation passes only `location.pathname` into `load()`. Query flags are
  currently ignored, including during Back/Forward navigation.
- `app/main.py`, `file_api()`: converts Markdown into sanitized HTML. Raw source
  cannot be recovered reliably by removing formatting in the frontend.
- `tests/test_app.py` covers a few backend cases; it has no browser coverage for
  navigation or rendering. These findings are from source inspection, not a live
  browser reproduction.

## Proposed URL contract

Flags are URL query parameters on existing file URLs. Accept a bare flag,
`=1`, or `=true` as enabled; accept `=0` or `=false` as disabled. Names and values
are case-sensitive. Reject other values and duplicate mode parameters with a
clear 400 error so frontend and backend do not interpret them differently.

| URL | Result |
| --- | --- |
| `/projects/readme.md` | Normal viewer UI, with exactly one rendered file |
| `/projects/readme.md?direct` | Rendered file only |
| `/projects/readme.md?raw` | Original source, without viewer UI |
| `/projects/readme.md?direct&raw` | Raw takes precedence |
| `/projects/readme.md?direct=0&raw=false` | Normal viewer |

The proposed meaning of `raw` is a draft assumption: return the original file
without the viewer shell. If raw source should instead appear inside the normal
viewer, that changes the routing and presentation design below.

Enabled modes require a file. Root and directory URLs with an enabled mode return
a concise 400 response rather than showing a listing. Missing or denied paths
retain their existing access errors. Unrelated query parameters remain untouched.

## Fix single-file rendering

Reuse `state.request` as the navigation generation. At navigation start, clear
the viewer with `replaceChildren()`, hide it, reset listing/status state, and
dispose of any resources owned by the previous render.

Build each next render in a detached fragment. Check the generation after every
await that precedes a DOM update, including body reads. Only the current request
may replace the viewer or directory listing, reveal content, or update status.
Clear the loading message when rendering succeeds. A failed navigation must not
reveal the previous file. Apply the same rules in normal and direct modes.

## Direct mode

Reuse the existing file renderers and sanitized Markdown response. Resolve the
mode from the full URL on initial load, clicks, and `popstate`.

Before the shell becomes visible, select the correct layout to prevent a flash
of navigation. Direct mode removes the header, identity, logout, sidebar,
breadcrumbs, directory listing, generated filename heading, and surrounding
application spacing. Hidden controls must also be absent from keyboard focus
and the accessibility tree. Content headings written inside the file remain.

| File type | Direct presentation |
| --- | --- |
| Markdown | Sanitized rendered document, with readable document styles |
| HTML | Existing sandboxed iframe, filling the viewport without viewer borders |
| Text/code | Plain text with whitespace preserved; no generated title or card |
| Raster image | Image alone, scaled to fit available width |
| PDF | Embedded browser PDF viewer filling the viewport, replacing the current “Open PDF” link |
| Unsupported binary | Original-file download; no invented renderer |

Browser-provided PDF controls may appear; they are not application UI. If PDF
embedding is unavailable, show a minimal file-opening fallback. Loading and
error states may contain a short status message, cleared on successful rendering.

For ordinary in-app document links without an explicit mode, carry forward
`direct` when navigating to another file. Explicit mode parameters override that
default. Preserve fragments, other query parameters, and native modified-click
behavior. External links are unchanged. Links to directories open the normal
listing without inherited `direct`. Link generation should account for this
before clicks, so opening a link in a new tab behaves consistently.

## Raw mode

Reuse `_open_path()`, `_read_limited()`, `_headers()`, and `_safe_attachment()`.
Factor file response selection into a shared helper used by `file_api()` and
the public file route. Dispatch raw public URLs before returning `index.html`;
also support `/api/file/{path}?raw`. Keep `/api/download/{path}` as an attachment
endpoint regardless of mode parameters.

For recognized text files, including Markdown, HTML, XML, and code, return the
original bytes as `text/plain; charset=utf-8`. Do not render Markdown, parse
HTML, syntax-highlight, pretty-print JSON, normalize whitespace, or add markup.
Retain the existing invalid-UTF-8 rejection policy for inline text rather than
silently replacing characters. Return images, PDFs, and other binary files
unchanged as attachments: binary data has no useful unformatted text view.

Preserve the existing authentication boundary, path restrictions, file-size
limit, `nosniff`, and cache policy. Keep the current `SERVE_HTML=0` restriction
for HTML files in every mode. Raw HTML must never execute. Direct HTML continues
to use the current CSP and iframe sandbox.

Raw links use normal browser navigation rather than SPA interception. Refresh,
copied URLs, and Back/Forward must select the same representation. Define GET
and HEAD consistently for raw public/API responses, with HEAD returning the
same representation headers and no body.

## Implementation sequence

1. Fix clearing and stale-response handling in `static/app.js`. Add meaningful
   browser regression coverage for sequential and delayed navigation.
2. Add shared flag parsing and raw response selection in `app/main.py`, with
   backend tests in `tests/test_app.py` for source bytes, mode precedence, errors,
   and response headers.
3. Add direct layout and full-URL navigation handling in `static/app.js`,
   `static/index.html`, and `static/styles.css`. Reuse existing rendering paths;
   add PDF embedding and mode-aware document links.
4. Add browser coverage for both modes and document the supported URL syntax,
   type-specific behavior, and limitations in `README.md`.

Use a lightweight browser test harness against temporary fixture roots; choose
the runner during implementation since this repository has no frontend test
toolchain. No production content is needed for validation.

## Acceptance checks

- Open file A, then B, then A: exactly one file and at most one generated title
  are present. Directory navigation and failed loads leave no old file visible.
- Delay A's response body, navigate to B, then release A: only B is displayed.
  Repeat with a delayed directory JSON body and verify loading status clears.
- Direct mode renders Markdown, HTML, text, images, and PDF as specified on
  desktop and mobile, with no application chrome or initial chrome flash.
- Raw Markdown/HTML/JSON matches the original bytes, including indentation and
  line endings; HTML remains inert. Binary responses download unchanged.
- Bare flags, explicit booleans, conflicting flags, duplicate/invalid values,
  refresh, copied URLs, and Back/Forward follow the contract.
- Document links preserve mode intent, query parameters, fragments, and new-tab
  behavior; directory links can return to normal browsing.
- Missing files, directories, denied paths, oversized files, invalid UTF-8,
  and disabled HTML produce the specified errors without exposing stale content.
- Existing backend checks pass; direct rendering retains Markdown sanitization
  and HTML isolation, and raw GET/HEAD response behavior is covered.
