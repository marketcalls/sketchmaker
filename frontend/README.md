# Sketchmaker frontend

React 19, Vite 8, TypeScript 7 and Tailwind v4. FastAPI serves the built `dist/` folder, so
in normal use there is no separate frontend server.

```bash
npm install
npm run dev       # http://localhost:3000, proxying /api and /static to port 8000
npm run build     # typechecks, then writes dist/
```

For development, set `DEBUG=true` in `backend/.env`, because the dev proxy needs it to allow
writes. Design rules are in `../docs/DESIGN_SYSTEM.md`.
