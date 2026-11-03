#!/bin/bash
#
# Sketchmaker update script: brings an existing server up to date, and undoes the whole
# update if the new version does not come up healthy.
#
#   sudo bash /var/www/sketchmaker/server/update.sh
#   sudo bash /var/www/sketchmaker/server/update.sh --rollback    undo the last update
#
# Phase 1 (this file as it is on disk now): git pull --ff-only.
# Phase 2 (the freshly pulled copy, re-executed with --after-pull): every other step, via
# the helpers in server/common.sh that install.sh also uses.
#
# The order keeps downtime short and failures safe. Everything that can fail on its own
# (dependencies, the frontend build) happens while the old version keeps serving; only
# then is the app stopped, the database copied, the schema upgraded and the new version
# started. Recoverable problems are warned about and summarised at the end.

set -Eeuo pipefail
umask 022

APP_DIR="/var/www/sketchmaker"
# The commit an update started from, until that update has finished one way or the other.
IN_PROGRESS_FILE="/etc/sketchmaker/update-in-progress"
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

on_error() {
    printf '%b[ERROR]%b update.sh stopped at line %s (exit %s). Check that the app is running: systemctl status sketchmaker\n' \
        "$RED" "$NC" "$1" "$2" >&2
}
trap 'on_error "$LINENO" "$?"' ERR

# ------------------------------------------------------------------
# Phase 1: pull
# ------------------------------------------------------------------
pull_latest() {
    local branch other
    if [ ! -d "$APP_DIR/.git" ]; then
        printf '%b%s is not a git checkout. Run install.sh first.%b\n' "$RED" "$APP_DIR" "$NC"
        exit 1
    fi
    cd "$APP_DIR"
    printf '%b== Pulling latest code ==%b\n' "$BLUE" "$NC"

    if ! git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$APP_DIR"; then
        git config --global --add safe.directory "$APP_DIR"
    fi

    other="$(git status --porcelain --untracked-files=no)"
    if [ -n "$other" ]; then
        printf '%b[ERROR]%b Tracked files were changed on this server, so the update stopped:\n%s\nCommit them upstream, or discard them with: git -C %s checkout -- .\n' \
            "$RED" "$NC" "$other" "$APP_DIR" >&2
        exit 1
    fi

    branch="$(git rev-parse --abbrev-ref HEAD)"
    if [ "$branch" = "HEAD" ]; then
        printf '%bDetached HEAD; check out the deploy branch first%b\n' "$RED" "$NC"
        exit 1
    fi
    # A crash during an earlier update leaves its starting point here. Without it, this run
    # would start from the half-applied code and treat that as the version to go back to.
    install -d -m 0700 -o root -g root "$(dirname "$IN_PROGRESS_FILE")"
    if [ -s "$IN_PROGRESS_FILE" ]; then
        PREVIOUS_COMMIT="$(cat "$IN_PROGRESS_FILE")"
        printf 'An earlier update did not finish; treating %s as the version to go back to.\n' "$PREVIOUS_COMMIT"
    else
        PREVIOUS_COMMIT="$(git rev-parse HEAD)"
        printf '%s\n' "$PREVIOUS_COMMIT" > "$IN_PROGRESS_FILE"
    fi
    git pull --ff-only origin "$branch"
    printf '%b[OK]%b Code updated (%s)\n' "$GREEN" "$NC" "$(git log -1 --format='%h %s')"
}

# ------------------------------------------------------------------
# Undo: previous code, previous frontend, database as it was before the update
# ------------------------------------------------------------------
restore_previous_code() {
    local commit="$1"
    git -C "$APP_DIR" reset --hard "$commit"
    sm_sync_python_deps || true
    sm_compile_app
    sm_normalise_permissions
    sm_secure_env_file
}

undo_update() {
    local commit="$1" snapshot="$2"
    sm_step "Undoing the update"
    systemctl stop "$SM_SERVICE_NAME" || true
    restore_previous_code "$commit"
    sm_swap_frontend_back || sm_warn "The previous frontend build could not be put back"
    if [ -n "$snapshot" ]; then
        sm_restore_snapshot "$snapshot" || sm_err "The database could not be put back from $snapshot"
    fi
    sm_install_units || true
    if sm_start_service; then
        sm_ok "The previous version is running again"
        return 0
    fi
    sm_err "The previous version did not start either. Database copy: ${snapshot:-none}. Check: journalctl -u $SM_SERVICE_NAME -n 100"
    return 1
}

manual_rollback() {
    local commit snapshot answer current
    # shellcheck source=server/common.sh
    source "$APP_DIR/server/common.sh"
    commit="$(sm_conf_get LAST_UPDATE_FROM_COMMIT)"
    snapshot="$(sm_conf_get LAST_UPDATE_SNAPSHOT)"
    if [ -z "$commit" ]; then
        sm_err "There is no update to roll back."
        exit 1
    fi
    printf 'This returns to %s and puts the database back as it was before the last update.\n' "$commit"
    printf '%bAnything saved since that update (jobs, settings, new keys) is lost; media files stay.%b\n' "$RED" "$NC"
    read -r -p "Type ROLLBACK to continue: " answer
    if [ "$answer" != "ROLLBACK" ]; then
        printf 'Nothing changed.\n'
        exit 1
    fi
    current="$(git -C "$APP_DIR" rev-parse HEAD)"
    sm_ensure_uv
    # The old frontend is built first, while the current version keeps serving, because
    # this is the step most likely to fail.
    git -C "$APP_DIR" reset --hard "$commit"
    if ! { sm_ensure_node && sm_build_frontend; }; then
        git -C "$APP_DIR" reset --hard "$current"
        sm_err "The previous frontend could not be built. Nothing was rolled back, and the app is still running."
        exit 1
    fi
    systemctl stop "$SM_SERVICE_NAME" || true
    # Whatever stops this script from here, the app does not stay down.
    trap 'systemctl start "$SM_SERVICE_NAME" || true' EXIT
    restore_previous_code "$commit"
    sm_swap_frontend
    if [ -n "$snapshot" ]; then
        sm_restore_snapshot "$snapshot"
    fi
    sm_install_units
    trap - EXIT
    sm_start_service
    sm_conf_set LAST_UPDATE_FROM_COMMIT ""
    sm_conf_set LAST_UPDATE_SNAPSHOT ""
    sm_ok "Rolled back to $commit. The next update.sh moves forward again."
}

