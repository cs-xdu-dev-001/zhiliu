# Hermes Integration Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让知流可在前端安全配置并验证Hermes连接，调度器即时使用受管配置，同时移除应用内登录并将访问控制交给反向代理IP白名单。

**Architecture:** SQLite保存单例Hermes配置，API密钥由服务器环境变量派生的Fernet密钥加密；后端通过公开`/health`和受保护`/v1/capabilities`区分可达性与鉴权状态。前端在订阅页顶部提供状态、配置和测试入口，浏览器永远无法读取已保存的完整密钥。

**Tech Stack:** FastAPI、SQLAlchemy、Pydantic Settings、httpx、cryptography/Fernet、React 19、TanStack Query、Vitest、Playwright。

---

## File map

- 新建`backend/app/core/crypto.py`、`backend/app/services/hermes_integration.py`、`backend/app/api/hermes_integration.py`和`backend/tests/test_hermes_integration.py`。
- 修改`backend/app/models.py`、`schemas.py`、`services/hermes.py`、`services/scheduler.py`、`main.py`和配置/依赖文件。
- 删除后端auth/security及认证测试；业务router移除`CurrentUser`。
- 新建`frontend/src/components/HermesConnection.tsx`及其测试；修改设置页、类型和CSS。
- 删除前端登录页及测试；简化AppShell并更新E2E。
- 修改`.env.example`、`README.md`、`docker-compose.yml`和`PRODUCT.md`。

### Task 1: Encrypted configuration storage

**Files:**
- Create: `backend/app/core/crypto.py`
- Create: `backend/tests/test_hermes_integration.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/models.py`
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Write failing tests**

```python
from app.core.crypto import SecretCipher
from app.models import HermesIntegration

def test_secret_cipher_round_trips_without_plaintext() -> None:
    cipher = SecretCipher("integration-secret-at-least-32-characters")
    encrypted = cipher.encrypt("hermes-api-key")
    assert encrypted != "hermes-api-key"
    assert cipher.decrypt(encrypted) == "hermes-api-key"

def test_hermes_integration_defaults_to_unconfigured(db_session) -> None:
    record = HermesIntegration(base_url="http://127.0.0.1:8642")
    db_session.add(record)
    db_session.commit()
    assert record.last_status == "unconfigured"
    assert record.encrypted_api_key is None
```

- [ ] **Step 2: Verify RED**

Run from`backend`:

```powershell
uv run pytest tests/test_hermes_integration.py -v
```

Expected: collection fails because both new symbols are missing.

- [ ] **Step 3: Add dependency and cipher**

Add`cryptography>=45,<46`to`backend/pyproject.toml`and create:

```python
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken

class SecretDecryptionError(RuntimeError):
    pass

class SecretCipher:
    def __init__(self, secret: str) -> None:
        if len(secret) < 32:
            raise ValueError("INTEGRATION_SECRET_KEY必须至少32位")
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode()
        except InvalidToken as exc:
            raise SecretDecryptionError("Hermes密钥无法解密，请重新配置") from exc
```

Add`integration_secret_key: str = "development-integration-secret-key-32"`to`Settings`; in production reject this default or any value shorter than32.

- [ ] **Step 4: Add SQLAlchemy model**

```python
class HermesIntegration(Base):
    __tablename__ = "hermes_integrations"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    api_key_hint: Mapped[str | None] = mapped_column(String(16))
    last_status: Mapped[str] = mapped_column(String(32), default="unconfigured")
    last_message: Mapped[str] = mapped_column(String(500), default="尚未配置Hermes连接")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hermes_version: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
```

Reuse the existing`utc_now`and model imports.

- [ ] **Step 5: Verify GREEN and commit**

```powershell
uv lock
uv run pytest tests/test_hermes_integration.py -v
git add backend/app/core/crypto.py backend/app/core/config.py backend/app/models.py backend/pyproject.toml backend/uv.lock backend/tests/test_hermes_integration.py
git commit -m "feat: add encrypted Hermes configuration storage"
```

