# Workspace conventions

- Use this repository root as the working directory for development, testing and packaging.
- Compatibility links are aliases of this workspace, not separate checkouts or development roots.

- This is the active workspace for Codex Connect. Edit `src/`; do not resume development in the previous projectless directory or in extracted release bundles.
- The approved visual foundation is `design/CodexConnect-v0.3-design.html` (historical layout). Current behavior is documented in `design/beginner-flow-spec.md` and `design/CodexConnect-0.10.4-preview.html`; use `src/desktop_ui.py` as the implementation authority. Do not restore obsolete controls from older mockups. Preserve the Windows and macOS standalone delivery requirement: end users must not need to install Python.
- `tools/windows/` and `tools/macos/` are the current build and verification entry points. Resolve paths relative to the workspace. Keep exactly four end-user files per version in `release/CodexConnect-<version>/` (Windows EXE, two macOS DMGs and a standalone PDF manual); keep source archives and checksums in `work/build-artifacts/<version>/`. Embed `src/assets/manual.pdf` in the Windows EXE and include it in both Mac disk images. Intermediate Mac ZIPs belong in `work/build-artifacts/<version>/mac-bundles/`, not release. Keep installation packages in `release/` and intermediate analysis in `work/`.
- `work/history/` contains archived snapshots and one-time transformation scripts, not executable build instructions.
- Use isolated fixture config files for testing. Do not read or change the user's actual Codex configuration or send real API requests without task authorization.
- Preserve unrelated TOML fields, comments, backups, concurrency checks and credential redaction. A successful text API response does not prove streaming or tool-call support.
- After relevant UI changes run `tools/windows/check_redesign.py` and `check_v3_states.py`. Run the configuration core tests for configuration changes. Check the standalone executable when rebuilding it.
- Report Windows runtime checks and macOS static package checks separately. No Mac runtime, signing or notarization evidence is currently available.
- The old workspace is retained as rollback material; do not delete it as routine cleanup.
