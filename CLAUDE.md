# Sketchmaker: working notes

Single-user, self-hosted AI image and video app. `backend/` (Python, FastAPI, SQLAlchemy 2, SQLite), `frontend/` (React 19, Vite 8, TypeScript 7, Tailwind v4). One process on one port: FastAPI serves the built frontend. `./run.sh` starts everything locally; `server/install.sh` publishes it on a domain, and `docker-compose.yml` runs it in a container. See `docs/DEPLOYMENT.md`.

It is a strip-down of a multi-user SaaS at `/Users/openalgo/sketch-demo/sketch-react`, which remains the reference for removed code. Do not bring back accounts, roles, admin pages, payments, credits, subscriptions, presentations, the public gallery, S3, Redis or email. **Consult the owner before removing anything else.**

**Faceless Studio is deferred, not abandoned.** Its video pipeline and pages are in the reference repo. `services/faceless/` keeps what other features use (catalog, consent, errors, media, scenes, views, activity), along with `FacelessCharacter`, `FacelessActivity` and the character routes. `services/faceless/prompts.py` and `components/faceless/CharacterEditorDialog.tsx` have no callers yet; they are kept for the return.

## Configuration

`.env` holds only what is needed before the database can be read: `SECRET_KEY`, `JWT_SECRET_KEY`, `ENCRYPTION_SALT`, `DATA_DIR`, `HOST`, `PORT`, `TRUSTED_PROXIES`, `DEBUG`, `LOG_LEVEL`. **Provider API keys never go in `.env`.** They are stored encrypted in the database behind Settings. A new integration adds a key column and a Settings entry, not a config field. The app refuses to start on missing, short or placeholder secrets. `.env` wins over exported variables; in Docker it holds only the secrets (`init --secrets-only`), so the rest comes from the environment.

`TRUSTED_PROXIES` is the switch between the two modes. Empty is local: only loopback `Host` names are served (`security.host_allowed`, which stops DNS rebinding) and the account is created in the browser. Set is public: the proxy picks the names, and the web setup route is off, so the account is created with `python -m app.cli create-account`. **Do not reopen web setup on a public site:** whoever gets there first would own it.

## Deployment

`server/common.sh` holds every server step once, called from both `install.sh` and `update.sh`, so a new server and an existing one converge. Anything new goes there, idempotent, and never calls `exit`. nginx only terminates TLS and limits abuse; the app serves everything, including its own security headers. Run app commands on a server as `www-data` (`sudo sketchmaker <command>`, or `sm_as_app`), or files in the data folder end up owned by root.

Neither the server scripts nor the Docker setup have been run on real Ubuntu or in Docker yet. They were only linted and rehearsed. Say so until someone has.

## Things that bite

- **SQLite has one writer.** No network call or ffmpeg between the first write and commit. Pattern: read, commit, call the provider, then lock, re-check, apply, commit (`services/motion_graphics/jobs.py` is the model). Do not set `isolation_level=None` in `database.py`: pysqlite's default keeps reads out of a transaction, so writes do not fail with `SQLITE_BUSY_SNAPSHOT`, which `busy_timeout` cannot retry. Use `apply_row_lock(query)`, never `with_for_update`.
- **One worker, so one event loop.** A blocking call in `async def` freezes the whole app. Use `asyncio.to_thread`, `run_in_threadpool` or a plain `def` route for anything that calls a provider.
- **fal cannot read local files.** `services/fal_inputs.py` uploads own `/static/` and private media files to fal storage inside the `fal_client` wrappers, so callers pass local URLs. The database keeps local URLs. Never store a fal storage URL as the file's location.
- **Polling only.** There are no webhooks. The scheduler polls every 30 seconds. A finished job is settled only by whoever wins `job_state.claim_job`.
- **Paid results are not thrown away on a temporary failure.** `job_state.fail_claimed_job` hands a job back to the poller on network errors, a missing or rejected key, or a locked database (`is_temporary_failure`), and returns False. 5xx answers are retried a limited number of times because fal can return one for a run that truly failed. Claims from a previous run are released at startup.
- **Job and render concurrency.** The scheduler runs in-process (`scheduler_service.job_scheduler`). `render_timeline` always runs inside `render_queue.render_slot()`.
- **`/static` is an authenticated route**, not a public mount (`routers/media.py`). `<img>` and `<video>` rely on the session cookie, which is why it lasts 30 days.
- **Stored secrets** use `utils/secret_box.py` (Fernet, HKDF per field). Changing `SECRET_KEY` or `ENCRYPTION_SALT` makes stored keys unreadable until re-entered. Keys are write-only: no endpoint returns one.
- **fal client:** use `fal_keys.get_sync_client()`, never `os.environ["FAL_KEY"]`. ffmpeg subprocesses get `utils.security.scrubbed_env()`.
- **Stored SVG is untrusted** until `utils/svg_sanitize.py` has rebuilt it.
- **Server-side downloads** of provider URLs go through `services/url_fetch.py`, which blocks private addresses. Own files are read from disk with `storage_service.read_local_media`. Do not weaken the check.
- **Error text shown to users is written for people.** Log the exception and return a fixed sentence. `frontend/src/utils/errors.ts` trusts a detail only on replies carrying `X-SM-Origin: app`.
- **Prices are estimates.** Every model or step needs a `USD_COSTS` entry in `services/pricing.py`, which also validates model names. `record_usage` is for fal and Sarvam spending, on success only. LLM calls are logged by `litellm_client` into `llm_usage`; do not record them twice.
- **Consent gates** on characters stay: they are about likeness, not billing.
- **Media uploads** are one control, `components/media/` (`MediaDropzone`, `useMediaPicker`). Do not add a second file input.
- **Alembic:** after changing a model, run `uv run alembic revision --autogenerate`. `tests/` checks the migrations match the models. Migrations on SQLite are not transactional, so always upgrade through `python -m app.cli migrate` (`services/migration_service.py`), never `alembic upgrade head`: it backs up first and restores on failure. The app refuses to start if the schema does not match the code.
- **Rate limits are in three layers** (`middleware/rate_limiter.py`): a per-address ceiling on all of `/api` with a tighter one for requests that cost money, slowapi decorators on sign-in and costly routes, and failed logins per address. A new router that spends money goes in `PAID_ROUTERS`. Do not lower the account-wide lock (`LOGIN_MAX_FAILED_ATTEMPTS`) back near ten: a stranger who knows the username could then lock everyone out.
- **Logging:** no `print()` in app code. It skips the key redaction filter, and prompts do not belong in production logs. Use `logger.debug`.
- **`npm run lint` is broken** under TypeScript 7. `npm run build` typechecks.

## Design system

Dark-first "Calm Studio". Tokens only, never raw `text-white`, `bg-gray-*` or hex values. One lime accent (`primary`) for the one primary action. Nothing glows, pulses, floats or sweeps; motion is short fades with at most 8 px travel. No emojis in code or UI. Full rules in `docs/DESIGN_SYSTEM.md`.

## Verify before claiming

```bash
cd backend && uv run pytest            # includes an AST check that every import resolves, even inside functions
cd backend && uvx ruff check --select F821,F811 app
cd frontend && npx tsc -b --noEmit && npm run build
```

Tests stub the providers. Nothing here proves a real fal or LLM call works; say so when reporting.