Expected: two tests pass and only scoped files enter the commit.

### Task 2: Side-effect-free Hermes probe

**Files:**
- Modify: `backend/app/services/hermes.py`
- Modify: `backend/tests/test_hermes.py`

- [ ] **Step 1: Write failing probe tests**

```python
@pytest.mark.asyncio
async def test_probe_checks_health_then_capabilities() -> None:
    hermes = import_module("app.services.hermes")
    paths = []
    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "version": "1.2.3"})
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"endpoints": ["/v1/runs"]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = hermes.HermesClient(base_url="http://hermes.local", api_key="test-key", timeout_seconds=2, http_client=http_client)
        result = await client.probe()
    assert paths == ["/health", "/v1/capabilities"]
    assert result.version == "1.2.3"

@pytest.mark.asyncio
async def test_probe_distinguishes_unauthorized() -> None:
    hermes = import_module("app.services.hermes")
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(401, json={"error": "Invalid API key"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = hermes.HermesClient(base_url="http://hermes.local", api_key="bad", timeout_seconds=2, http_client=http_client)
        with pytest.raises(hermes.HermesUnauthorized):
            await client.probe()
```

- [ ] **Step 2: Verify RED**

```powershell
uv run pytest tests/test_hermes.py -v
```

Expected: missing`probe`and`HermesUnauthorized`fail.

- [ ] **Step 3: Implement probe**

Add`HermesUnauthorized(HermesError)`and`HermesProbe(ApiModel)`with`version`and`platform`. Add to`HermesClient`:

```python
async def probe(self) -> HermesProbe:
    owns_client = self._external_client is None
    client = self._external_client or httpx.AsyncClient(timeout=httpx.Timeout(5))
    try:
        health = await client.get(f"{self.base_url}/health")
        health.raise_for_status()
        health_payload = health.json()
        capabilities = await client.get(f"{self.base_url}/v1/capabilities", headers=self._headers)
        if capabilities.status_code in {401, 403}:
            raise HermesUnauthorized("Hermes拒绝了当前密钥")
        capabilities.raise_for_status()
        if not isinstance(health_payload, dict) or not isinstance(capabilities.json(), dict):
            raise ValueError("Hermes响应不是JSON对象")
        return HermesProbe(version=health_payload.get("version"), platform=health_payload.get("platform"))
    except HermesUnauthorized:
        raise
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        raise HermesUnavailable(f"Hermes API不可用: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()
```

- [ ] **Step 4: Verify GREEN and commit**

```powershell
uv run pytest tests/test_hermes.py -v
git add backend/app/services/hermes.py backend/tests/test_hermes.py
git commit -m "feat: verify Hermes connectivity and authorization"
```

Expected: new probe and existing run tests pass.

### Task 3: Hermes management API

**Files:**
- Create: `backend/app/services/hermes_integration.py`
- Create: `backend/app/api/hermes_integration.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_hermes_integration.py`

- [ ] **Step 1: Write failing API tests**

```python
def test_get_unconfigured_connection(client) -> None:
    response = client.get("/api/integrations/hermes")
    assert response.status_code == 200
    assert response.json()["status"] == "unconfigured"
    assert response.json()["apiKeyConfigured"] is False

def test_put_masks_key_and_auto_tests(client, monkeypatch) -> None:
    async def connected(self):
        return HermesProbe(version="1.2.3", platform="hermes-agent")
    monkeypatch.setattr(HermesClient, "probe", connected)
    response = client.put("/api/integrations/hermes", json={"baseUrl": "http://hermes.local:8642", "apiKey": "secret-a9f2"})
    assert response.status_code == 200
    assert response.json()["apiKeyHint"] == "••••a9f2"
    assert "secret-a9f2" not in response.text
    assert response.json()["status"] == "connected"
```

- [ ] **Step 2: Verify RED**

```powershell
uv run pytest tests/test_hermes_integration.py -v
```

Expected: GET and PUT return404.

- [ ] **Step 3: Add schemas and service**

