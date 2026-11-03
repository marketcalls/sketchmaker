#!/bin/bash
#
# Restore the database from a backup file, on a server set up by install.sh.
#
#   sudo bash /var/www/sketchmaker/server/restore.sh /var/lib/sketchmaker/backups/sketchmaker-YYYYmmdd-HHMMSS.db
#
# The current database is copied first, and comes back if the backup turns out to be
# unusable. An older backup is upgraded to the current schema by the normal migration.
# It needs the backend/.env the backup was made with to read the stored provider keys.

set -Eeuo pipefail
umask 022

APP_DIR="/var/www/sketchmaker"

main() {
    local backup="${1:-}" check answer safety
    if [ "$EUID" -ne 0 ]; then
        printf 'Please run as root (sudo bash restore.sh <backup file>)\n' >&2
        exit 1
    fi
    if [ -z "$backup" ] || [ ! -f "$backup" ]; then
        printf 'Usage: sudo bash restore.sh <backup file>\nBackups are in /var/lib/sketchmaker/backups and /var/backups/sketchmaker/db.\n' >&2
        exit 1
    fi

    # shellcheck source=server/common.sh
    source "$APP_DIR/server/common.sh"

    check="$("$SM_BACKEND_DIR/.venv/bin/python" -I -c '
import sqlite3, sys
conn = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
print(conn.execute("PRAGMA integrity_check").fetchone()[0])
' "$backup" 2>/dev/null || true)"
    if [ "$check" != "ok" ]; then
        sm_err "$backup is not a healthy SQLite database. Nothing was changed."
        exit 1
    fi

    printf 'This replaces the current database with %s.\n' "$backup"
    read -r -p "Type RESTORE to continue: " answer
    if [ "$answer" != "RESTORE" ]; then
        printf 'Nothing changed.\n'
        exit 1
    fi

    systemctl stop "$SM_SERVICE_NAME"
    # Whatever stops this script from here, the app does not stay down.
    trap 'systemctl start "$SM_SERVICE_NAME" || true' EXIT
    sm_snapshot_db
    safety="$SM_DB_SNAPSHOT"

    if rm -f "$SM_DB-wal" "$SM_DB-shm" \
        && install -m 0600 -o www-data -g www-data "$backup" "$SM_DB" \
        && sm_migrate_db && sm_start_service; then
        trap - EXIT
        sm_ok "Restored from $backup. The previous database is in ${safety:-(there was none)}"
        return 0
    fi

    sm_err "The restored database did not come up, so the previous one is going back."
    systemctl stop "$SM_SERVICE_NAME" || true
    if [ -n "$safety" ]; then
        sm_restore_snapshot "$safety" || sm_err "The previous database could not be put back. It is in $safety"
    fi
    trap - EXIT
    sm_start_service || true
    exit 1
}

main "$@"
exit 0
