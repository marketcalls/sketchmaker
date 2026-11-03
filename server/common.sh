#!/bin/bash
# shellcheck shell=bash
#
# Shared deploy helpers for server/install.sh, server/update.sh and server/restore.sh.
# Sourced, never executed.
#
# Every unit, directory, package, nginx rule and host hardening step lives here once
# and is called from both install.sh and update.sh, so a new server and an existing one
# converge on the same state. Anything new goes in here.
#
# Conventions:
#   - functions never print secrets and never call "exit"; they return non-zero and the
#     caller decides whether that is fatal
#   - every function is idempotent and safe to run on every deploy
#   - recoverable problems are reported with sm_warn and summarised at the end

if [ -n "${SM_COMMON_LOADED:-}" ]; then
    return 0
fi
SM_COMMON_LOADED=1

# ------------------------------------------------------------------
# Layout and versions
# ------------------------------------------------------------------
SM_SERVICE_NAME="sketchmaker"
SM_APP_ROOT="/var/www/sketchmaker"
SM_BACKEND_DIR="$SM_APP_ROOT/backend"
SM_FRONTEND_DIR="$SM_APP_ROOT/frontend"
SM_SERVER_DIR="$SM_APP_ROOT/server"
SM_DATA_DIR="/var/lib/sketchmaker"
SM_DB="$SM_DATA_DIR/sketchmaker.db"
SM_ENV_FILE="$SM_BACKEND_DIR/.env"
SM_CONF_DIR="/etc/sketchmaker"
SM_DEPLOY_CONF="$SM_CONF_DIR/deploy.conf"
SM_ACME_ROOT="/var/www/letsencrypt"
SM_NGINX_SITE="/etc/nginx/sites-available/sketchmaker"
SM_NGINX_SITE_LINK="/etc/nginx/sites-enabled/sketchmaker"
SM_BACKUP_ROOT="/var/backups/sketchmaker"
SM_SNAPSHOT_KEEP=10
SM_SOCKET="/run/sketchmaker/sketchmaker.sock"
SM_UNIT_DIR="/etc/systemd/system"
SM_CLI="/usr/local/bin/sketchmaker"

# Node only builds the frontend; it never runs in production. 22 is the line the build
# is tested on.
SM_NODE_MAJOR=22
SM_NODE_MIN_VERSION="22.23.4"
# uv before 0.13.4 bundles the compromised eMudhra roots (GHSA-hq85-5cpj-mr62).
SM_UV_MIN_VERSION="0.13.4"
SM_PYTHON_VERSION="3.12"

# uv: managed Pythons go outside /root so www-data can execute them (the service also
# runs with ProtectHome=true); prefer the distro Python when it matches; copy instead of
# hard-linking into root's cache; precompile bytecode because the service cannot write
# __pycache__.
export UV_PYTHON_INSTALL_DIR="/usr/local/share/uv/python"
export UV_PYTHON_PREFERENCE="system"
export UV_LINK_MODE="copy"
export UV_COMPILE_BYTECODE=1
export UV_NO_PROGRESS=1

# sudo resets PATH; uv may be a snap (/snap/bin) or a per-user install.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin:/root/.local/bin:/root/.cargo/bin"

SM_RED='\033[0;31m'
SM_GREEN='\033[0;32m'
SM_YELLOW='\033[1;33m'
SM_BLUE='\033[0;34m'
SM_NC='\033[0m'

SM_WARNINGS=()
SM_UV=""
SM_SERVER_NAMES=""
SM_CERT_NAME=""
SM_UNIT_BACKUP_DIR=""
SM_APT_UPDATED=0
SM_HEALTH_CODE=""
SM_HEALTH_BODY=""
SM_NGINX_MAIN_BACKUP=""
SM_CHANGED=0
SM_TS="$(date +%Y%m%d-%H%M%S)"

# ------------------------------------------------------------------
# Output
# ------------------------------------------------------------------
sm_ok()   { printf '%b[OK]%b %s\n' "$SM_GREEN" "$SM_NC" "$*"; }
sm_info() { printf '%s\n' "$*"; }
sm_step() { printf '\n%b== %s ==%b\n' "$SM_BLUE" "$*" "$SM_NC"; }
sm_err()  { printf '%b[ERROR]%b %s\n' "$SM_RED" "$SM_NC" "$*" >&2; }
sm_warn() {
    printf '%b[WARN]%b %s\n' "$SM_YELLOW" "$SM_NC" "$*" >&2
    SM_WARNINGS+=("$*")
}

sm_print_warnings() {
    local w
    if [ "${#SM_WARNINGS[@]}" -eq 0 ]; then
        sm_ok "No warnings"
        return 0
    fi
    printf '\n%bWarnings from this run (%s):%b\n' "$SM_YELLOW" "${#SM_WARNINGS[@]}" "$SM_NC"
    for w in "${SM_WARNINGS[@]}"; do
        printf '  - %s\n' "$w"
    done
}

# ------------------------------------------------------------------
# Small utilities
# ------------------------------------------------------------------

# sm_version_ge A B: true when version A >= version B.
sm_version_ge() {
    local lowest
    [ -n "$1" ] && [ -n "$2" ] || return 1
    lowest="$(printf '%s\n%s\n' "$1" "$2" | sort -V | sed -n 1p)"
    [ "$lowest" = "$2" ]
}

# sm_install_file DEST MODE OWNER:GROUP < content
# Installs stdin as DEST only when the content differs. Sets SM_CHANGED=1/0.
sm_install_file() {
    local dest="$1" mode="$2" owner="$3" tmp
    tmp="$(mktemp)"
    cat > "$tmp"
    if [ -f "$dest" ] && cmp -s "$tmp" "$dest"; then
        rm -f "$tmp"
        chown "$owner" "$dest"
        chmod "$mode" "$dest"
        SM_CHANGED=0
    else
        install -D -m "$mode" -o "${owner%%:*}" -g "${owner##*:}" "$tmp" "$dest"
        rm -f "$tmp"
        SM_CHANGED=1
    fi
    return 0
}

sm_backup_dir() {
    # sm_backup_dir NAME: prints a fresh root-only backup directory.
    local dir="$SM_BACKUP_ROOT/$1/$SM_TS"
    install -d -m 0700 -o root -g root "$SM_BACKUP_ROOT"
    install -d -m 0700 -o root -g root "$SM_BACKUP_ROOT/$1"
    install -d -m 0700 -o root -g root "$dir"
    printf '%s' "$dir"
}