```python
class HermesConnectionUpdate(ApiModel):
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=500)

class HermesConnectionResponse(ApiModel):
    base_url: str
    api_key_configured: bool
    api_key_hint: str | None
    status: Literal["unconfigured", "unreachable", "unauthorized", "connected", "error"]
    message: str
    checked_at: datetime | None
    version: str | None
```

`HermesIntegrationService`must expose`get_record()`,`response()`,`save_and_test()`and`test()`. `save_and_test()`validates an http/https URL with a hostname, keeps the old key when input is blank, encrypts a new key, stores`••••`plus the last4 characters, commits, then calls`test()`.

`test()`decrypts the key and calls`HermesClient.probe()`; map`HermesUnauthorized→unauthorized`,`HermesUnavailable→unreachable`,`SecretDecryptionError/HermesError→error`, success→`connected`. Always store UTC`last_checked_at`, message and version; never return the plaintext key.

- [ ] **Step 4: Add router and register it**

```python
router = APIRouter(prefix="/api/integrations/hermes", tags=["hermes-integration"])

@router.get("", response_model=HermesConnectionResponse)
def get_connection(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    service = HermesIntegrationService(db, settings)
    return service.response(service.get_record())

@router.put("", response_model=HermesConnectionResponse)
async def update_connection(payload: HermesConnectionUpdate, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return await HermesIntegrationService(db, settings).save_and_test(payload)

@router.post("/test", response_model=HermesConnectionResponse)
async def test_connection(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return await HermesIntegrationService(db, settings).test()
```

Import and include the router in`create_app()`.

- [ ] **Step 5: Verify GREEN and commit**

```powershell
uv run pytest tests/test_hermes_integration.py tests/test_hermes.py -v
git add backend/app/api/hermes_integration.py backend/app/services/hermes_integration.py backend/app/schemas.py backend/app/main.py backend/tests/test_hermes_integration.py
git commit -m "feat: expose Hermes connection management API"
```

Expected: camelCase API responses pass all contract tests.

### Task 4: Use managed settings in queued tasks

**Files:**
- Modify: `backend/app/services/hermes_integration.py`
- Modify: `backend/app/services/scheduler.py`
- Modify: `backend/tests/test_scheduler.py`

- [ ] **Step 1: Write failing resolver tests**

```python
def test_resolve_client_prefers_database_config(db_session, subscription) -> None:
    settings = Settings(app_env="development", hermes_base_url="http://env", hermes_api_key="env-key", integration_secret_key="integration-secret-at-least-32-characters")
    service = HermesIntegrationService(db_session, settings)
    db_session.add(HermesIntegration(id=1, base_url="http://managed", encrypted_api_key=service.cipher.encrypt("managed-key"), api_key_hint="••••-key"))
    db_session.commit()
    client = service.resolve_client(subscription, DemoHermesClient)
    assert client.base_url == "http://managed"
    assert client._headers["Authorization"] == "Bearer managed-key"

def test_resolve_client_rejects_missing_real_config(db_session, subscription) -> None:
    settings = Settings(app_env="development", demo_mode=False, hermes_api_key="", integration_secret_key="integration-secret-at-least-32-characters")
    with pytest.raises(HermesUnavailable, match="尚未配置Hermes连接"):
        HermesIntegrationService(db_session, settings).resolve_client(subscription, DemoHermesClient)
```

- [ ] **Step 2: Verify RED**

```powershell
uv run pytest tests/test_scheduler.py -v
```

Expected: missing`resolve_client`fails.

- [ ] **Step 3: Implement precedence and scheduler wiring**

```python
def resolve_client(self, subscription: Subscription, demo_client_factory):
    record = self.get_record()
    if record and record.encrypted_api_key:
        return HermesClient(base_url=record.base_url, api_key=self.cipher.decrypt(record.encrypted_api_key), timeout_seconds=self.settings.hermes_timeout_seconds)
    if self.settings.hermes_api_key:
        return HermesClient(base_url=self.settings.hermes_base_url, api_key=self.settings.hermes_api_key, timeout_seconds=self.settings.hermes_timeout_seconds)
    if self.settings.demo_mode:
        return demo_client_factory(subscription)
    raise HermesUnavailable("尚未配置Hermes连接")
```

