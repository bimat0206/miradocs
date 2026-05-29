# Changelog

## v1.1.3 - 2026-05-29

- Fixed startup-triggered updates so `./start.sh` updates in place and then re-execs the refreshed launcher in the same terminal.
- Kept in-app `/api/update` on the detached restart path used by the running application.

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
