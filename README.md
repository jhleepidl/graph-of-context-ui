# Graph-of-Context Run Studio

Graph-of-Context is a graph-first workspace for execution observability.
It keeps the generic `Node`/`Edge` model and adds an additive Run Studio control-plane projection layer.

## Product Surfaces
- `Run Studio` (default): now/status, runtime team, attached skills, context packs, skill usage, context decisions, evidence.
- `Graph`: manual graph editing and fold/unfold.
- `Raw Trace`: execution trace and timeline.
- `Artifacts` and `Advanced` tools remain available.

## Skill-Aware Model (Additive)
- `Agent = role`
- `Skill = reusable expertise package`
- `TeamPlan = roles + attached skills + policy`
- `ContextPack = shared + role-specific + skill-specific context`
- `RuntimeAgent = instantiated role with attached skills`

This is projection-only over the existing graph backend; no new graph stack is required.

## Docs Map
- Project overview: this file.
- Backend/API/service notes: [`backend/README.md`](backend/README.md)
- Frontend architecture notes: [`frontend/README.md`](frontend/README.md)
- Operator usage: [`UI_USAGE_GUIDE.md`](UI_USAGE_GUIDE.md)
- Skill UI supplement: [`SKILLS_IN_UI_GUIDE.md`](SKILLS_IN_UI_GUIDE.md)

## Quick Start
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

