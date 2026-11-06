# Changelog

## v2.3.4 — Persistent Windows installer wizard

- Replaces the sequence of short-lived folder-picker dialogs with one installer window that remains open through selection, progress, errors and success.
- `INSTALL.bat` starts the GUI in a separate Python window on Windows; there are still exactly two BAT files.
- Offers existing compatible AI App Server or installing a new bundled server first, with editable destinations and clear update confirmation.
- Captures installer output in the GUI and writes a per-user log under LocalAppData. Failure no longer silently closes the installation UI.
- Does not change Studio runtime behavior, installed databases, separate AI App Server instances, or update/rollback safety logic.

## v2.3.3 — Confirm before overwriting an existing Studio project

- When a chosen directory contains a recognised existing Studio installation, `INSTALL.bat` now asks Yes/No instead of failing with a generic non-empty destination error. No cancels without changes.
- Yes creates a dated backup outside Studio, replaces only release-managed application code, preserves the database/agents/users/configuration, verifies routes, and restores old code if installation fails.
- Unknown, special and unrelated folders are never overwritten. CLI automation requires an explicit `--overwrite-existing` flag.
- Still only `INSTALL.bat` and `START.bat`; AI App Server standalone installations remain unmodified.

## v2.3.2 — Start from source and safe interrupted-install recovery

- `START.bat` now detects source versus installed folders, finds or asks for the correct Studio installation, and avoids misleading virtualenv-missing errors.
- The installer remembers the selected Studio directory in a local per-user file so subsequent starts can find it. This file is never committed.
- `--resume` can finish a missing Python environment or app bootstrap without replacing user data, accounts, agent projects or existing app code.
- A copy of the Python recovery logic is included inside the installed Studio and bundled AI App Server; either can complete a missing Python environment, with no additional BAT files.
- Added tests for interrupted installs, source launcher and recorded-location safety.


## v2.3.1 — Windows route preflight correction and safe recovery

- Corrected the route verification crash when FastAPI returns `_IncludedRouter` entries without a `.path`. Router containers are handled safely, while missing Studio endpoints remain an error.
- Added `INSTALL.bat --resume` (folder picker) or `--resume "STUDIO_FOLDER"` to finish v2.3.0 installations stopped by this verification bug, without touching databases, application source, existing servers or accounts.
- Added regression tests covering nested router containers, missing routes and safe recovery of an existing installation.
- Still just two BAT files: `INSTALL.bat` and `START.bat`.


## v2.3.0 — clean two-stage portable installer

- Complete Agent Studio v2.2 source preserved, including Ollama, MCP integration, tools, SQL Server read-only support and visual editor.
- Installer checks for an installed AI App Server v1.0.4–v1.0.5, with a browseable destination. When missing, asks to install the bundled standalone AI App Server v1.0.5 first.
- Creates an independent Studio server instance with isolated framework code, accounts, SQLite database, admin dashboard and application port. No changes are made to an existing server.
- Install path can be any writable drive or folder; no fixed E: requirement. Never overwrites a non-empty destination.
- Exactly two BAT files in the GitHub source root: `INSTALL.bat`, `START.bat`. Removed old multi-file overlay and launcher workflow.
- Added first-login, desktop shortcut, automatic Windows sign-in startup, compatibility, testing and support instructions.
- Fresh-install only. In-place upgrade and Windows Service are not bundled in this release.

## v2.2 — original visual agent builder

See [v2.2](https://github.com/tuckbloor/AI-Agent-Studio) for older Studio changelog and feature history.
