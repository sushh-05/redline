# Redline

Redline is a deterministic simulator for testing AI-agent spending policies before an agent gets access to money.

It is a simulator, not a wallet. Redline does not hold funds, connect to a bank, authorize payments, or move money. It evaluates fixed payment scenarios against a policy and reports whether the scenario is safe, escalated, blocked, or escaped.

## Live demo

Try Redline online: [redline-pbv.vercel.app](https://redline-pbv.vercel.app/)

## Build proof

Redline was built with Wispr Flow. Watch the demo and build walkthrough:

[![Redline demo](https://img.youtube.com/vi/_hWatdY0rw0/hqdefault.jpg)](https://youtu.be/_hWatdY0rw0)

[Watch the Redline demo on YouTube](https://youtu.be/_hWatdY0rw0)

## Run it locally

Install [uv](https://docs.astral.sh/uv/) if it is not already installed, then from the project directory run:

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 in a browser. The API is also available at `/evaluate`, `/run`, `/pass`, `/patch`, `/custom-run`, `/simulate`, `/adaptive-run`, and `/multi-agent-run`.

The React UI includes policy presets, risk scoring, recommendations, attack filters, expandable payment timelines, workspace-scoped local run history, JSON and print/PDF reports, shareable policy links, a custom attack builder, a scenario library, a seeded stress test for 100 randomized payment patterns, adaptive-attacker mode, shared-budget multi-agent testing, allowed-recipient rules, time windows, and per-recipient daily caps. GitHub Actions runs the backend tests and React production build on pushes and pull requests.

### Optional AI copilot

The **Ask the policy copilot** panel is optional. AI explains attack results and suggests patches; the deterministic policy engine remains the decision source.

Recommended hosted option: Gemini Developer API. Set the key on the backend only:

```powershell
$env:GEMINI_API_KEY = "your-key"
uv run uvicorn app.main:app --reload
```

Use the exact variable spelling `GEMINI_API_KEY`. The loader also accepts the existing `GEMINI_API_key` spelling for convenience. Groq is the only fallback provider and uses `GROQ_API_KEY`. If neither provider is available, Redline returns a clear `503` response; it does not silently switch providers. The frontend never receives an API key.

### Use Redline as a spending guard for any AI agent

Redline exposes `POST /guard` as a provider-neutral REST/OpenAPI tool. Before a payment tool executes a transaction, any agent—ChatGPT, Claude, Gemini, Groq, or your own application—sends the proposed amount, recipient, time, policy, and recent history to `/guard`.

The response is explicit:

- `allow` / `approved: true` — the payment tool may continue.
- `review` / `requires_confirmation: true` — ask the user for confirmation first.
- `block` / `approved: false` — do not execute the payment.

For ChatGPT Actions, Claude tool use, Gemini function calling, Groq tool use, or a custom agent, deploy Redline to an HTTPS URL and import its `/openapi.json` or define the same JSON schema in the provider’s tool configuration. Add an instruction such as: “Always call `/guard` before any spending action. Never execute a payment after `block`. Ask for confirmation after `review`.” A local `127.0.0.1` server is not reachable by hosted agents until it is exposed through a secure HTTPS tunnel or deployed to a server.

The UI is a React app built with Vite. To work on the frontend with hot reload, run the API in one terminal and the frontend in another:

```bash
# terminal 1
uv run uvicorn app.main:app --reload

# terminal 2
npm install
npm run dev
```

For the production UI served directly by FastAPI, build the frontend:

```bash
npm run build
```

The build output is written to `app/static/`, which is served at `/`.

If you already have the environment prepared, the short form is:

```bash
uvicorn app.main:app --reload
```

## Run tests

```bash
uv run pytest
```

## The three attacks

Redline currently tests three fixed attack patterns. They are intentionally small, deterministic scenarios—not a complete model of every way a policy could be abused.

- **Split-second** sends four payments of `$4.99`, eight minutes apart. It tests whether an agent can split a larger spend into smaller payments that each stay below the approval threshold.
- **Boundary** sends `$4.99`, `$5.00`, and `$5.01` at the same time. It checks threshold behavior around the exact approval boundary.
- **Velocity** sends ten payments of `$1.50` within five minutes. It tests whether a rolling-hour limit catches rapid, repeated spending.

These attacks have important limitations: they use one recipient, fixed amounts and timings, and a small set of policy rules. They do not simulate real payment rails, identity changes, multiple currencies, retries, concurrent agents, or adaptive attackers. Treat the results as a focused policy smoke test, not as a security guarantee.

## Built with Wispr Flow

Wispr Flow was used to build Redline by making it possible to describe and iterate on the product, policy language, attack scenarios, and interface through voice. The app itself remains intentionally simple: policy decisions are made by deterministic Python code, while the UI accepts plain-language policy descriptions and turns them into testable limits.

## Try it in 60 seconds

1. Start the app:

   ```bash
   uv run uvicorn app.main:app --reload
   ```

2. Open http://127.0.0.1:8000.

3. In **Speak Your Policy**, enter the demo policy:

   ```text
   Set a daily limit of $100, approval above $5, and a rolling hour limit of $25.
   ```

4. Click **Run attacks**. You should see the split-second, boundary, and velocity cards with their outcomes.

5. In **Speak Your Patch**, try:

   ```text
   Set a daily limit of $100, approval above $25, and a rolling hour limit of $25.
   ```

6. Click **Apply patch** to see the policy difference and which attack outcomes changed.

## Project layout

- `app/engine.py` — deterministic policy evaluation
- `app/attacks.py` — fixed attack scenarios
- `app/main.py` — FastAPI routes and the web UI
- `app/static/` — plain HTML, CSS, and JavaScript interface
- `tests/` — API, engine, attack, and scenario tests
