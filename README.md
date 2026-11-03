# Sketchmaker

AI image and video generation you host yourself. FastAPI, SQLite and React, running as one process on one port. There is one login, no accounts to manage, and no external services to set up beyond the AI providers you choose.

You pay providers directly with your own keys. Your database and generated files stay on your disk.

Built with React 19, Vite 8, TypeScript 7, Tailwind v4, FastAPI and SQLAlchemy 2.

## Three ways to run it

| | For | Command |
|---|---|---|
| **On your computer** | One person | `./run.sh` |
| **Docker** | One person, isolated from the rest of the computer | `docker compose up -d --build` |
| **On a server, on your domain** | A team | `sudo bash server/install.sh` |

Publishing on a domain, updates, rollback, moving servers and Docker are all in **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

## Quick start on your computer

You need [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js 22 or newer, and ffmpeg (for video tools and renders).

```bash
./run.sh
```

The first run creates `backend/.env` with random secrets, builds the frontend, creates the database, and prints the address:

```
First run. Create your account at:
  http://127.0.0.1:8000
```

Open it and choose a username and a password of at least 12 characters. Then go to **Settings > API keys** and add:

- a **fal** key, for images and video
- a **language model** key (OpenAI, Anthropic, Gemini, Groq, xAI, Cerebras, OpenRouter or Baseten), for Magic Prompt, the story tools and other writing features
- a **Sarvam** key, only if you want Bulbul voices for Indian languages

Pick your preferred language model under **Settings > AI model**.

## Tools

Generate, Magix, Virtual Try-On, Explainer, Logo, Remove Background, Reduce and Convert, Motion Control, Recast, Lip Sync, Story Room, Quick clip, Subtitles, Motion Graphics, My Gallery, My Assets, My Jobs and Usage.

Faceless Studio is not included yet. It is planned for a later version.

## Costs

Prices on buttons and in dialogs are **estimates** from a table built into the app (`backend/app/services/pricing.py`), not live quotes. The **Usage** page adds up estimated spending and can look up fal's current unit price for each model. Your provider's invoice is the real number.

Language model spending is estimated from token counts where the model's price is known. Where it is not, Usage shows tokens only.

## Where your data lives

| Path | Contents |
|---|---|
| `backend/.env` | Secrets that encrypt your keys and sign your session. No provider keys. |
| `backend/data/sketchmaker.db` | Settings, job history and your provider keys, encrypted |
| `backend/data/static/` | Generated and uploaded files |
| `backend/data/private_media/` | Files that must never be served directly |
| `backend/data/backups/` | Nightly database backups, and the copy taken before each upgrade |

On a server, the data is in `/var/lib/sketchmaker` instead. In Docker, it is in the `data` and `config` volumes.

**Files you use as inputs are uploaded to fal's storage when a job runs**, because fal cannot read your disk. Results are downloaded back to your data folder.

## Commands

Run these from `backend/`. On a server, use `sudo sketchmaker <command>` instead.

```bash
uv run python -m app.cli reset-password   # forgot your password
uv run python -m app.cli unlock           # clear an account lock
uv run python -m app.cli logout-all       # end every session
uv run python -m app.cli backup           # back up the database now
uv run python -m app.cli migrate          # upgrade the database (./run.sh does this for you)
uv run python -m app.cli create-account   # create the account from the terminal
```

## Backups

The database is backed up every night at 03:00 UTC to the `backups` folder, keeping the latest 14. **Generated files and `.env` are not included**, so copy the `static` folder and `.env` yourself. Keep `.env` apart from your backups: together they can decrypt your keys.

To restore on your computer, stop the app and replace the database with a backup:

```bash
cp backend/data/backups/sketchmaker-YYYYmmdd-HHMMSS.db backend/data/sketchmaker.db
rm -f backend/data/sketchmaker.db-wal backend/data/sketchmaker.db-shm
```

On a server, use `server/restore.sh`. Restoring needs the `.env` the backup was made with. With a different one, the app still works but your provider keys must be entered again.

## Security

No software can be promised unhackable, so this is what is in place and what remains your job. Details are in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#security).

- **Sign-in:** bcrypt passwords of at least 12 characters, and a session cookie scripts cannot read. Ten wrong passwords block that address for 15 minutes; 100 from anywhere lock the account.
- **Rate limits:** on every API route per address, tighter on anything that costs money, and tightest on sign-in. On a server, nginx and fail2ban add more in front.
- **Your keys:** encrypted in the database, never returned by any page, removed from logs, and never in `.env`.
- **Your files:** every generated file requires a login, including direct links.
- **On your computer:** the app answers only on `127.0.0.1`, and refuses other sites reaching it through tricks such as DNS rebinding. To use it from other computers, publish it on a domain with HTTPS.
- **On a server:** HTTPS only, a firewall, a sandboxed service, automatic security updates, and the account is created in the terminal, so nobody can claim it first.

**Your part:** use a long, unique password, because everyone on the team shares this one login. Set spending limits with fal and your language model providers, since a stolen password could spend until you notice. There is no two-factor sign-in.

Do not change `SECRET_KEY` or `ENCRYPTION_SALT` once keys are stored. If you do, re-enter your keys. Changing `JWT_SECRET_KEY` only signs you out.

## Outbound connections

The app connects to fal, the language model providers and Sarvam you add keys for, and fal storage for input files. The browser loads fonts from Google Fonts. The LiteLLM library fetches its model price list from GitHub when the app starts.

## Development

```bash
# Backend, with DEBUG=true in backend/.env (the Vite proxy needs it to allow writes)
cd backend && uv run uvicorn app.main:app --reload --port 8000

# Frontend, on http://localhost:3000
cd frontend && npm install && npm run dev

# Checks
cd backend && uv run pytest
cd frontend && npx tsc -b --noEmit && npm run build
```

After changing a model, add a migration. See [Writing a migration](docs/DEPLOYMENT.md#writing-a-migration).

## Known limits

- **Cancel on My Jobs** stops the app tracking a job and discards its result. It does not cancel the request at fal, so a job fal has already started can still be billed.
- **Retry on My Jobs** is available for video and lip sync jobs only.
- Characters are saved from a story in Story Room. Creating or editing them directly returns with Faceless Studio.
- Backups have no screen in the app yet.
- Everyone signs in with one shared login, so the gallery, jobs and keys are shared too, and there is no record of who did what.
- If a result cannot be fetched because of a network problem or a missing key, the job keeps retrying for up to 6 hours from when it started.

## License

See [LICENSE](LICENSE).