Replace the environment-only branch in`process_queued_tasks()`with:

```python
client = HermesIntegrationService(db, settings).resolve_client(task.subscription, DemoHermesClient)
await RunService(db, client).execute_task(task.id)
```

- [ ] **Step 4: Verify GREEN and commit**

```powershell
uv run pytest tests/test_scheduler.py tests/test_run_service.py -v
git add backend/app/services/hermes_integration.py backend/app/services/scheduler.py backend/tests/test_scheduler.py
git commit -m "feat: run tasks with managed Hermes settings"
```

Expected: database config wins, environment fallback remains, missing production config fails clearly, and`hermes_run_id`tests still pass.

### Task 5: Remove backend authentication

**Files:**
- Delete: `backend/app/api/auth.py`
- Delete: `backend/app/core/security.py`
- Delete: `backend/tests/test_auth.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/subscriptions.py`
- Modify: `backend/app/api/items.py`
- Modify: `backend/app/api/briefings.py`
- Modify: `backend/app/api/runs.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/seed.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_config.py`
- Modify: `backend/tests/test_seed.py`
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Write failing public-access tests**

```python
def test_business_api_is_available_without_cookie(client) -> None:
    assert client.get("/api/subscriptions").status_code == 200

def test_auth_routes_are_removed(client) -> None:
    assert client.get("/api/auth/me").status_code == 404
    assert client.post("/api/auth/login", json={"username": "admin", "password": "password"}).status_code == 404
```

Change existing business tests from`auth_client`to`client`.

- [ ] **Step 2: Verify RED**

```powershell
uv run pytest -q
```

Expected: public request returns401 and auth routes are not404.

- [ ] **Step 3: Remove auth dependencies and dead code**

For every endpoint in subscriptions/items/briefings/runs, remove`CurrentUser`imports and parameters while preserving paths, schemas and DB behavior. Remove auth router registration. Delete auth/security/test_auth. Remove`LoginRequest`and`UserResponse`; remove administrator creation from seed but keep demo data. Remove`seeded_user`and`auth_client`fixtures. Keep the`User`table model for existing SQLite compatibility but stop reading/writing it.

Remove`pyjwt`and`pwdlib[argon2]`, run`uv lock`. Remove`jwt_secret`,`admin_username`,`admin_password`and their validator; production validation retains only a non-default32+ character`integration_secret_key`. Update config and seed tests accordingly.

- [ ] **Step 4: Verify GREEN and commit**

```powershell
uv run pytest -q
git add backend/app backend/tests backend/pyproject.toml backend/uv.lock
git commit -m "feat: remove application-level authentication"
```

Expected: the complete backend suite passes without cookies and auth paths return404.

### Task 6: Add Hermes connection UI

**Files:**
- Create: `frontend/src/components/HermesConnection.tsx`
- Create: `frontend/src/components/HermesConnection.test.tsx`
- Modify: `frontend/src/pages/Subscriptions.tsx`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write failing component tests**

