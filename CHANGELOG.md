# Changelog

## v1.1.2 - 2026-05-29

- Fixed update-triggered restarts so `start.sh` hands service control to `update.sh` instead of treating the intentional shutdown as a crash.
- Added a short-lived update handoff marker and ignored its runtime file.
- Added regression coverage for the update handoff exit path.

## v1.1.1 - 2026-05-29

- Added startup auto-update checks in `start.sh` before API/UI launch.
- Added update recursion guard with `MIRADOCS_SKIP_START_UPDATE`.
- Updated `update.sh` restart flow so the updater owns service relaunch after pulling changes.
- Documented startup auto-update behavior and update status/log locations.
- Added shell-level regression tests for startup update, no-update, and recursion-guard paths.
