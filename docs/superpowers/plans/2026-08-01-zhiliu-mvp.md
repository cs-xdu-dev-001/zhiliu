# 知流MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个可部署到VPS、在手机上使用的单用户情报台，用Hermes完成热点与论文情报的搜索和总结。

**Architecture:** React单页应用通过Nginx访问FastAPI REST API，FastAPI使用SQLite保存订阅、情报、简报和任务记录。后端通过Hermes的`/v1/runs`接口异步执行Agent任务，APScheduler只负责根据订阅规则触发后端任务。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy 2、Alembic、APScheduler、httpx、Pydantic Settings、PyJWT、pwdlib/Argon2、pytest；React 19、TypeScript、Vite、React Router、TanStack Query、Lucide React、Vitest、Playwright；Docker Compose、Nginx。

---

## File Structure

```text
知流/
├─ backend/
│  ├─ app/
│  │  ├─ api/{auth,subscriptions,items,briefings,runs}.py
│  │  ├─ core/{config,security}.py
│  │  ├─ services/{hermes,scheduler,run_service}.py
│  │  ├─ {db,models,schemas,seed,main}.py
│  ├─ tests/
│  ├─ alembic/
│  ├─ pyproject.toml
│  └─ Dockerfile
├─ frontend/
│  ├─ src/
│  │  ├─ components/{AppShell,BottomNav,ItemCard,EmptyState}.tsx
│  │  ├─ pages/{Login,Home,Feed,Subscriptions,Reports,Tasks}.tsx
│  │  ├─ {api,types,router,main,styles}.ts(x)
│  ├─ e2e/
│  ├─ package.json
│  └─ Dockerfile
├─ deploy/nginx.conf
├─ docs/
├─ .env.example
├─ docker-compose.yml
└─ README.md
```

### Task 1: Backend foundation and database

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/core/config.py`
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Write the failing health test**

```python
def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "zhiliu"}
```

- [ ] **Step 2: Run the test and confirm collection/import failure**

Run: `cd backend; uv run pytest tests/test_health.py -v`
Expected: FAIL because `app.main` does not exist.

- [ ] **Step 3: Implement settings, SQLAlchemy session and core models**

Create five SQLAlchemy models with these stable fields:

```python
class User: id, username, password_hash, created_at
class Subscription: id, name, kind, keywords_json, schedule, prompt, enabled, last_run_at, next_run_at
class IntelligenceItem: id, subscription_id, kind, title, summary, url, source, published_at, keywords_json, reason, importance, fingerprint, is_read, is_saved, is_ignored, created_at
class Briefing: id, subscription_id, title, kind, content, item_count, period_start, period_end, created_at
class TaskRun: id, subscription_id, hermes_run_id, status, started_at, finished_at, duration_ms, error_message, raw_output
```

`create_app()` must register `/api/health`, create tables for local development, and expose lifespan hooks without starting the scheduler in tests.

- [ ] **Step 4: Run the health test**

Run: `cd backend; uv run pytest tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 5: Commit backend foundation**

```bash
git add backend
git commit -m "feat: scaffold backend and data model"
```

### Task 2: Single-user authentication

**Files:**
- Create: `backend/app/core/security.py`
- Create: `backend/app/api/auth.py`
- Create: `backend/app/schemas.py`
- Create: `backend/app/seed.py`
- Create: `backend/tests/test_auth.py`

- [ ] **Step 1: Write authentication tests**

```python
def test_login_sets_cookie(client, seeded_user):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "test-pass"})
    assert response.status_code == 204
    assert "zhiliu_session=" in response.headers["set-cookie"]

def test_protected_endpoint_rejects_anonymous(client):
    assert client.get("/api/auth/me").status_code == 401
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `cd backend; uv run pytest tests/test_auth.py -v`
Expected: FAIL with missing routes.

- [ ] **Step 3: Implement authentication**

Implement `POST /api/auth/login`, `POST /api/auth/logout`, and `GET /api/auth/me`. Hash passwords with Argon2; issue a signed JWT in a `HttpOnly`, `SameSite=Lax` cookie; set `Secure` from configuration. Seed the only user from `ADMIN_USERNAME` and `ADMIN_PASSWORD` when the database is empty.

- [ ] **Step 4: Verify valid, invalid and anonymous cases**

Run: `cd backend; uv run pytest tests/test_auth.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit authentication**

```bash
git add backend/app backend/tests/test_auth.py
git commit -m "feat: add single-user authentication"
```