```tsx
const connected = { baseUrl: "http://127.0.0.1:8642", apiKeyConfigured: true, apiKeyHint: "••••a9f2", status: "connected", message: "Hermes已连接并通过鉴权", checkedAt: "2026-08-02T02:30:00Z", version: "1.2.3" };

it("显示状态但不回显完整密钥", async () => {
  get.mockResolvedValue(connected);
  renderConnection();
  expect(await screen.findByText("Hermes已连接并通过鉴权")).toBeVisible();
  expect(screen.getByText("••••a9f2")).toBeVisible();
  expect(screen.queryByDisplayValue("secret-a9f2")).not.toBeInTheDocument();
});

it("保存配置并显示鉴权失败", async () => {
  get.mockResolvedValue({ ...connected, status: "unconfigured", apiKeyConfigured: false, apiKeyHint: null });
  put.mockResolvedValue({ ...connected, status: "unauthorized", message: "Hermes拒绝了当前密钥，请重新配置", version: null });
  renderConnection();
  await userEvent.click(await screen.findByRole("button", { name: "配置连接" }));
  await userEvent.clear(screen.getByLabelText("Hermes服务地址"));
  await userEvent.type(screen.getByLabelText("Hermes服务地址"), "http://hermes.local:8642");
  await userEvent.type(screen.getByLabelText("Hermes API密钥"), "bad-key");
  await userEvent.click(screen.getByRole("button", { name: "保存并测试" }));
  expect(put).toHaveBeenCalledWith("/api/integrations/hermes", { baseUrl: "http://hermes.local:8642", apiKey: "bad-key" });
  expect(await screen.findByText("Hermes拒绝了当前密钥，请重新配置")).toBeVisible();
});

it("测试已保存连接", async () => {
  get.mockResolvedValue(connected); post.mockResolvedValue(connected); renderConnection();
  await userEvent.click(await screen.findByRole("button", { name: "测试连接" }));
  expect(post).toHaveBeenCalledWith("/api/integrations/hermes/test");
});
```

Use the QueryClient and mocked`api.get/put/post`pattern from`Subscriptions.test.tsx`.

- [ ] **Step 2: Verify RED**

```powershell
npm test -- --run src/components/HermesConnection.test.tsx
```

Expected: component import fails.

- [ ] **Step 3: Add types and component**

```ts
export type HermesConnectionStatus = "unconfigured" | "unreachable" | "unauthorized" | "connected" | "error";
export interface HermesConnection { baseUrl: string; apiKeyConfigured: boolean; apiKeyHint: string | null; status: HermesConnectionStatus; message: string; checkedAt: string | null; version: string | null; }
```

The component queries`GET /api/integrations/hermes`; test mutation posts`/api/integrations/hermes/test`; save mutation puts`{baseUrl,apiKey}`and writes returned data into`["hermes-connection"]`cache. Render status/message, base URL, masked key, version, localized checked time, plus“测试连接”和“配置连接”。The password input is blank on every open and blank means retain. Use existing dialog patterns, Esc/backdrop close, disabled pending controls,`role=status`and`role=alert`.

- [ ] **Step 4: Integrate and style**

Insert`<HermesConnection />`before the subscriptions toolbar. Add product-specific`.hermes-connection`,`.hermes-summary`,`.hermes-status`,`.hermes-meta`,`.hermes-actions`; reuse tokens and 44px targets. Mobile stacks without horizontal overflow and keeps core text14px or larger.

- [ ] **Step 5: Verify GREEN and commit**

```powershell
npm test -- --run src/components/HermesConnection.test.tsx src/pages/Subscriptions.test.tsx
npm run build
git add frontend/src/components/HermesConnection.tsx frontend/src/components/HermesConnection.test.tsx frontend/src/pages/Subscriptions.tsx frontend/src/types.ts frontend/src/styles.css
git commit -m "feat: manage Hermes connection from settings"
```

Expected: UI tests and TypeScript build pass.

### Task 7: Remove frontend login and update E2E

**Files:**
- Create: `frontend/src/App.test.tsx`
- Delete: `frontend/src/pages/Login.tsx`
- Delete: `frontend/src/pages/Login.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/e2e/core-flow.spec.ts`
- Modify: `frontend/playwright.config.ts`

- [ ] **Step 1: Write failing direct-entry test**