sm_valid_domain() {
    [[ "$1" =~ ^([a-zA-Z0-9]([-a-zA-Z0-9]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$ ]]
}

# Host names served for a primary domain: an apex also gets www, and a www name also
# gets its apex.
sm_server_names_for() {
    local d="$1"
    if [[ "$d" == www.* ]]; then
        printf '%s %s' "$d" "${d#www.}"
    elif [[ "$d" =~ ^[^.]+\.[^.]+$ ]]; then
        printf '%s www.%s' "$d" "$d"
    else
        printf '%s' "$d"
    fi
}

# deploy.conf holds non-secret deploy facts (host names, certificate name, ACME email,
# the last update's rollback point) so update.sh never has to guess them. Mode 0600,
# because the email is personal data.
sm_conf_get() {
    [ -f "$SM_DEPLOY_CONF" ] || return 0
    sed -n "s/^$1=//p" "$SM_DEPLOY_CONF" | tail -n 1
}

sm_conf_set() {
    local key="$1" value="$2" tmp
    install -d -m 0700 -o root -g root "$SM_CONF_DIR"
    tmp="$(mktemp)"
    if [ -f "$SM_DEPLOY_CONF" ]; then
        grep -v "^$key=" "$SM_DEPLOY_CONF" > "$tmp" || true
    fi
    printf '%s=%s\n' "$key" "$value" >> "$tmp"
    install -m 0600 -o root -g root "$tmp" "$SM_DEPLOY_CONF"
    rm -f "$tmp"
}

# Runs an app command as the service user, so nothing in the data folder ends up owned
# by root.
sm_as_app() {
    (cd "$SM_BACKEND_DIR" && runuser -u www-data -- env HOME="$SM_DATA_DIR" "$@")
}

# ------------------------------------------------------------------
# apt
# ------------------------------------------------------------------
sm_apt_update() {
    if [ "$SM_APT_UPDATED" = 1 ]; then
        return 0
    fi
    SM_APT_UPDATED=1
    if DEBIAN_FRONTEND=noninteractive apt-get update -qq >/dev/null 2>&1; then
        return 0
    fi
    sm_warn "apt-get update failed (repositories unreachable, or the release is past end of support); package installs may fail"
    return 1
}

sm_pkg_installed() {
    local status
    status="$(dpkg-query -W -f='${Status}' "$1" 2>/dev/null || true)"
    [ "$status" = "install ok installed" ]
}

# sm_apt_install PKG...: installs whichever are missing. Non-zero on failure.
sm_apt_install() {
    local missing=() p
    for p in "$@"; do
        if ! sm_pkg_installed "$p"; then
            missing+=("$p")
        fi
    done
    if [ "${#missing[@]}" -eq 0 ]; then
        return 0
    fi
    sm_apt_update || true
    sm_info "Installing: ${missing[*]}"
    if DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}" >/dev/null; then
        return 0
    fi
    return 1
}

# ------------------------------------------------------------------
# OS status
# ------------------------------------------------------------------
sm_check_os_support() {
    local id ver version y m eol now kind
    [ -r /etc/os-release ] || return 0
    id="$(. /etc/os-release && printf '%s' "${ID:-}")"
    ver="$(. /etc/os-release && printf '%s' "${VERSION_ID:-}")"
    version="$(. /etc/os-release && printf '%s' "${VERSION:-}")"
    [ "$id" = "ubuntu" ] || return 0
    [[ "$ver" =~ ^([0-9]+)\.([0-9]+)$ ]] || return 0
    y=$((10#${BASH_REMATCH[1]} + 2000))
    m=$((10#${BASH_REMATCH[2]}))
    if [[ "$version" == *LTS* ]]; then
        kind="LTS"
        eol=$(( (y + 5) * 12 + m - 1 ))
    else
        kind="interim"
        eol=$(( y * 12 + m - 1 + 9 ))
    fi
    now=$(( 10#$(date +%Y) * 12 + 10#$(date +%m) - 1 ))
    if [ "$now" -gt "$eol" ]; then
        sm_warn "Ubuntu $ver ($kind) is past end of standard support and receives no security updates. Move to a current LTS: run server/install.sh on a fresh server, then follow 'Moving to a new server' in docs/DEPLOYMENT.md."
    else
        sm_ok "Ubuntu $ver ($kind) is within its support window"
    fi
    return 0
}

sm_check_reboot_required() {
    local pkgs=""
    if [ -f /var/run/reboot-required ]; then
        if [ -f /var/run/reboot-required.pkgs ]; then
            pkgs="$(sort -u /var/run/reboot-required.pkgs | tr '\n' ' ')"
        fi
        sm_warn "A reboot is pending to load security updates${pkgs:+ ($pkgs)}. Reboot during a quiet period."
    fi
    return 0
}

# eMudhra intermediate CA keys were compromised (disclosed 2026-10-17). Ubuntu ships the
# fix in ca-certificates (USN-8944-1), but releases past end of support never get it.
# Distrusting the root in the system store protects curl, apt, git and nginx upstreams.
# Python uses certifi, which is fixed in uv.lock.
sm_distrust_emsign_ecc_g3() {
    local conf=/etc/ca-certificates.conf f rel found=0 changed=0 tmp
    if [ ! -f "$conf" ]; then
        return 0
    fi
    for f in /usr/share/ca-certificates/mozilla/emSign_ECC_Root_CA_-_G3*.crt; do
        [ -e "$f" ] || continue
        found=1
        rel="mozilla/${f##*/}"
        if grep -qxF "!$rel" "$conf"; then
            continue
        fi
        tmp="$(mktemp)"
        if grep -qxF "$rel" "$conf"; then
            awk -v r="$rel" '$0 == r { print "!" r; next } { print }' "$conf" > "$tmp"
        else
            cat "$conf" > "$tmp"
            printf '!%s\n' "$rel" >> "$tmp"
        fi
        cat "$tmp" > "$conf"
        rm -f "$tmp"
        changed=1
    done
    if [ "$found" = 0 ] || [ "$changed" = 0 ]; then
        return 0
    fi
    if update-ca-certificates >/dev/null 2>&1; then
        sm_ok "Distrusted emSign ECC Root CA - G3 in the system CA store"
    else
        sm_warn "Marked emSign ECC Root CA - G3 as distrusted but update-ca-certificates failed; run it by hand"
    fi
    return 0
}

# ------------------------------------------------------------------
# Repository permissions and runtime directories
# ------------------------------------------------------------------
# git honours the invoking umask, so a deploy from a shell with a restrictive umask
# leaves source unreadable by www-data. Source is owned by root and read-only to the
# service; only the data directory belongs to www-data.
sm_normalise_permissions() {
    (
        cd "$SM_APP_ROOT" || exit 1
        chown root:root "$SM_APP_ROOT"
        chmod 0755 "$SM_APP_ROOT"
        git ls-files -z | xargs -0 -r chown root:root --
        git ls-files -z | xargs -0 -r chmod u+rw,go+r,go-w --
        git ls-files -z | xargs -0 -r dirname -z -- | sort -zu | xargs -0 -r chown root:root --
        git ls-files -z | xargs -0 -r dirname -z -- | sort -zu | xargs -0 -r chmod u+rwx,go+rx,go-w --

        # .git/config can hold a credential in the remote URL.
        chown -R root:root .git
        chmod 0600 .git/config
        if git config --get-regexp '^remote\..*\.url$' 2>/dev/null | awk '{print $2}' | grep -qE '^[a-zA-Z+]+://[^/@]+@'; then
            exit 3
        fi
        exit 0
    ) || {
        local rc=$?
        if [ "$rc" = 3 ]; then
            sm_warn "A credential is embedded in a git remote URL (value not shown). Replace it with a read-only deploy key and revoke the token."
        else
            sm_warn "Permission normalisation failed (exit $rc)"
        fi
    }
    sm_ok "Source owned by root and readable; .git/config is 0600"
    return 0
}

sm_ensure_runtime_dirs() {
    install -d -m 0700 -o www-data -g www-data "$SM_DATA_DIR"
    install -d -m 0755 -o root -g root "$SM_ACME_ROOT"
    install -d -m 0700 -o root -g root "$SM_BACKUP_ROOT"
    # The app clears its own render folders; this bounds everything else in the cache:
    # anything unused for 7 days goes, and the app recreates caches on demand.
    sm_install_file /etc/tmpfiles.d/sketchmaker.conf 0644 root:root <<EOF
# Managed by Sketchmaker (server/common.sh). Pruned daily by systemd-tmpfiles-clean.timer.
e $SM_DATA_DIR/cache - - - 7d
EOF
    sm_ok "Data directory $SM_DATA_DIR (www-data, 0700)"
    return 0
}

# A small command so nobody has to remember how to run the app's commands as www-data.
sm_install_cli() {
    sm_install_file "$SM_CLI" 0755 root:root <<EOF
#!/bin/bash
# Managed by Sketchmaker (server/common.sh). Usage: sudo sketchmaker <command>
if [ "\$EUID" -ne 0 ]; then
    echo "Run this with sudo: sudo sketchmaker \$*" >&2
    exit 1
fi
cd "$SM_BACKEND_DIR" || exit 1
exec runuser -u www-data -- env HOME="$SM_DATA_DIR" .venv/bin/python -m app.cli "\$@"
EOF
    return 0
}

# ------------------------------------------------------------------
# Secrets and environment
# ------------------------------------------------------------------
# backend/.env holds what is needed before the database can be read. It must be readable
# by the service (www-data) and nobody else, and writable only by root. Never overwritten:
# a new SECRET_KEY would make every stored provider key unreadable.
sm_ensure_env_file() {
    if [ -f "$SM_ENV_FILE" ]; then
        return 0
    fi
    (cd "$SM_BACKEND_DIR" && .venv/bin/python -m app.cli init --secrets-only >/dev/null) || return 1
    cat >> "$SM_ENV_FILE" <<EOF

DATA_DIR=$SM_DATA_DIR
# Only nginx can reach the app's socket, so its forwarded headers are trusted.
TRUSTED_PROXIES=*
DEBUG=false
LOG_LEVEL=INFO
EOF
    chown root:www-data "$SM_ENV_FILE"
    chmod 0640 "$SM_ENV_FILE"
    sm_ok "backend/.env created with fresh secrets (root:www-data 640)"
    return 0
}

sm_secure_env_file() {
    local cur key keys
    if [ ! -f "$SM_ENV_FILE" ]; then
        sm_warn "backend/.env is missing, so the app cannot start. Run server/install.sh again; restore the original file if you have stored provider keys."
        return 0
    fi
    cur="$(stat -c '%U:%G %a' "$SM_ENV_FILE")"
    if [ "$cur" != "root:www-data 640" ]; then
        chown root:www-data "$SM_ENV_FILE"
        chmod 0640 "$SM_ENV_FILE"
        sm_warn "backend/.env was $cur; fixed to root:www-data 640. If it was ever world-readable, re-enter your provider keys and consider new secrets."
    fi
    if ! grep -qE '^TRUSTED_PROXIES=.+' "$SM_ENV_FILE"; then
        sm_warn "backend/.env has no TRUSTED_PROXIES, so behind nginx the app refuses every request. Add TRUSTED_PROXIES=*"
    fi
    if grep -qiE '^DEBUG=(true|1|yes|on)[[:space:]]*$' "$SM_ENV_FILE"; then
        sm_warn "backend/.env has DEBUG enabled in production"
    fi
    keys="$(grep -oE '^[A-Z0-9_]+=.+' "$SM_ENV_FILE" | cut -d= -f1 \
            | grep -E '(_API_KEY|_SECRET|_TOKEN|_DSN|_PASSWORD|^FAL_KEY)$' \
            | grep -vxE 'SECRET_KEY|JWT_SECRET_KEY' || true)"
    for key in $keys; do
        sm_warn "backend/.env sets $key; provider keys belong in Settings, not .env"
    done
    sm_ok "backend/.env is root:www-data 640"
    return 0
}

# ------------------------------------------------------------------
# Node.js (system NodeSource build)
# ------------------------------------------------------------------
sm_ensure_node() {
    local cur="" setup
    if [ -x /usr/bin/node ]; then
        cur="$(/usr/bin/node -v 2>/dev/null | sed 's/^v//' || true)"
    fi
    if [ -z "$cur" ] || ! sm_version_ge "$cur" "$SM_NODE_MIN_VERSION"; then
        sm_info "System Node ${cur:-is missing} (need $SM_NODE_MIN_VERSION or newer); installing Node $SM_NODE_MAJOR from NodeSource"
        setup="$(mktemp)"
        if curl -fsSL --proto '=https' --tlsv1.2 -o "$setup" "https://deb.nodesource.com/setup_${SM_NODE_MAJOR}.x" \
            && bash "$setup" >/dev/null 2>&1; then
            SM_APT_UPDATED=1
            if ! DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nodejs >/dev/null; then
                sm_warn "apt-get install nodejs failed"
            fi
        else
            sm_warn "NodeSource setup for Node $SM_NODE_MAJOR failed"
        fi
        rm -f "$setup"
        cur="$(/usr/bin/node -v 2>/dev/null | sed 's/^v//' || true)"
    fi
    if [ -z "$cur" ] || [ ! -x /usr/bin/npm ]; then
        sm_err "Node.js and npm are not available, so the frontend cannot be built"
        return 1
    fi
    # /usr/bin first so an old /usr/local/bin/node cannot win.
    export PATH="/usr/bin:$PATH"
    hash -r
    if ! sm_version_ge "$cur" "$SM_NODE_MIN_VERSION"; then
        sm_warn "Node $cur is still below $SM_NODE_MIN_VERSION; building anyway"
    fi
    sm_ok "Node $cur, npm $(npm -v 2>/dev/null || echo '?')"
    return 0
}

# Builds into dist.next and leaves the live site alone. sm_swap_frontend puts it live.
# Exactly what package-lock.json pins, and no dependency runs code at install time.
sm_build_frontend() {
    (
        cd "$SM_FRONTEND_DIR" || exit 1
        npm ci --ignore-scripts --no-audit --no-fund --loglevel=error || exit 1
        # A dist.prev left by an interrupted update must not be restored by a later undo.
        rm -rf dist.next dist.prev
        npm run build -- --outDir dist.next --emptyOutDir || exit 1
        [ -f dist.next/index.html ] || { echo "The build produced no index.html" >&2; exit 1; }
        chmod -R u=rwX,go=rX dist.next
    ) || return 1
    sm_ok "Frontend built"
    return 0
}

sm_swap_frontend() {
    (
        cd "$SM_FRONTEND_DIR" || exit 1
        [ -d dist.next ] || exit 0
        rm -rf dist.prev
        if [ -d dist ]; then
            mv dist dist.prev || exit 1
        fi
        mv dist.next dist || { mv dist.prev dist 2>/dev/null; exit 1; }
    ) || return 1
    return 0
}

sm_swap_frontend_back() {
    (
        cd "$SM_FRONTEND_DIR" || exit 1
        rm -rf dist.next
        [ -d dist.prev ] || exit 0
        rm -rf dist
        mv dist.prev dist
    ) || return 1
    return 0
}

# ------------------------------------------------------------------
# uv and the Python environment
# ------------------------------------------------------------------
sm_find_uv() {
    local c
    SM_UV=""
    for c in "$(command -v uv 2>/dev/null || true)" /usr/local/bin/uv /snap/bin/uv /root/.local/bin/uv /root/.cargo/bin/uv; do
        if [ -n "$c" ] && [ -x "$c" ]; then
            SM_UV="$c"
            return 0
        fi
    done
    return 1
}

sm_uv_version() {
    "$SM_UV" --version 2>/dev/null | awk '{print $2}'
}

sm_ensure_uv() {
    local v installer
    if ! sm_find_uv; then
        sm_info "Installing uv to /usr/local/bin..."
        installer="$(mktemp)"
        if ! curl -fsSL --proto '=https' --tlsv1.2 -o "$installer" https://astral.sh/uv/install.sh \
            || ! env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh "$installer" >/dev/null 2>&1; then
            rm -f "$installer"
            sm_err "uv could not be installed"
            return 1
        fi
        rm -f "$installer"
        sm_find_uv || return 1
    fi
    v="$(sm_uv_version)"
    if ! sm_version_ge "$v" "$SM_UV_MIN_VERSION"; then
        sm_info "uv $v is below $SM_UV_MIN_VERSION; updating"
        case "$SM_UV" in
            /snap/*) snap refresh astral-uv >/dev/null 2>&1 || true ;;
            *)       "$SM_UV" self update >/dev/null 2>&1 || true ;;
        esac
        v="$(sm_uv_version)"
        if ! sm_version_ge "$v" "$SM_UV_MIN_VERSION"; then
            sm_warn "uv is still $v (below $SM_UV_MIN_VERSION); update it by hand"
        fi
    fi
    sm_ok "uv $v ($SM_UV)"
    return 0
}

# The venv must run as www-data. A release upgrade removes the old /usr/bin/python3.X,
# and a uv-managed Python under /root is unreadable by www-data; either way it is rebuilt.
sm_venv_usable() {
    local py="$SM_BACKEND_DIR/.venv/bin/python"
    [ -x "$py" ] || return 1
    (cd / && runuser -u www-data -- "$py" -c "import sys; sys.exit(0 if sys.version_info[:2] == ($(printf '%s' "$SM_PYTHON_VERSION" | tr . ,)) else 1)") >/dev/null 2>&1
}

sm_ensure_venv() {
    local venv="$SM_BACKEND_DIR/.venv"
    if sm_venv_usable; then
        sm_ok "Python venv OK ($("$venv/bin/python" -V 2>&1))"
        return 0
    fi
    rm -rf "$venv"
    (cd "$SM_BACKEND_DIR" && "$SM_UV" venv --python "$SM_PYTHON_VERSION" .venv) || return 1
    if [ -d "$UV_PYTHON_INSTALL_DIR" ]; then
        chmod -R go+rX "$UV_PYTHON_INSTALL_DIR"
    fi
    chmod -R go+rX "$venv"
    if ! sm_venv_usable; then
        sm_err "The new venv cannot be executed by www-data"
        return 1
    fi
    sm_ok "Created backend/.venv ($("$venv/bin/python" -V 2>&1))"
    return 0
}

# Installs exactly what uv.lock pins (never resolves from PyPI).
sm_sync_python_deps() {
    if ! (cd "$SM_BACKEND_DIR" && "$SM_UV" sync --frozen --no-dev --no-install-project); then
        sm_err "uv sync --frozen failed"
        return 1
    fi
    chmod -R go+rX "$SM_BACKEND_DIR/.venv"
    sm_ok "Python dependencies synced from uv.lock"
    return 0
}

# The service cannot write __pycache__ (read-only source), so compile as root.
sm_compile_app() {
    if (cd "$SM_BACKEND_DIR" && .venv/bin/python -m compileall -q -j 0 app alembic >/dev/null); then
        sm_ok "Backend bytecode compiled"
    else
        sm_warn "compileall reported errors in backend sources"
    fi
    return 0
}

# Indicators of the malicious LiteLLM 1.107.0 release (2026-10-21).
sm_check_malicious_packages() {
    local hits=() sp f
    for sp in "$SM_BACKEND_DIR"/.venv/lib/python3*/site-packages; do
        [ -d "$sp" ] || continue
        for f in "$sp/cook.pth" "$sp/cook.py" "$sp/litellm-1.107.0.dist-info"; do
            if [ -e "$f" ]; then
                hits+=("$f")
            fi
        done
    done
    for f in /tmp/remote_code_loader.lock /var/tmp/remote_code_loader.lock /tmp/systemd-private-*/tmp/remote_code_loader.lock; do
        if [ -e "$f" ]; then
            hits+=("$f")
        fi
    done
    if [ "${#hits[@]}" -eq 0 ]; then
        sm_ok "No indicators of the malicious LiteLLM 1.107.0 release"
        return 0
    fi
    for f in "${hits[@]}"; do
        sm_warn "POSSIBLE COMPROMISE indicator found: $f. Stop the service, replace every key stored in Settings and .env, and investigate before continuing."
    done
    return 0
}

# ------------------------------------------------------------------
# Database: snapshot, migrate, restore
# ------------------------------------------------------------------
# A root-only copy taken with the service stopped, outside the data folder, so the whole
# update can be undone. Sets SM_DB_SNAPSHOT (empty when there is no database yet).
sm_snapshot_db() {
    local dir
    SM_DB_SNAPSHOT=""
    [ -f "$SM_DB" ] || return 0
    dir="$(sm_backup_dir db)"
    # With the app stopped its WAL has been checkpointed, but a crash can leave one behind.
    cp -p "$SM_DB" "$dir/sketchmaker.db" || return 1
    if [ -f "$SM_DB-wal" ]; then
        cp -p "$SM_DB-wal" "$dir/sketchmaker.db-wal" || return 1
    fi
    # shellcheck disable=SC2034  # read by update.sh and restore.sh
    SM_DB_SNAPSHOT="$dir"
    # Newest first; everything after the first few goes.
    find "$SM_BACKUP_ROOT/db" -mindepth 1 -maxdepth 1 -type d | sort -r | tail -n +$((SM_SNAPSHOT_KEEP + 1)) \
        | xargs -r rm -rf --
    sm_ok "Database snapshot in $dir"
    return 0
}

sm_restore_snapshot() {
    local dir="$1"
    [ -n "$dir" ] && [ -f "$dir/sketchmaker.db" ] || return 1
    rm -f "$SM_DB-wal" "$SM_DB-shm"
    install -m 0600 -o www-data -g www-data "$dir/sketchmaker.db" "$SM_DB" || return 1
    if [ -f "$dir/sketchmaker.db-wal" ]; then
        install -m 0600 -o www-data -g www-data "$dir/sketchmaker.db-wal" "$SM_DB-wal" || return 1
    fi
    return 0
}

# The app's own procedure: it backs up, migrates, verifies, and puts the database back by
# itself if any of that fails. The service must be stopped.
sm_migrate_db() {
    if sm_as_app .venv/bin/python -m app.cli migrate; then
        sm_ok "Database schema is current"
        return 0
    fi
    sm_err "The database migration failed. See the message above."
    return 1
}

# ------------------------------------------------------------------
# systemd unit
# ------------------------------------------------------------------
sm_install_units() {
    local src="$SM_SERVER_DIR/sketchmaker.service" dest="$SM_UNIT_DIR/$SM_SERVICE_NAME.service"
    SM_UNIT_BACKUP_DIR=""
    if [ ! -f "$src" ]; then
        sm_err "Unit template missing in $SM_SERVER_DIR"
        return 1
    fi
    if [ ! -f "$dest" ] || ! cmp -s "$src" "$dest"; then
        SM_UNIT_BACKUP_DIR="$(sm_backup_dir systemd)"
        if [ -f "$dest" ]; then
            cp -p "$dest" "$SM_UNIT_BACKUP_DIR/"
        fi
        install -m 0644 -o root -g root "$src" "$dest"
        systemctl daemon-reload
        sm_ok "systemd unit updated"
    else
        sm_ok "systemd unit already current"
    fi
    systemctl enable --quiet "$SM_SERVICE_NAME"
    if compgen -G "$SM_UNIT_DIR/$SM_SERVICE_NAME.service.d/*.conf" >/dev/null; then
        sm_warn "Drop-in overrides exist in $SM_UNIT_DIR/$SM_SERVICE_NAME.service.d/ and may weaken the sandbox; review them"
    fi
    return 0
}

sm_wait_healthy() {
    local tmp code=""
    tmp="$(mktemp)"
    for _ in $(seq 1 30); do
        code="$(curl -s -o "$tmp" -w '%{http_code}' --max-time 5 \
                --unix-socket "$SM_SOCKET" http://localhost/api/health 2>/dev/null || true)"
        if [ "$code" = "200" ]; then
            rm -f "$tmp"
            SM_HEALTH_CODE=200
            return 0
        fi
        printf '.'
        sleep 2
    done
    SM_HEALTH_CODE="${code:-none}"
    SM_HEALTH_BODY="$(head -c 300 "$tmp" 2>/dev/null || true)"
    rm -f "$tmp"
    return 1
}

sm_start_service() {
    systemctl restart "$SM_SERVICE_NAME" || true
    printf 'Waiting for the app to become healthy'
    if sm_wait_healthy; then
        printf '\n'
        sm_ok "The app is healthy"
        return 0
    fi
    printf '\n'
    sm_err "The app did not become healthy within 60s (HTTP $SM_HEALTH_CODE) ${SM_HEALTH_BODY}. Check: journalctl -u $SM_SERVICE_NAME -n 50"
    return 1
}

# ------------------------------------------------------------------
# nginx
# ------------------------------------------------------------------
sm_tune_nginx_main_conf() {
    local conf=/etc/nginx/nginx.conf tmp
    SM_NGINX_MAIN_BACKUP=""
    [ -f "$conf" ] || return 0
    tmp="$(mktemp)"
    cp "$conf" "$tmp"
    sed -i -E 's/^([[:space:]]*)worker_processes[[:space:]]+1;/\1worker_processes auto;/' "$tmp"
    if ! grep -q 'worker_rlimit_nofile' "$tmp"; then
        sed -i -E '/^[[:space:]]*worker_processes[[:space:]]/a worker_rlimit_nofile 65535;' "$tmp"
    fi
    sed -i -E 's/^([[:space:]]*)worker_connections[[:space:]]+(768|1024);/\1worker_connections 2048;/' "$tmp"
    # Global default for any other site; this one sets the same per server.
    sed -i -E 's/^([[:space:]]*)ssl_protocols[[:space:]][^;]*;/\1ssl_protocols TLSv1.2 TLSv1.3;/' "$tmp"
    sed -i -E 's/^([[:space:]]*)#[[:space:]]*server_tokens[[:space:]]+off;/\1server_tokens off;/' "$tmp"
    if cmp -s "$tmp" "$conf"; then
        rm -f "$tmp"
        return 0
    fi
    SM_NGINX_MAIN_BACKUP="$(sm_backup_dir nginx)/nginx.conf"
    cp -p "$conf" "$SM_NGINX_MAIN_BACKUP"
    cat "$tmp" > "$conf"
    rm -f "$tmp"
    return 0
}

sm_ensure_snakeoil() {
    if [ -f /etc/ssl/certs/ssl-cert-snakeoil.pem ] && [ -f /etc/ssl/private/ssl-cert-snakeoil.key ]; then
        return 0
    fi
    sm_apt_install ssl-cert || true
    if command -v make-ssl-cert >/dev/null 2>&1; then
        make-ssl-cert generate-default-snakeoil >/dev/null 2>&1 || true
    fi
    [ -f /etc/ssl/certs/ssl-cert-snakeoil.pem ] && [ -f /etc/ssl/private/ssl-cert-snakeoil.key ]
}

# Sets SM_SERVER_NAMES and SM_CERT_NAME from deploy.conf.
sm_discover_site() {
    local n
    SM_SERVER_NAMES="$(sm_conf_get SERVER_NAMES)"
    SM_CERT_NAME="$(sm_conf_get CERT_NAME)"
    [ -n "$SM_SERVER_NAMES" ] || return 1
    for n in $SM_SERVER_NAMES; do
        if ! sm_valid_domain "$n"; then
            SM_SERVER_NAMES=""
            return 1
        fi
    done
    if [ -n "$SM_CERT_NAME" ] && ! [[ "$SM_CERT_NAME" =~ ^[A-Za-z0-9.-]+$ ]]; then
        SM_CERT_NAME=""
    fi
    return 0
}

sm_render_site() {
    # sm_render_site TEMPLATE OUT NAMES CERT
    sed -e "s|__SERVER_NAMES__|$3|g" -e "s|__CERT_NAME__|$4|g" "$1" > "$2"
}

# Port 80 only, used until a certificate exists: answers ACME challenges and nothing else.
sm_write_bootstrap_site() {
    cat > "$1" <<EOF
# Temporary Sketchmaker site: no TLS certificate yet. It only answers ACME challenges.
# server/update.sh or install.sh replaces it once /etc/letsencrypt/live/<cert>/ exists.
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    server_tokens off;
    return 444;
}

server {
    listen 80;
    listen [::]:80;
    server_name $2;
    server_tokens off;

    location ^~ /.well-known/acme-challenge/ {
        root $SM_ACME_ROOT;
        default_type text/plain;
    }

    location / {
        return 503;
    }
}
EOF
}

# Renders the template (or the bootstrap site when no certificate exists yet), validates
# with nginx -t, reloads, and rolls everything back if validation fails.
sm_install_nginx_site() {
    local template="$SM_SERVER_DIR/sketchmaker.nginx.conf" candidate bdir had_site=0 default_removed="" out
    if ! sm_discover_site; then
        sm_warn "No host names in $SM_DEPLOY_CONF; nginx not changed"
        return 1
    fi
    if [ ! -f "$template" ]; then
        sm_warn "nginx template $template not found; nginx not changed"
        return 1
    fi
    if ! sm_ensure_snakeoil; then
        sm_warn "Snakeoil certificate unavailable (package ssl-cert); nginx not changed"
        return 1
    fi
    candidate="$(mktemp)"
    if [ -n "$SM_CERT_NAME" ] && [ -f "/etc/letsencrypt/live/$SM_CERT_NAME/fullchain.pem" ]; then
        sm_render_site "$template" "$candidate" "$SM_SERVER_NAMES" "$SM_CERT_NAME"
    else
        if [ -f "$SM_NGINX_SITE" ] && grep -qE '^[[:space:]]*ssl_certificate[[:space:]]' "$SM_NGINX_SITE"; then
            rm -f "$candidate"
            sm_warn "The live nginx site uses TLS but its certificate could not be located; left unchanged"
            return 1
        fi
        sm_write_bootstrap_site "$candidate" "$SM_SERVER_NAMES"
        sm_info "No TLS certificate yet for $SM_SERVER_NAMES; serving the ACME-only site"
    fi

    sm_tune_nginx_main_conf

    if [ -f "$SM_NGINX_SITE" ] && cmp -s "$candidate" "$SM_NGINX_SITE" && [ -z "$SM_NGINX_MAIN_BACKUP" ] \
        && [ -L "$SM_NGINX_SITE_LINK" ]; then
        rm -f "$candidate"
        sm_ok "nginx site already current"
        return 0
    fi

    bdir="$(sm_backup_dir nginx)"
    if [ -f "$SM_NGINX_SITE" ]; then
        had_site=1
        cp -p "$SM_NGINX_SITE" "$bdir/sketchmaker"
    fi
    install -m 0644 -o root -g root "$candidate" "$SM_NGINX_SITE"
    rm -f "$candidate"
    ln -sfn "$SM_NGINX_SITE" "$SM_NGINX_SITE_LINK"
    # The stock default site also claims default_server.
    if [ -L /etc/nginx/sites-enabled/default ]; then
        default_removed="$(readlink /etc/nginx/sites-enabled/default)"
        rm -f /etc/nginx/sites-enabled/default
    fi

    if nginx -t >/dev/null 2>&1; then
        if systemctl is-active --quiet nginx; then
            systemctl reload nginx
        else
            systemctl enable --now nginx >/dev/null 2>&1 || true
        fi
        sm_ok "nginx site installed and reloaded (previous copy in $bdir)"
        return 0
    fi

    out="$(nginx -t 2>&1 || true)"
    if [ "$had_site" = 1 ]; then
        cp -p "$bdir/sketchmaker" "$SM_NGINX_SITE"
    else
        rm -f "$SM_NGINX_SITE" "$SM_NGINX_SITE_LINK"
    fi
    if [ -n "$SM_NGINX_MAIN_BACKUP" ]; then
        cp -p "$SM_NGINX_MAIN_BACKUP" /etc/nginx/nginx.conf
    fi
    if [ -n "$default_removed" ]; then
        ln -sfn "$default_removed" /etc/nginx/sites-enabled/default
    fi
    sm_warn "New nginx config failed validation and was rolled back. nginx -t said: $(printf '%s' "$out" | tr '\n' ' ')"
    return 1
}

# Obtains a certificate with the webroot authenticator when none exists. Certbot never
# edits the nginx config.
sm_ensure_certificate() {
    local email cert names args=() n
    sm_discover_site || return 1
    names="$SM_SERVER_NAMES"
    cert="${SM_CERT_NAME:-${names%% *}}"
    if [ -f "/etc/letsencrypt/live/$cert/fullchain.pem" ]; then
        SM_CERT_NAME="$cert"
        sm_conf_set CERT_NAME "$cert"
        return 0
    fi
    email="$(sm_conf_get ADMIN_EMAIL)"
    if [ -z "$email" ]; then
        sm_warn "No certificate for $names and no email known for Let's Encrypt. Run server/install.sh again."
        return 1
    fi
    if ! command -v certbot >/dev/null 2>&1 && ! sm_apt_install certbot; then
        sm_warn "certbot is not installed and could not be installed"
        return 1
    fi
    for n in $names; do
        args+=(-d "$n")
    done
    if certbot certonly --webroot -w "$SM_ACME_ROOT" --cert-name "$cert" "${args[@]}" \
        --non-interactive --agree-tos -m "$email" --keep-until-expiring; then
        SM_CERT_NAME="$cert"
        sm_conf_set CERT_NAME "$cert"
        sm_ok "TLS certificate issued for $names"
        return 0
    fi
    # An apex domain also asks for www, whose DNS record may simply not exist.
    if [ "$names" != "$cert" ] && certbot certonly --webroot -w "$SM_ACME_ROOT" --cert-name "$cert" -d "$cert" \
        --non-interactive --agree-tos -m "$email" --keep-until-expiring; then
        SM_CERT_NAME="$cert"
        SM_SERVER_NAMES="$cert"
        sm_conf_set CERT_NAME "$cert"
        sm_conf_set SERVER_NAMES "$cert"
        sm_warn "Certificate issued for $cert only: the other names in \"$names\" could not be verified. Check their DNS records."
        return 0
    fi
    sm_warn "certbot could not obtain a certificate for $names. Check that the DNS A/AAAA records point at this server and port 80 is reachable. Behind Cloudflare: set the records to DNS only (grey cloud) while issuing, then run update.sh."
    return 1
}

sm_ensure_cert_renewal() {
    sm_install_file /etc/letsencrypt/renewal-hooks/deploy/sketchmaker-reload-nginx 0755 root:root <<'EOF'
#!/bin/sh
# Managed by Sketchmaker (server/common.sh). Reload nginx after a renewal.
nginx -t -q && systemctl reload nginx
EOF
    if systemctl list-unit-files --no-legend certbot.timer 2>/dev/null | grep -q certbot; then
        systemctl enable --now certbot.timer >/dev/null 2>&1 || true
        sm_ok "Certificate renewal: certbot.timer with an nginx reload hook"
    elif systemctl list-unit-files --no-legend snap.certbot.renew.timer 2>/dev/null | grep -q certbot; then
        sm_ok "Certificate renewal: snap.certbot.renew.timer with an nginx reload hook"
    else
        sm_install_file /etc/cron.d/sketchmaker-certbot 0644 root:root <<'EOF'
# Managed by Sketchmaker (server/common.sh): no certbot timer on this server.
17 3 * * * root certbot renew --quiet
EOF
        sm_ok "Certificate renewal: /etc/cron.d/sketchmaker-certbot with an nginx reload hook"
    fi
    return 0
}

# Warns when Cloudflare publishes ranges missing from the set_real_ip_from list (rate
# limits would then key on an edge address).
sm_check_cloudflare_ranges() {
    local template="$SM_SERVER_DIR/sketchmaker.nginx.conf" live r absent=""
    live="$({ curl -fsS --max-time 10 https://www.cloudflare.com/ips-v4; echo; curl -fsS --max-time 10 https://www.cloudflare.com/ips-v6; } 2>/dev/null || true)"
    if [ -z "$live" ]; then
        sm_info "Could not fetch Cloudflare IP ranges; real-IP list not checked"
        return 0
    fi
    for r in $live; do
        [[ "$r" =~ ^[0-9a-fA-F:.]+/[0-9]+$ ]] || continue
        if ! grep -qF "set_real_ip_from $r;" "$template"; then
            absent="$absent $r"
        fi
    done
    if [ -n "$absent" ]; then
        sm_warn "Cloudflare publishes ranges missing from set_real_ip_from in server/sketchmaker.nginx.conf:$absent"
    else
        sm_ok "Cloudflare real-IP ranges current"
    fi
    return 0
}

# ------------------------------------------------------------------
# Host hardening
# ------------------------------------------------------------------
sm_ssh_ports() {
    local ports="22" p
    for p in $( { sshd -T 2>/dev/null || true; } | awk '$1 == "port" {print $2}'); do
        ports="$ports $p"
    done
    for p in $( { systemctl show ssh.socket -p Listen --value 2>/dev/null || true; } | grep -oE ':[0-9]+ ' | tr -d ': ' || true); do
        ports="$ports $p"
    done
    for p in $ports; do
        if [[ "$p" =~ ^[0-9]+$ ]] && [ "$p" -ge 1 ] && [ "$p" -le 65535 ]; then
            printf '%s\n' "$p"
        fi
    done | sort -un | tr '\n' ' ' | sed 's/ $//'
}

# Firewall: allow SSH (every configured port, always 22) BEFORE enabling, then 80/443.
# Never removes existing rules. Enabling does not drop the current SSH session.
sm_ensure_firewall() {
    local ports p status
    if ! command -v ufw >/dev/null 2>&1 && ! sm_apt_install ufw; then
        sm_warn "ufw is not installed and could not be installed; no host firewall"
        return 0
    fi
    ports="$(sm_ssh_ports)"
    for p in $ports; do
        ufw allow "$p/tcp" comment 'SSH' >/dev/null || sm_warn "ufw allow $p/tcp failed"
    done
    ufw allow 80/tcp comment 'HTTP' >/dev/null || sm_warn "ufw allow 80/tcp failed"
    ufw allow 443/tcp comment 'HTTPS' >/dev/null || sm_warn "ufw allow 443/tcp failed"
    status="$(ufw status 2>/dev/null || true)"
    case "$status" in
        *"Status: active"*)
            sm_ok "ufw active; SSH ($ports), 80 and 443 allowed"
            ;;
        *)
            ufw default deny incoming >/dev/null || sm_warn "ufw default deny failed"
            ufw default allow outgoing >/dev/null || sm_warn "ufw default allow failed"
            if ufw --force enable >/dev/null; then
                sm_ok "ufw enabled with SSH ($ports), 80 and 443 allowed and everything else inbound denied"
            else
                sm_warn "ufw enable failed; no host firewall"
            fi
            ;;
    esac
    return 0
}

sm_admin_ip() {
    local ip
    ip="$(who -m 2>/dev/null | sed -n 's/.*(\([0-9a-fA-F:.]*\)).*/\1/p' || true)"
    if [[ "$ip" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || [[ "$ip" =~ ^[0-9a-fA-F:]+:[0-9a-fA-F:]*$ ]]; then
        printf '%s' "$ip"
    fi
}

# fail2ban: the sshd jail, plus one that bans an address at the firewall for repeated
# failed logins on the app. Behind Cloudflare the ban has no effect (the peer is the edge),
# so the app's own per-address limit is what holds there.
sm_ensure_fail2ban() {
    local ports admin ignore source_lines changed=0
    if ! sm_apt_install fail2ban; then
        sm_warn "fail2ban could not be installed; SSH brute force is unmitigated"
        return 0
    fi
    ports="$(sm_ssh_ports | tr ' ' ',')"
    admin="$(sm_admin_ip)"
    ignore="127.0.0.1/8 ::1${admin:+ $admin}"
    if [ -f /var/log/auth.log ]; then
        source_lines="backend = auto
logpath = /var/log/auth.log"
    else
        sm_apt_install python3-systemd || sm_warn "python3-systemd missing; the journal backend may not start"
        source_lines="backend = systemd
journalmatch = _SYSTEMD_UNIT=ssh.service"
    fi
    sm_install_file /etc/fail2ban/filter.d/sketchmaker-auth.conf 0644 root:root <<'EOF'
# Managed by Sketchmaker (server/common.sh). Failed or rate limited logins in nginx's log.
[Definition]
failregex = ^<HOST> \S+ \S+ \[[^\]]*\] "POST /api/auth/login[^"]*" (?:401|429)
ignoreregex =
EOF
    changed="$SM_CHANGED"
    sm_install_file /etc/fail2ban/jail.d/sketchmaker.local 0644 root:root <<EOF
# Managed by Sketchmaker (server/common.sh, applied by install.sh and update.sh).
# ignoreip includes the address of the admin session that last ran the script, so a few
# mistyped passwords cannot lock the operator out.
[sshd]
enabled = true
port = $ports
$source_lines
maxretry = 5
findtime = 10m
bantime = 1h
bantime.increment = true
ignoreip = $ignore

# Well above the app's own limit of ten per 15 minutes, so a colleague who mistypes a
# password is never banned along with the rest of the office.
[sketchmaker-auth]
enabled = true
port = http,https
filter = sketchmaker-auth
logpath = /var/log/nginx/access.log
maxretry = 30
findtime = 15m
bantime = 1h
bantime.increment = true
ignoreip = $ignore
EOF
    if [ "$SM_CHANGED" = 1 ]; then
        changed=1
    fi
    systemctl enable --quiet fail2ban || true
    if [ "$changed" = 1 ] || ! systemctl is-active --quiet fail2ban; then
        systemctl restart fail2ban || true
    fi
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        if fail2ban-client status sshd >/dev/null 2>&1; then
            if fail2ban-client status sketchmaker-auth >/dev/null 2>&1; then
                sm_ok "fail2ban active: sshd (ports $ports) and sketchmaker-auth; ignoreip $ignore"
            else
                sm_warn "The fail2ban sketchmaker-auth jail is not running. Check: fail2ban-client status"
            fi
            return 0
        fi
        sleep 1
    done
    sm_warn "The fail2ban sshd jail is not running. Check: systemctl status fail2ban"
    return 0
}

sm_ensure_unattended_upgrades() {
    if ! sm_apt_install unattended-upgrades; then
        sm_warn "unattended-upgrades could not be installed"
        return 0
    fi
    sm_install_file /etc/apt/apt.conf.d/20auto-upgrades 0644 root:root <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
    sm_ok "Unattended security upgrades enabled (no automatic reboot)"
    return 0
}

# Never changes sshd_config: the operator may not have a working key yet.
sm_ssh_recommendations() {
    local cfg prl pa
    cfg="$(sshd -T 2>/dev/null || true)"
    prl="$(printf '%s\n' "$cfg" | awk '$1 == "permitrootlogin" {print $2}')"
    pa="$(printf '%s\n' "$cfg" | awk '$1 == "passwordauthentication" {print $2}')"
    if [ "$pa" = "yes" ] || [ "$prl" = "yes" ]; then
        sm_warn "SSH accepts passwords (PasswordAuthentication=$pa, PermitRootLogin=$prl) and is under constant brute force. Add your public key, confirm a key login works in a SECOND session, then put 'PasswordAuthentication no' and 'PermitRootLogin prohibit-password' in /etc/ssh/sshd_config.d/10-hardening.conf, run 'sshd -t' and 'systemctl reload ssh'. Not changed automatically."
    fi
    return 0
}

# Warning-only audit. pip-audit runs with --exclude-newer so a package published in the
# last week (a fresh malicious release) is never resolved.
sm_dependency_audit() {
    local cutoff req
    if command -v npm >/dev/null 2>&1 && [ -d "$SM_FRONTEND_DIR/node_modules" ]; then
        if (cd "$SM_FRONTEND_DIR" && timeout 180 npm audit --omit=dev --audit-level=high); then
            sm_ok "npm audit: no high or critical advisories in production dependencies"
        else
            sm_warn "npm audit reported advisories or could not run; review the output above"
        fi
    fi
    if [ -n "$SM_UV" ]; then
        cutoff="$(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || true)"
        req="$(mktemp)"
        if (cd "$SM_BACKEND_DIR" && "$SM_UV" export --frozen --no-dev --no-hashes --no-emit-project --format requirements-txt -o "$req" >/dev/null 2>&1) \
            && timeout 300 "$SM_UV" tool run ${cutoff:+--exclude-newer "$cutoff"} pip-audit \
                -r "$req" --no-deps --disable-pip --progress-spinner off; then
            sm_ok "pip-audit: no known vulnerabilities in the locked Python packages"
        else
            sm_warn "pip-audit reported vulnerabilities or could not run; review the output above"
        fi
        rm -f "$req"
    fi
    return 0
}