### Task 3: Subscription, feed and briefing APIs

**Files:**
- Create: `backend/app/api/subscriptions.py`
- Create: `backend/app/api/items.py`
- Create: `backend/app/api/briefings.py`
- Create: `backend/tests/test_subscriptions.py`
- Create: `backend/tests/test_items.py`

- [ ] **Step 1: Write CRUD and item-state tests**

```python
def test_create_subscription(auth_client):
    payload = {"name": "Agent论文", "kind": "paper", "keywords": ["LLM Agent"], "schedule": "0 9 * * 1", "prompt": "检索过去7天的论文", "enabled": True}
    response = auth_client.post("/api/subscriptions", json=payload)
    assert response.status_code == 201
    assert response.json()["keywords"] == ["LLM Agent"]

def test_mark_item_read(auth_client, seeded_item):
    response = auth_client.patch(f"/api/items/{seeded_item.id}", json={"isRead": True})
    assert response.status_code == 200
    assert response.json()["isRead"] is True
```

- [ ] **Step 2: Run tests and confirm missing routes**

Run: `cd backend; uv run pytest tests/test_subscriptions.py tests/test_items.py -v`
Expected: FAIL with 404.

- [ ] **Step 3: Implement API contracts**

Implement authenticated endpoints:

```text
GET/POST /api/subscriptions
GET/PUT/DELETE /api/subscriptions/{id}
GET /api/items?kind=&state=&subscriptionId=&limit=&offset=
PATCH /api/items/{id}  body: isRead/isSaved/isIgnored
GET /api/briefings?kind=&limit=&offset=
GET /api/briefings/{id}
GET /api/dashboard
```

Use camelCase response aliases, validate cron expressions, cap page size at 100, and return 404 for missing records.

- [ ] **Step 4: Run API tests**

Run: `cd backend; uv run pytest tests/test_subscriptions.py tests/test_items.py -v`
Expected: PASS.

- [ ] **Step 5: Commit domain APIs**

```bash
git add backend/app backend/tests
git commit -m "feat: add intelligence and subscription APIs"
```

### Task 4: Hermes client and structured result parsing

**Files:**
- Create: `backend/app/services/hermes.py`
- Create: `backend/app/services/run_service.py`
- Create: `backend/tests/test_hermes.py`
- Create: `backend/tests/fixtures/hermes_success.json`

- [ ] **Step 1: Write contract tests with mocked HTTP**

```python
async def test_execute_returns_structured_briefing(mock_transport, hermes_client):
    result = await hermes_client.execute("find papers")
    assert result.briefing.title == "Agent论文周报"
    assert result.items[0].url == "https://arxiv.org/abs/2608.00001"

def test_fingerprint_is_stable():
    assert item_fingerprint("Title", "https://example.com/a") == item_fingerprint(" Title ", "https://example.com/a/")
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `cd backend; uv run pytest tests/test_hermes.py -v`
Expected: FAIL because the Hermes service is missing.

- [ ] **Step 3: Implement Hermes integration**

`HermesClient.execute(prompt)` must:

```text
POST /v1/runs with prompt and a strict JSON output instruction
poll GET /v1/runs/{run_id} until completed/failed/timeout
parse output after stripping optional Markdown fences
validate BriefingResult with Pydantic
raise HermesUnavailable, HermesTimeout or HermesInvalidOutput
```

Use bearer authentication, a 10-second connect timeout, configurable overall timeout, and no automatic HTTP retry inside the client. Normalize URLs and calculate SHA-256 fingerprints in `run_service.py`; ignore duplicate fingerprints rather than overwriting user state.

- [ ] **Step 4: Run Hermes contract tests**

Run: `cd backend; uv run pytest tests/test_hermes.py -v`
Expected: success, timeout, failed run and malformed output tests PASS.

- [ ] **Step 5: Commit Hermes adapter**

```bash
git add backend/app/services backend/tests
git commit -m "feat: integrate Hermes run API"
```

### Task 5: Scheduling, manual runs and demo seed

**Files:**
- Create: `backend/app/services/scheduler.py`
- Create: `backend/app/api/runs.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/seed.py`
- Create: `backend/tests/test_runs.py`

- [ ] **Step 1: Write run lifecycle tests**

```python
def test_manual_run_creates_task(auth_client, subscription, fake_hermes):
    response = auth_client.post(f"/api/subscriptions/{subscription.id}/run")
    assert response.status_code == 202
    task = auth_client.get("/api/runs?limit=1").json()[0]
    assert task["status"] in {"queued", "running", "success"}