```tsx
vi.mock("./components/AppShell", () => ({ AppShell: () => <div>应用外壳</div> }));
it("无需登录直接渲染应用", () => {
  window.history.pushState({}, "", "/login");
  render(<App />);
  expect(screen.getByText("应用外壳")).toBeVisible();
  expect(screen.queryByText("登录你的情报台")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Verify RED**

```powershell
npm test -- --run src/App.test.tsx
```

Expected: existing route/auth structure does not satisfy direct entry.

- [ ] **Step 3: Remove frontend auth**

Replace App with`return <AppShell />`. In AppShell remove`useQuery`,`Redirect`,`ApiError`,`User`,`/api/auth/me`,401 handling, logout request, username chip and logout button. Keep`useLocation`only for navigation state. Delete Login files and`User`type; delete login/user/logout-only CSS. The topbar contains mobile brand and page title only.

- [ ] **Step 4: Update Playwright**

Change web-server readiness URL from`/login`to`/`. Delete the login helper. Begin the flow with`page.goto("/")`and assert“今日情报”。On settings assert“Hermes连接”和“测试连接”。Keep both desktop/mobile projects, overflow assertions, screenshots and task-trigger flow.

- [ ] **Step 5: Verify GREEN and commit**

```powershell
npm test -- --run
npm run build
npx playwright test
git add frontend/src frontend/e2e/core-flow.spec.ts frontend/playwright.config.ts
git commit -m "feat: remove frontend login flow"
```

Expected: all frontend tests and both E2E projects pass without auth requests.

### Task 8: Deployment contract and release verification

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `PRODUCT.md`

- [ ] **Step 1: Update environment contract**

```dotenv
APP_ENV=production
INTEGRATION_SECRET_KEY=replace-with-at-least-32-random-characters
DEMO_MODE=false
SCHEDULER_ENABLED=true
HERMES_BASE_URL=http://127.0.0.1:8642
HERMES_API_KEY=
HERMES_TIMEOUT_SECONDS=180
WEB_PORT=8080
```

Document`HERMES_API_KEY`as migration fallback only; new deployments configure through the UI. Remove JWT/admin variables from Compose and docs.

- [ ] **Step 2: Document Hermes and IP allowlist**

Keep exact Hermes config:

```dotenv
API_SERVER_ENABLED=true
API_SERVER_KEY=使用独立的高强度随机密钥
```

Explain that testing calls`/health`and authenticated`/v1/capabilities`, then direct operators to“订阅与任务→Hermes连接”。Add:

```nginx
location / {
    allow 203.0.113.10;
    deny all;
    proxy_pass http://127.0.0.1:8080;
}
```

State before the snippet that知流must not be exposed until the allowlist is active. Update PRODUCT.md from application login to single-operator deployment-layer IP protection.

- [ ] **Step 3: Run full verification**

```powershell
Push-Location backend
uv run pytest -q
Pop-Location
Push-Location frontend
npm test -- --run
npm run build
npx playwright test
Pop-Location
node 'C:\Users\z2986\.codex\skills\impeccable\scripts\detect.mjs' --json frontend/src
git diff --check
git status --short
```

Expected: backend/frontend tests, build and two E2E projects pass; detector returns`[]`; diff check exits0; status only lists intentional changes.

- [ ] **Step 4: Perform live three-level acceptance when Hermes runs**

```powershell
Invoke-WebRequest http://127.0.0.1:8642/health -UseBasicParsing
$headers = @{ Authorization = "Bearer $env:HERMES_TEST_KEY" }
Invoke-RestMethod http://127.0.0.1:8642/v1/capabilities -Headers $headers
```

Then save the same key in知流, click“测试连接”，and trigger one subscription. Acceptance requires“已连接”、a completed task with non-null`hermesRunId`, and newly ingested intelligence. If Hermes is stopped, report live acceptance as externally blocked; mocked tests are not live proof.

- [ ] **Step 5: Commit docs and configuration**

```powershell
git add .env.example docker-compose.yml README.md PRODUCT.md
git commit -m "docs: document secure Hermes deployment"
```

## Final review checklist

- Backend never returns or logs the full Hermes API key.
- `/health`proves reachability;`/v1/capabilities`proves Bearer authorization; a completed Run proves end-to-end execution.
- Managed SQLite config overrides environment fallback without restart.
- Missing encryption key never causes plaintext storage.
- Business routes work without cookies; auth API and login UI no longer exist.
- IP allowlisting is mandatory in deployment docs.
- Desktop and mobile settings remain keyboard accessible and overflow-free.
