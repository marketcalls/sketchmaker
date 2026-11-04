# Deployment

- [Publish on your domain](#publish-on-your-domain)
- [Updating](#updating)
- [Rolling back and restoring](#rolling-back-and-restoring)
- [Moving to a new server](#moving-to-a-new-server)
- [Docker](#docker)
- [Database migrations](#database-migrations)
- [Security](#security)

## Publish on your domain

For a team using the app from their own computers. You need:

- a fresh Ubuntu LTS server, with root or sudo
- a domain name whose DNS A or AAAA record already points at the server
- ports 80 and 443 reachable from the internet

```bash
curl -fsSL https://raw.githubusercontent.com/marketcalls/sketchmaker/main/server/install.sh -o install.sh
sudo bash install.sh
```

If the repository is private, a plain `curl` will not reach it. Clone it into `/var/www/sketchmaker` with a read-only deploy key, then run `sudo bash /var/www/sketchmaker/server/install.sh`.

The installer asks for your domain, an email for certificate notices, and the username and password your team will sign in with. If it fails part way, fix the cause and run it again: the secrets and the database are kept. Once the app is running, it refuses to run and points you to `update.sh`.

| Step | What it does |
|---|---|
| Packages | nginx, certbot, ffmpeg, ufw, fail2ban, unattended-upgrades |
| App | Clones into `/var/www/sketchmaker`, owned by root, with dependencies from the lock files |
| Secrets | Creates `backend/.env` with fresh secrets, readable only by the service |
| Data | Creates `/var/lib/sketchmaker`, owned by the service |
| Account | Creates your login **in the terminal, before the site goes live**, so nobody can claim it first |
| Service | A sandboxed systemd unit serving on a private socket |
| HTTPS | A Let's Encrypt certificate, renewed automatically |
| Hardening | Firewall with only SSH, 80 and 443 open, fail2ban for SSH and logins, automatic security updates |

Then sign in at `https://your-domain`, add your provider keys under **Settings > API keys**, and set spending limits with your providers.

**Using Cloudflare:** set the DNS records to "DNS only" (grey cloud) while the certificate is issued. You can turn the proxy on afterwards. The nginx site already trusts the real visitor address from Cloudflare, and `update.sh` warns if Cloudflare's address list changes.

### Everyday commands

```bash
sudo sketchmaker reset-password     # change the password; ends every session
sudo sketchmaker unlock             # clear an account lock
sudo sketchmaker backup             # back up the database now
journalctl -u sketchmaker -f        # follow the logs
sudo systemctl restart sketchmaker  # restart the app
sudo fail2ban-client status         # see who is banned
```

### Where things are

| Path | Contents |
|---|---|
| `/var/www/sketchmaker` | The code, owned by root and read-only to the service |
| `/var/www/sketchmaker/backend/.env` | Secrets, `root:www-data`, mode 640 |
| `/var/lib/sketchmaker` | Database, media, nightly backups, logs and cache |
| `/var/backups/sketchmaker` | Root-only copies from each update, and previous nginx and systemd files |
| `/etc/sketchmaker/deploy.conf` | Your domain, the certificate name, and the last update's rollback point |

## Updating

```bash
sudo bash /var/www/sketchmaker/server/update.sh
```

The order keeps downtime short and failures safe:

1. Pulls the new code. It stops first if tracked files were changed on the server.
2. Applies host hardening, installs dependencies and builds the frontend into a side folder, **while the old version keeps serving**. If either step fails, the code goes back and nothing else has changed.
3. Stops the app and copies the database to `/var/backups/sketchmaker/db/`.
4. Upgrades the database schema. See [Database migrations](#database-migrations).
5. Puts the new frontend live, starts the app and waits for its health check.
6. **If anything fails along the way, it undoes everything:** previous code, previous frontend, database as it was, and the app running again. Then it exits with an error. If the server loses power mid-update, the next `update.sh` still knows which version to go back to.
7. Updates nginx and certificates, then runs a dependency audit that only warns.

The app is normally down for the seconds between steps 3 and 5. Jobs running at fal are not lost: the poller picks them up again when the app returns.

## Rolling back and restoring

**To undo the last update** after it has succeeded, for example if you find a problem an hour later:

```bash
sudo bash /var/www/sketchmaker/server/update.sh --rollback
```

This returns to the previous code and puts the database back as it was before the update. **Anything saved since that update is lost**, apart from media files, so it asks you to confirm. The next `update.sh` moves forward again.

**To restore a backup:**

```bash
sudo bash /var/www/sketchmaker/server/restore.sh /var/lib/sketchmaker/backups/sketchmaker-YYYYmmdd-HHMMSS.db
```

It checks that the file is a healthy database, copies the current one first, and upgrades an older backup to the current schema. If the result does not come up, the previous database goes back.

## Moving to a new server

1. Run `install.sh` on the new server, with the same domain if you are keeping it. Point DNS at it first, or the certificate will not issue.
2. Stop both apps: `sudo systemctl stop sketchmaker`.
3. Copy from the old server to the new one, keeping the owner `www-data`:
   - `/var/lib/sketchmaker/` (use `rsync -a`)
   - `/var/www/sketchmaker/backend/.env`
4. On the new server: `sudo sketchmaker migrate`, then `sudo systemctl start sketchmaker`.

Copy `.env` with the data. Without the original `SECRET_KEY` and `ENCRYPTION_SALT`, the stored provider keys cannot be read and must be entered again.

**Moving from your computer to a server** works the same way: copy `backend/data/` to `/var/lib/sketchmaker/` and fix the owner with `sudo chown -R www-data:www-data /var/lib/sketchmaker`. For `.env`, copy only `SECRET_KEY`, `JWT_SECRET_KEY` and `ENCRYPTION_SALT` into the server's file, because its other settings differ.

**Old installs are not migrated.** The earlier multi-user Sketchmaker (the `master` branch and `sketch-react`) uses a different database and storage. There is no importer for its users, images or settings, and `install.sh` refuses to run over one. Use a fresh server.

## Docker

```bash
docker compose up -d --build
```

Then open `http://127.0.0.1:8000` and create your account. To use a different port, put `SKETCHMAKER_PORT=9000` in a `.env` file next to `docker-compose.yml`.

```bash
docker compose logs -f                                                  # logs
docker compose exec sketchmaker python -m app.cli reset-password        # owner commands
docker compose exec sketchmaker python -m app.cli backup                # back up now
docker compose cp sketchmaker:/data/backups ./backups                   # copy backups out
git pull && docker compose up -d --build                                # update
```

Updating upgrades the database when the container starts, with the same backup and automatic restore as everywhere else. To undo an update, check out the previous code and rebuild, then restore the `pre-migrate-*.db` file from `/data/backups` if the schema changed.

The container is locked down:

- runs as an unprivileged user, with every Linux capability dropped and no privilege escalation
- has a read-only filesystem, apart from the `/data` volume, the `/config` volume and a temporary `/tmp`
- is published on `127.0.0.1` only
- is built from base images pinned by digest and an allow-listed build context, so secrets and data cannot reach an image, and holds no secrets itself: they are created in the `config` volume on first start

The `config` volume holds the secrets and the `data` volume everything else. **Back up both, and keep them apart.** Removing the `config` volume makes stored provider keys unreadable.

**On a domain:** `server/install.sh` is the supported route. If you run Docker behind your own HTTPS proxy instead:

1. Set `TRUSTED_PROXIES` in the `.env` next to `docker-compose.yml`, to the proxy's address as the container sees it.
2. Have the proxy forward the original host and scheme, or the app rejects every write as cross-origin:

   ```nginx
   proxy_set_header Host $http_host;
   proxy_set_header X-Forwarded-Proto $scheme;
   proxy_set_header X-Forwarded-For $remote_addr;
   ```

3. Create the account from the terminal before exposing it: `docker compose exec sketchmaker python -m app.cli create-account`.

## Database migrations

The schema is managed by Alembic, and every route into the app goes through one procedure, `python -m app.cli migrate`: `uv run run.py`, the Docker entrypoint, `install.sh`, `update.sh` and `restore.sh` all call it.

1. If the schema is current, it does nothing.
2. If the database comes from **newer** code, it refuses and changes nothing.
3. It writes a backup, `pre-migrate-*.db`, to the `backups` folder. The newest 5 are kept, and nightly rotation does not touch them.
4. It runs the upgrade, then checks the revision, runs SQLite's integrity check, and confirms no new rows were left pointing at missing records.
5. **If anything fails, it puts the database back from the backup** and exits with an error. This matters because SQLite migrations are not transactional, so a failed one would otherwise leave a half-changed database.

**The app refuses to start** if the database does not match its code, so new code can never run on an old schema or the reverse. The app must be stopped while `migrate` runs. All the scripts do that for you.

### Writing a migration

After changing a model:

```bash
cd backend
uv run alembic revision --autogenerate -m "describe the change"
```

Then read the generated file, and:

- Make it safe on real data. Add columns as nullable or with a `server_default`, and fill existing rows in the migration.
- Leave `render_as_batch` to do its work: SQLite cannot alter most things in place, so it rebuilds the table.
- Do not call a network service or a provider from a migration.
- Do not edit a migration that has shipped. Add a new one.
- Run `uv run pytest`. The tests check that the migrations match the models.

Downgrades are not used. Going back means restoring the backup, which is what the rollback does.

### Changing data for existing installs

A migration can change rows as well as tables. This matters for anything first created by `app/seed.py`, such as the language model list: the seed only runs on an empty database, so **changing the list alone never reaches existing installs**. Do both:

1. Change `DEFAULT_MODELS` in `app/seed.py`, for new installs.
2. Add a data migration for existing ones. Copy `alembic/versions/0002_latest_models.py`.

A test fails if a new install and an upgraded one end up with different models or a different order.

Data migrations must respect what the owner did. `0002_latest_models` adds models, marks older ones as no longer the latest, and switches off models that providers have retired. It never changes the default or fallback model. It never overwrites a model the owner added or edited, and never brings back one they deleted. A retired model stays on if the owner has it selected.

The data in a migration is a frozen copy. Do not import `app/seed.py` into one: the migration must keep doing the same thing after that list changes again. A migration runs before the app starts, and the first run on a new install has no rows yet, so it must do nothing when the provider table is empty.

## Security

No software can be promised unhackable. This is what is in place, how it was checked, and what is left to you.

### In the app

| Area | What is in place |
|---|---|
| **Passwords** | bcrypt, at least 12 characters, never logged or echoed |
| **Sessions** | httpOnly, SameSite=Lax cookie, Secure on HTTPS. Signing out, or changing the password, ends every session |
| **Guessing** | 5 attempts a minute per address. 10 failures block that address for 15 minutes, with the same answer as a wrong password. 100 failures in 15 minutes lock the account, for attacks spread over many addresses |
| **Rate limits** | Per address, and per /64 network on IPv6: 1,200 reads, 240 writes and 60 requests that cost money each minute, plus tighter limits on Faceless Studio, Story Room and Motion Graphics |
| **Uploads** | A stranger's large request is refused from its headers, before any of it is stored |
| **Other websites** | Writes from other sites are refused by an Origin check. Locally, requests under other host names are refused, which stops DNS rebinding |
| **Account creation** | Local: in the browser, from this computer only. Public: only in the terminal, because the web page is switched off |
| **Provider keys** | Encrypted per field with Fernet and HKDF, never returned by any route, removed from logs, never in `.env` |
| **Files** | Every generated file requires a login. Path traversal is blocked. Stored SVG is rebuilt before serving |
| **Server-side requests** | Downloads from provider URLs cannot reach private addresses |
| **Browser** | A strict Content Security Policy with hashed inline scripts, and nosniff, frame, referrer, permissions and cross-origin policies. HSTS on HTTPS |
| **Errors** | Fixed sentences for people. Exceptions go only to the log |
| **Dependencies** | Pinned by lock files. `update.sh` audits them and checks for a known malicious LiteLLM release |

### On a server

| Layer | What is in place |
|---|---|
| **TLS** | TLS 1.2 and 1.3 only, modern ciphers, automatic renewal |
| **nginx** | Unknown host names are dropped. Per-address rate and connection limits, slow-client timeouts, upload size limits, and hidden files and script extensions blocked |
| **Firewall** | ufw allows only SSH, 80 and 443 |
| **fail2ban** | SSH, and repeated failed logins, are banned at the firewall. Behind the Cloudflare proxy, the login ban has no effect, and the app's own limit is what holds |
| **Service** | Runs as `www-data` with no capabilities, a read-only system, private `/tmp` and no access to home folders. It can write only to its data folder and cannot change its own code |
| **Updates** | Automatic security updates. `update.sh` warns about pending reboots, an unsupported Ubuntu, and SSH that accepts passwords |

### What is left to you

- **Use a long, unique password.** The whole team shares one login, so everyone who has it has everything, and there is no record of who did what. If someone leaves, change it with `sudo sketchmaker reset-password`.
- **Set spending limits with fal and your language model providers.** This is the real cap on damage: a stolen password could otherwise spend until you notice. The rate limits only slow it down.
- **Turn off SSH passwords** on the server. `update.sh` tells you how.
- **Run `update.sh` regularly**, so fixes reach the server.
- **Reboot when told.** Security updates install automatically, but some only take effect after a reboot.

### Not included

- Two-factor sign-in
- Separate logins for each person
- Protection from someone who has root on the server, or a copy of `.env` together with the database
- Protection from a large network flood. nginx limits one address at a time, so a distributed attack needs something like Cloudflare's proxy in front

### How it was checked

The automated tests cover sign-in, sessions, rate limits, key handling, uploads and the migration procedure. The running app was also attacked locally: guessing, flooding, path traversal, cross-site writes and DNS rebinding were all tried and refused. This is not a professional penetration test.

**The server scripts and the Docker configuration have not yet been run on a real Ubuntu server or in Docker.** They were checked with linters and config parsers, and each build step was rehearsed without containers. Try them on a throwaway server before relying on them.