def test_duplicate_active_run_is_rejected(auth_client, running_task):
    response = auth_client.post(f"/api/subscriptions/{running_task.subscription_id}/run")
    assert response.status_code == 409
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `cd backend; uv run pytest tests/test_runs.py -v`
Expected: FAIL with missing endpoint.

- [ ] **Step 3: Implement scheduler and execution lifecycle**

Create one `AsyncIOScheduler` on application startup. Rebuild jobs from enabled subscriptions, update jobs after CRUD operations, set `max_instances=1` and `coalesce=True`, and execute tasks through `RunService`. Retry exactly once for Hermes connectivity/timeouts, never retry invalid output. Provide:

```text
POST /api/subscriptions/{id}/run
GET /api/runs?limit=&offset=
GET /api/runs/{id}
GET /api/system/hermes-health
```

Seed three subscriptions, eight intelligence items, two briefings and four task runs only when `DEMO_MODE=true` and the relevant tables are empty.

- [ ] **Step 4: Verify lifecycle and full backend suite**

Run: `cd backend; uv run pytest -v`
Expected: all tests PASS with no live Hermes call.

- [ ] **Step 5: Commit scheduling**

```bash
git add backend
git commit -m "feat: schedule and track intelligence runs"
```

### Task 6: Frontend foundation and login

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/router.tsx`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/pages/Login.tsx`
- Create: `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/components/BottomNav.tsx`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/pages/Login.test.tsx`

- [ ] **Step 1: Write the login interaction test**

```tsx
it("submits credentials and opens the dashboard", async () => {
  render(<Login />);
  await userEvent.type(screen.getByLabelText("用户名"), "admin");
  await userEvent.type(screen.getByLabelText("密码"), "secret");
  await userEvent.click(screen.getByRole("button", { name: "登录" }));
  expect(mockNavigate).toHaveBeenCalledWith("/");
});
```

- [ ] **Step 2: Run Vitest and confirm failure**

Run: `cd frontend; npm test -- --run`
Expected: FAIL because the UI is not implemented.

- [ ] **Step 3: Implement the application shell**

Configure React Router and TanStack Query. `api.ts` must use `credentials: "include"`, convert non-2xx responses into typed errors, and redirect 401 responses to `/login`. Build a compact top bar and a four-item fixed mobile bottom navigation using Lucide icons: 首页、情报、报告、设置。 Desktop uses a restrained left sidebar. Use CSS variables with neutral ink, white, cool gray, signal green and amber; no gradients or decorative blobs.

- [ ] **Step 4: Run frontend unit tests**

Run: `cd frontend; npm test -- --run`
Expected: PASS.

- [ ] **Step 5: Commit frontend foundation**

```bash
git add frontend
git commit -m "feat: scaffold mobile web client"
```

### Task 7: Dashboard, feed and reports

**Files:**
- Create: `frontend/src/pages/Home.tsx`
- Create: `frontend/src/pages/Feed.tsx`
- Create: `frontend/src/pages/Reports.tsx`
- Create: `frontend/src/components/ItemCard.tsx`
- Create: `frontend/src/components/EmptyState.tsx`
- Create: `frontend/src/pages/Feed.test.tsx`

- [ ] **Step 1: Write feed behavior tests**

```tsx
it("marks an intelligence item as read", async () => {
  render(<Feed />);
  await screen.findByText("Agent框架发布新版本");
  await userEvent.click(screen.getByRole("button", { name: "标记已读" }));
  expect(mockPatch).toHaveBeenCalledWith(expect.stringContaining("/api/items/"), { isRead: true });
});
```

- [ ] **Step 2: Run test and confirm failure**

Run: `cd frontend; npm test -- --run src/pages/Feed.test.tsx`
Expected: FAIL because Feed is missing.

- [ ] **Step 3: Implement information views**

Home shows four compact metrics, the three highest-importance unread items, the latest briefing and recent task health. Feed uses horizontal category tabs and state filters, with stable item-card dimensions and icon buttons for save/read/ignore. Reports shows briefing rows and a readable detail view with source links. Loading, empty and error states must not resize the page shell.

- [ ] **Step 4: Run frontend tests**

Run: `cd frontend; npm test -- --run`
Expected: PASS.

- [ ] **Step 5: Commit information views**

```bash
git add frontend/src
git commit -m "feat: add intelligence feed and reports"
```

### Task 8: Subscription and task management

**Files:**
- Create: `frontend/src/pages/Subscriptions.tsx`
- Create: `frontend/src/pages/Tasks.tsx`
- Create: `frontend/src/pages/Subscriptions.test.tsx`
- Modify: `frontend/src/router.tsx`

- [ ] **Step 1: Write subscription form tests**

```tsx
it("validates and creates a subscription", async () => {
  render(<Subscriptions />);
  await userEvent.click(screen.getByRole("button", { name: "新建订阅" }));
  await userEvent.type(screen.getByLabelText("订阅名称"), "RAG论文");
  await userEvent.click(screen.getByRole("button", { name: "保存" }));
  expect(mockPost).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run test and confirm failure**

Run: `cd frontend; npm test -- --run src/pages/Subscriptions.test.tsx`
Expected: FAIL because the page is missing.

- [ ] **Step 3: Implement management pages**

Subscriptions displays compact rows with an enabled toggle, schedule label, last-run state and overflow actions. Use a bottom sheet on mobile and a modal on desktop for create/edit fields. Tasks displays status, subscription, start time, duration and concise error; provide refresh and manual-run icon actions with tooltips. Do not expose Hermes keys or raw prompts on the dashboard.

- [ ] **Step 4: Run frontend tests**

Run: `cd frontend; npm test -- --run`
Expected: PASS.

- [ ] **Step 5: Commit management pages**

```bash
git add frontend/src
git commit -m "feat: manage subscriptions and task runs"
```

### Task 9: Containers, proxy and operations documentation

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `deploy/nginx.conf`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `README.md`
- Create: `backend/tests/test_config.py`

- [ ] **Step 1: Write production configuration tests**

```python
def test_production_rejects_default_secrets(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "change-me")
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings()
```

- [ ] **Step 2: Run the configuration test and confirm failure**

Run: `cd backend; uv run pytest tests/test_config.py -v`
Expected: FAIL until production validation is added.

- [ ] **Step 3: Add deployment assets**

Compose must run `backend`, `frontend` and `nginx`; persist `/data/zhiliu.db`; expose only Nginx; pass Hermes base URL as `http://host.docker.internal:8642` with Linux `host-gateway`; add health checks and restart policies. Nginx must proxy `/api/` to FastAPI, serve the built SPA, set security headers, and apply a 10 MB request limit. README must document local development, Hermes API server configuration, first login, Docker deployment to `/opt/zhiliu`, HTTPS reverse proxy expectations, backup of the SQLite volume, and key rotation.

- [ ] **Step 4: Verify tests and Compose rendering**

Run: `cd backend; uv run pytest -v`
Expected: PASS.

Run: `docker compose config`
Expected: valid rendered configuration with no missing required variable in demo mode.

- [ ] **Step 5: Commit deployment support**

```bash
git add .
git commit -m "ops: add container deployment"
```

### Task 10: End-to-end and responsive verification

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/core-flow.spec.ts`
- Modify: `README.md`

- [ ] **Step 1: Write the end-to-end core flow**

```ts
test("mobile user reviews intelligence and triggers a subscription", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("用户名").fill("admin");
  await page.getByLabel("密码").fill("demo-password");
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page.getByText("今日情报")).toBeVisible();
  await page.getByRole("link", { name: "设置" }).click();
  await page.getByRole("button", { name: "立即执行" }).first().click();
  await expect(page.getByText(/queued|running|已排队|执行中/)).toBeVisible();
});
```

- [ ] **Step 2: Run the E2E test and fix only observed failures**

Run: `cd frontend; npx playwright test`
Expected: PASS on Chromium mobile and desktop projects.

- [ ] **Step 3: Inspect screenshots and layout metrics**

Capture 390x844 and 1440x900 screenshots for login, home, feed, reports and settings. Verify no horizontal overflow, text overlap, blank regions, unstable card heights or obscured content behind the bottom navigation. Use Playwright DOM checks for `document.documentElement.scrollWidth === document.documentElement.clientWidth`.

- [ ] **Step 4: Run the complete verification suite**

```bash
cd backend && uv run pytest -v
cd frontend && npm test -- --run
cd frontend && npm run build
cd frontend && npx playwright test
docker compose config
```

Expected: all commands succeed; screenshots contain rendered content at both viewports.

- [ ] **Step 5: Commit final verification**

```bash
git add frontend/e2e frontend/playwright.config.ts README.md
git commit -m "test: verify core mobile workflow"
```

