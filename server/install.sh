#!/bin/bash
#
# Sketchmaker installer: stands up a working HTTPS site from a bare Ubuntu server.
#
#   sudo bash install.sh
#
# Target: a fresh Ubuntu LTS server, with the domain's DNS already pointing at it. After a
# failed run, fix the cause and run it again: the secrets in backend/.env and the database
# are kept. Once the app is running, use update.sh instead. Shared steps live in
# server/common.sh, which update.sh also uses, so both converge on the same state.
#
# Overrides (environment): SKETCHMAKER_REPO_URL, SKETCHMAKER_BRANCH.

set -Eeuo pipefail
umask 022

REPO_URL="${SKETCHMAKER_REPO_URL:-https://github.com/marketcalls/sketchmaker}"
REPO_BRANCH="${SKETCHMAKER_BRANCH:-main}"
APP_ROOT="/var/www/sketchmaker"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

on_error() {
    printf '%b[ERROR]%b install.sh stopped at line %s (exit %s). Fix the cause and re-run; finished steps are repeated safely.\n' \
        "$RED" "$NC" "$1" "$2" >&2
}
trap 'on_error "$LINENO" "$?"' ERR

ensure_account() {
    if (cd "$SM_BACKEND_DIR" && runuser -u www-data -- env HOME="$SM_DATA_DIR" .venv/bin/python -c \
        'import sys; from app.database import SessionLocal; from app.models.user import User; db = SessionLocal(); sys.exit(0 if db.query(User.id).first() else 1)') 2>/dev/null; then
        sm_ok "An account already exists"
        return 0
    fi
    local attempt
    printf '\nChoose the login your team will use. Password: at least 12 characters.\n'
    for attempt in 1 2 3; do
        if "$SM_CLI" create-account </dev/tty; then
            return 0
        fi
        printf 'Please try again (attempt %s of 3).\n' "$attempt"
    done
    sm_warn "No account was created. Create it before anyone can sign in: sudo sketchmaker create-account"
    return 0
}

main() {
    local server_name admin_email branch

    if [ "$EUID" -ne 0 ]; then
        printf '%bPlease run as root (sudo bash install.sh)%b\n' "$RED" "$NC"
        exit 1
    fi

    printf '%bSketchmaker installer%b\n\n' "$BLUE" "$NC"

    while true; do
        printf '%bDomain name for this site (its DNS must already point at this server):%b\n' "$GREEN" "$NC"
        read -r -p "Domain (e.g., sketch.example.com): " server_name
        if [[ "$server_name" =~ ^([a-zA-Z0-9]([-a-zA-Z0-9]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$ ]]; then
            break
        fi
        printf '%bThat is not a valid domain name%b\n' "$RED" "$NC"
    done

    while true; do
        printf '%bEmail for Let'"'"'s Encrypt certificate notices:%b\n' "$GREEN" "$NC"
        read -r -p "Email: " admin_email
        if [[ "$admin_email" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
            break
        fi
        printf '%bThat is not a valid email address%b\n' "$RED" "$NC"
    done

    # ------------------------------------------------------------------
    # Repository (needed first: common.sh lives in it)
    # ------------------------------------------------------------------
    printf '\n%b== Repository ==%b\n' "$BLUE" "$NC"
    DEBIAN_FRONTEND=noninteractive apt-get update -qq >/dev/null
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ca-certificates curl git >/dev/null
    mkdir -p "$APP_ROOT"
    if [ -f "$APP_ROOT/backend/.env" ] && grep -qE '^DATABASE_URL=' "$APP_ROOT/backend/.env"; then
        printf '%b%s holds an older multi-user Sketchmaker (its .env has DATABASE_URL). Use a fresh server: this installer would replace it.%b\n' "$RED" "$APP_ROOT" "$NC"
        exit 1
    fi
    if [ -d "$APP_ROOT/.git" ]; then
        # It would upgrade the code and database under a running app, with no way back.
        if systemctl is-active --quiet sketchmaker 2>/dev/null; then
            printf '%bSketchmaker is already running here. To update it, run: sudo bash %s/server/update.sh%b\n' "$RED" "$APP_ROOT" "$NC"
            exit 1
        fi
        git config --global --add safe.directory "$APP_ROOT"
        branch="$(git -C "$APP_ROOT" rev-parse --abbrev-ref HEAD)"
        git -C "$APP_ROOT" pull --ff-only origin "$branch"
    elif [ -z "$(ls -A "$APP_ROOT")" ]; then
        git clone --branch "$REPO_BRANCH" "$REPO_URL" "$APP_ROOT"
    else
        printf '%b%s exists, is not empty and is not a git checkout; move it aside and re-run%b\n' "$RED" "$APP_ROOT" "$NC"
        exit 1
    fi

    # shellcheck source=server/common.sh
    source "$APP_ROOT/server/common.sh"
    SM_APT_UPDATED=1  # apt-get update already ran above

    sm_conf_set SERVER_NAMES "$(sm_server_names_for "$server_name")"
    sm_conf_set ADMIN_EMAIL "$admin_email"

    sm_step "System packages"
    sm_check_os_support
    if ! sm_apt_install nginx ssl-cert certbot ffmpeg ufw fail2ban unattended-upgrades; then
        sm_err "Package installation failed; see the apt output above"
        exit 1
    fi
    sm_distrust_emsign_ecc_g3
    sm_ok "System packages installed"

    # SSH stays reachable: its ports are allowed before the firewall is enabled.
    sm_step "Host hardening"
    sm_ensure_firewall
    sm_ensure_fail2ban
    sm_ensure_unattended_upgrades

    sm_step "Backend"
    sm_ensure_uv
    sm_ensure_runtime_dirs
    sm_ensure_venv
    sm_sync_python_deps
    sm_compile_app
    sm_check_malicious_packages
    sm_ensure_env_file
    sm_install_cli

    sm_step "Frontend"
    sm_ensure_node
    sm_build_frontend
    sm_swap_frontend

    sm_step "Permissions"
    sm_normalise_permissions
    sm_secure_env_file

    sm_step "Database and account"
    sm_migrate_db
    # In the terminal and before the site goes live, so nobody else can reach it first.
    # The web setup page is switched off on a public site for the same reason.
    ensure_account

    sm_step "Services"
    sm_install_units
    sm_start_service

    # ACME-only site first, then the full site once the certificate exists.
    sm_step "nginx and TLS"
    sm_install_nginx_site || true
    if sm_ensure_certificate; then
        sm_install_nginx_site || true
    fi
    sm_ensure_cert_renewal

    sm_step "Checks"
    sm_check_cloudflare_ranges
    sm_check_reboot_required
    sm_ssh_recommendations

    printf '\n%bInstallation finished.%b\n\n' "$GREEN" "$NC"
    printf 'Site: %bhttps://%s%b\n\n' "$BLUE" "$server_name" "$NC"
    printf 'Next steps:\n'
    printf '  1. Sign in, then add your provider keys under Settings > API keys.\n'
    printf '  2. Set spending limits with fal and your language model providers.\n\n'
    printf 'Useful commands:\n'
    printf '  sudo bash %s/server/update.sh       update to the latest version\n' "$SM_APP_ROOT"
    printf '  sudo sketchmaker reset-password           change the password\n'
    printf '  journalctl -u %s -f              follow the logs\n\n' "$SM_SERVICE_NAME"
    printf 'Security tests:\n'
    printf '  https://www.ssllabs.com/ssltest/analyze.html?d=%s\n' "$server_name"
    printf '  https://securityheaders.com/?q=https://%s\n' "$server_name"

    sm_print_warnings
}

main "$@"
exit 0