# ------------------------------------------------------------------
# Phase 2: everything else, from the freshly pulled code
# ------------------------------------------------------------------
SM_UPDATE_FROM=""
SM_UPDATE_SNAPSHOT=""

# Any step not handled below ends up here while the update is in flight, so an unexpected
# failure undoes the update rather than leaving new code on an old database, or the app
# stopped.
on_update_error() {
    trap - ERR
    set +e
    sm_err "update.sh stopped at line $1 (exit $2), so the update is being undone."
    undo_update "$SM_UPDATE_FROM" "$SM_UPDATE_SNAPSHOT"
    rm -f "$IN_PROGRESS_FILE"
    sm_print_warnings
    exit 1
}

# For failures while the old version is still serving: it stays up, and only the code on
# disk goes back, so a later restart cannot load new code on the old schema.
abort_before_stopping() {
    trap - ERR
    set +e
    sm_err "$1"
    restore_previous_code "$SM_UPDATE_FROM"
    rm -f "$IN_PROGRESS_FILE"
    sm_print_warnings
    exit 1
}

after_pull() {
    # shellcheck source=server/common.sh
    source "$APP_DIR/server/common.sh"

    SM_UPDATE_FROM="$1"
    trap 'on_update_error "$LINENO" "$?"' ERR

    sm_step "Permissions and secrets"
    sm_normalise_permissions
    sm_ensure_runtime_dirs
    sm_install_cli
    sm_secure_env_file

    sm_step "System"
    sm_apt_update || true
    sm_check_os_support
    sm_check_reboot_required
    sm_distrust_emsign_ecc_g3
    sm_apt_install ffmpeg || sm_warn "ffmpeg could not be installed; video tools will fail"

    sm_step "Host hardening"
    sm_ensure_firewall
    sm_ensure_fail2ban
    sm_ensure_unattended_upgrades

    sm_step "Backend dependencies"
    if ! { sm_ensure_uv && sm_ensure_venv && sm_sync_python_deps; }; then
        abort_before_stopping "The dependencies could not be installed. The app is still running the previous version."
    fi
    sm_compile_app
    sm_check_malicious_packages

    sm_step "Frontend"
    if ! { sm_ensure_node && sm_build_frontend; }; then
        abort_before_stopping "The frontend could not be built. The app is still running the previous version."
    fi

    sm_step "Database"
    systemctl stop "$SM_SERVICE_NAME" || true
    sm_snapshot_db
    SM_UPDATE_SNAPSHOT="$SM_DB_SNAPSHOT"
    # migrate restores the database itself on failure. Going through the handler also puts
    # the code back and restarts the app.
    sm_migrate_db

    sm_step "Restart and verify"
    sm_swap_frontend
    sm_install_units
    sm_start_service

    # The new version is live and healthy. Nothing below is worth undoing it for.
    trap 'on_error "$LINENO" "$?"' ERR
    rm -f "$IN_PROGRESS_FILE"
    rm -rf "$SM_FRONTEND_DIR/dist.prev"
    sm_conf_set LAST_UPDATE_FROM_COMMIT "$SM_UPDATE_FROM"
    sm_conf_set LAST_UPDATE_SNAPSHOT "$SM_UPDATE_SNAPSHOT"

    sm_step "nginx and TLS"
    sm_ensure_certificate || true
    sm_install_nginx_site || true
    sm_ensure_cert_renewal
    sm_check_cloudflare_ranges

    sm_step "Checks"
    sm_ssh_recommendations

    sm_step "Dependency audit (warnings only)"
    sm_dependency_audit

    sm_step "Summary"
    printf '  App:    %s\n' "$(systemctl is-active "$SM_SERVICE_NAME" 2>/dev/null || true)"
    printf '  nginx:  %s\n' "$(systemctl is-active nginx 2>/dev/null || true)"
    printf '  Undo:   sudo bash %s/server/update.sh --rollback\n' "$SM_APP_ROOT"
    printf '  Logs:   journalctl -u %s -f\n' "$SM_SERVICE_NAME"
    sm_print_warnings
    printf '\n%bUpdate completed.%b\n' "$GREEN" "$NC"
}

main() {
    if [ "$EUID" -ne 0 ]; then
        printf '%bPlease run as root (sudo bash update.sh)%b\n' "$RED" "$NC"
        exit 1
    fi
    case "${1:-}" in
        --after-pull)
            after_pull "$2"
            return 0
            ;;
        --rollback)
            manual_rollback
            return 0
            ;;
    esac
    pull_latest
    if [ ! -f "$APP_DIR/server/common.sh" ]; then
        printf '%b[ERROR]%b %s/server/common.sh is missing after the pull\n' "$RED" "$NC" "$APP_DIR" >&2
        exit 1
    fi
    # Continue with the update.sh that was just pulled, so this run uses the newest steps.
    exec bash "$APP_DIR/server/update.sh" --after-pull "$PREVIOUS_COMMIT"
}

# Everything is inside functions and parsed before it runs, so git replacing this file
# during the pull cannot corrupt the running script.
main "$@"
exit 0
