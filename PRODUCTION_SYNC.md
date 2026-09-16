# Production code snapshot — 2026-09-16

Source revision: `04941d6` (production), including the meal photo/history release.

This is a source-only public snapshot, not a production database backup. It includes
the latest account/roster, campus isolation, club and meal functionality. Existing
public regression tests and anonymized sample data are retained.

Excluded: production Git history, databases and SQLite sidecars, student documents,
account exports, runtime uploads, logs, virtual environments and private configuration.
Real teacher identifiers remain deployment configuration, not public source:

- `GENERAL_TEACHER_USERIDS`: comma-separated general teacher IDs.
- `BENBU_DUAL_ROLE_TEACHER_USERIDS`: comma-separated approved dual-role teacher IDs.
- `server/campus_config.json`, per-campus `clubNotifyUserIds`: notification recipients.
- `BENBU_FAMILY_XLS`, `BENBU_TEACHER_XLSX`, `BENBU_CLASS_TEACHER_XLSX`: private import paths.

Example domains/IP addresses and anonymized course-teacher names are intentional.
Do not overwrite production private settings with public examples. The deployment
workflow remains manual; pushing this snapshot does not deploy to the server.

See `MEAL_HISTORY_DEPLOYMENT.md` for the additive migration and rollback procedure.
