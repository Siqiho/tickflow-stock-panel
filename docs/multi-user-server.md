# Multi-user Hermes server

Status: production Deployment `6a7b3099408580a2d37e8a01` is running on Zeabur
as of 2026-08-11. The original multi-user release was first restored as
Deployment `6a7b25d50d41a78958bb0954`, then replaced by this shared-market-data
optimization. Account/Profile isolation, the pinned Hermes runtime, owner
migration, the shared market-data read contract, administrator write controls,
restart persistence, and the real browser surface are verified. Multi-user and
Hermes remain enabled; public registration remains disabled.

## Boundary

- Shared: market instruments, quotes, K-line, indices, financials, market
  overview, catalog/schema/status reads, and the server-owned provider,
  schedule, scope, batch and quote-service settings that produce those data.
- Per user: watchlist, navigation/display preferences, portfolio, AI reports,
  analysis menus, strategy overrides/cache, alerts, backtest summaries,
  Hermes Sessions/memory, and user-managed secrets where applicable.
- Owner only: TickFlow and deployment AI credentials, provider/endpoints and
  other shared-market setting writes, data sync/clear/rescan operations, custom
  data sources, run/source-detail inspection, monitoring administration,
  runtime logs, and server schedules.
- Local administrator candidate: the owner can open `/admin/users` to view
  account/Profile status, bounded usage aggregates, and read-only conversation
  history. The Interface has no impersonation, message sending, memory
  mutation, export, or deletion.
- AI: every account and Hermes Profile uses one deployment-owned Grok
  subscription. The upstream OAuth token or API key stays only on the server;
  regular users still consume separate UTC-day request quotas.
- Agent: every account has one stable Hermes Profile mapping. The physical
  Profile is provisioned on first Agent access, with separate config, Profile
  API key, internal model-auth token, data-auth token, Session database,
  long-term memory, and `HERMES_HOME`. These Profile tokens only authenticate
  internal local bridges; they are not Grok subscription credentials.

## Storage

- Identity, sessions, roles and quota counters: `DATA_DIR/control/identity.sqlite3`.
- The shared server Grok OAuth credential:
  `DATA_DIR/control/deployment-secrets.json` (`0600`). It is outside every
  tenant directory and every Hermes Profile.
- Account-to-Hermes mapping and provisioning status: the `hermes_profiles`
  table in the same identity database.
- Existing owner data: unchanged at `DATA_DIR/user_data/`.
- New users: `DATA_DIR/tenants/<user_id>/user_data/`.
- Managed Hermes Profiles: `ONE_TRADING_HERMES_ROOT/profiles/<profile>/`.
- Session tokens are stored as SHA-256 hashes in SQLite; passwords remain PBKDF2-HMAC-SHA256 hashes with per-user salts.
- Browser-only recent symbols, drafts and reconnect state are cleared at login/logout so they cannot cross an account boundary on a shared device.

On first startup, an existing `DATA_DIR/user_data/auth.json` owner password and
unexpired sessions are imported into the `admin` owner account. Existing owner
files are not moved. The legacy file is retained as rollback evidence and is no
longer read after the identity database contains an account.

For cloud Grok OAuth, an existing owner `user_data/secrets.json` is a read-only
compatibility source until the token is refreshed or the owner logs in again.
All new/refresh writes go to `control/deployment-secrets.json`. Clearing server
OAuth writes deployment tombstones so the legacy token cannot reappear.

## Deployment variables

```dotenv
AUTH_OWNER_USERNAME=admin
AUTH_TRUSTED_PROXY_IPS=
PUBLIC_REGISTRATION_ENABLED=true
PUBLIC_REGISTRATION_INVITE_CODE=
PUBLIC_REGISTRATION_DAILY_PER_IP=3
PUBLIC_MAX_USERS=100
USER_AI_DAILY_QUOTA=20
USER_WATCHLIST_LIMIT=100
USER_SESSION_TTL_DAYS=30
COOKIE_SECURE=true

# One deployment-owned Grok subscription for every account/Profile.
AI_ACCESS_MODE=cloud_subscription
AI_SUBSCRIPTION_ENABLED=true
AI_SUBSCRIPTION_PLAN=Grok
AI_PROVIDER=xai
AI_MODEL=grok-4.5
# Use either server OAuth or a deployment-secret AI_API_KEY, never a user key.
AI_API_KEY=

# The release image supervises the runtime. This flag was enabled only after
# the two-account production canary and restart checks passed.
ONE_TRADING_HERMES_RUNTIME_ENABLED=true
ONE_TRADING_HERMES_MULTIUSER_ENABLED=true
ONE_TRADING_HERMES_ROOT=/app/data/hermes
ONE_TRADING_HERMES_BASE_URL=http://127.0.0.1:8650
ONE_TRADING_HERMES_PROFILE=ot-owner
ONE_TRADING_HERMES_PYTHON=/opt/hermes/venv/bin/python
# Leave empty to follow the deployment PORT (Zeabur currently supplies 8080).
ONE_TRADING_INTERNAL_BASE_URL=
```

Public signup is enabled by default. Leaving
`PUBLIC_REGISTRATION_INVITE_CODE` empty allows any visitor to create an
account; the per-source daily cap and global user cap still apply. Set
`PUBLIC_REGISTRATION_ENABLED=false` to hide the signup entry and reject new
registrations without deleting existing accounts or sessions.

Registration is deliberately disabled by default. For a controlled public
trial, prefer enabling registration together with a non-empty invite code.
Open registration still has per-source daily and global account caps, but it
does not replace email verification, CAPTCHA, abuse detection, billing, or a
formal privacy/terms workflow.

## Shared login and role isolation

The online architecture needs one project, one origin, one frontend bundle and
one shared login page. Ordinary users and the owner authenticate with distinct
usernames and password hashes. `AUTH_OWNER_USERNAME` names the owner account;
its password is initialized separately through the existing setup or deployment
Secret flow. In the local candidate, a successful owner login goes to
`/admin/users`, while an ordinary user enters the regular workbench.

This is role isolation rather than a second deployment. A separate admin
frontend project would not create a security boundary because browser code is
never authoritative. The actual gates are the authenticated server role, the
`/api/admin` deny rule, a second endpoint-local administrator check, and
target-Profile credentials resolved only inside a read-only administrator
Module.

Administrator AI-usage behavior:

1. `GET /api/admin/users` returns safe identity, quota, Profile and aggregate
   conversation status. It never returns password hashes or Profile keys.
2. `GET /api/admin/users/<user_id>/conversations` reads visible conversation
   titles and previews directly, without a reason field or audit-record write.
3. Message history returns only visible `user` and `assistant` messages. Tool
   traces, system prompts, reasoning fields, credentials and memory are removed.
4. History is read from the target Hermes Profile through its native multiplex
   route at view time. Chat text is not copied into the identity database.
5. The UI cannot talk as the user, edit memory, rename, export, or delete.

Administrator navigation and data-console behavior:

1. The duplicated TickFlow and AI configuration cards are removed from the
   sidebar. Their existing `数据密钥` and `AI 设置` modules remain in `/settings`.
2. Administrator navigation ends with `用户管理` followed by `数据`. Ordinary
   accounts see the read-only `数据` entry, but not `用户管理` or monitoring
   administration.
3. `/admin/users` remains role-guarded. `/data` is an authenticated shared-data
   route: ordinary accounts receive only `数据总览` and `数据目录`, while the owner
   also receives `采集与同步`, `运行记录`, and `来源追踪`.
4. The server allowlists authenticated ordinary `GET` access only for
   `/api/data/status`, `/api/data/version`, `/api/data/catalog`, catalog detail
   and schema reads. The ordinary catalog removes operational storage,
   filesystem paths, lineage internals and scan errors; status storage totals
   include only managed market-data categories. Control summaries, runs, source
   provenance, provider writes, sync, clear and rescan remain administrator-only
   and return `403` to ordinary accounts.
5. Shared browser workbenches use the full sanitized `GET /api/data/status`.
   `GET /api/overview/data-readiness` remains as the bounded backward-compatible
   date-coverage contract and for the role-filtered Hermes data bridge. Giving
   the browser safe catalog reads does not add `/api/data/*` tools to an
   ordinary Hermes Profile.
6. Unknown `/api/*` paths return JSON `404` instead of the React SPA. Therefore
   the retired `/api/admin/audit` endpoint cannot look successful through the
   browser fallback.

The user-facing Hermes page discloses that ordinary accounts cannot read each
other's conversations while the server administrator can read AI usage and
conversation history. Production privacy/terms text must carry the same
statement before public registration is enabled.

## Hermes runtime contract

The application does not emulate Profile isolation. It uses Hermes' native
`gateway.multiplex_profiles=true` route contract: every request goes through
`/p/<profile>/...`, and the Adapter rejects a gateway that ignores that prefix.
The root Hermes config must own the single API listener; managed named Profiles
have their own API listener disabled.

`ONE_TRADING_HERMES_ROOT` must be persistent and writable by the application
that provisions Profiles, and the Hermes gateway must read that exact same
root. `Dockerfile.one-trading` pins Hermes Agent 0.20.0 at reviewed commit
`91937a6dc3ffbbe2f3be91a500f0ecf962c4cf53`, installs the MCP and API Server
runtime dependencies, and stores the root under the existing persistent
`/app/data` mount. The image entrypoint supervises one loopback-only multiplex
gateway and FastAPI together: FastAPI starts only after the gateway health
probe succeeds, and an unexpected exit of either child terminates the
container. Do not enable the user-facing feature flag while the gateway health
or production canary is incomplete.
`ONE_TRADING_HERMES_PYTHON` must point to that pinned Hermes runtime's Python;
the generated read-only MCP process uses its installed `mcp` package. The MCP
Adapter script itself is included in the application image.

Internal model and data bridges are loopback-only and authenticate with
Profile-specific bearer tokens. Those tokens identify which product account is
calling, but the model bridge always replaces the requested model/credential
with the single deployment-owned Grok subscription runtime. User-managed AI
settings and Profile files cannot select or replace the upstream credential.
The calling account's quota is still consumed separately. The data bridge is
read-only and filters its catalog by account role. Unknown local-model probe
paths return `404`, preventing the React SPA fallback from being mistaken for
LM Studio.

The owner also uses a dedicated managed `ot-owner` Profile, so an unrelated
pre-existing Hermes Profile can never select another upstream model. New
accounts are assigned non-guessable `ot-<user_id>` Profile names at
registration; directories and credentials are created lazily on first Agent
access.

Hermes 0.20 can backfill newly shipped toolsets into an existing configuration.
The managed root and every managed Profile therefore explicitly persist
`agent.disabled_toolsets: [bfl]`. Existing managed configs are migrated through
an atomic `0600` replacement. The actual Profile API surface is restricted to
`memory` and `session_search`, plus the separate read-only
`one-trading-data` MCP. Terminal, filesystem, browser, delegation, BFL, order,
and external-action toolsets are not exposed.

## Required production rollout (completed through Agent enablement)

1. Back up the Zeabur persistent volume, especially `user_data/` and `control/`.
2. Record the current deployment/build SHA and confirm the rollback image.
3. Deploy with registration disabled; verify legacy admin login and owner data.
4. Verify `identity.sqlite3`, imported sessions, and that no owner files moved.
   Verify the deployment OAuth file is `0600` and no tenant/Profile contains an
   upstream Grok token or API key.
5. Create two canary users and prove watchlist/report isolation plus admin 403s.
   For the administrator extension, also prove both users receive `403` from
   every `/api/admin/*` route while the owner can open `/admin/users` through
   the shared login flow.
6. Install and pin the reviewed Hermes runtime; make its root persistent, start
   one multiplex gateway, and keep `ONE_TRADING_HERMES_MULTIUSER_ENABLED=false`
   until the step 7 canary passes.
7. With two canary accounts, prove distinct Profile paths, credentials,
   Sessions, long-term-memory files, model bridge calls, and denied cross-Profile
   Session access. Also prove both bridge calls reach the same server-owned Grok
   credential/model while retaining different internal Profile tokens. Restart
   both processes and repeat the checks.
8. Verify AI quota exhaustion and reset semantics with automated/non-production
   evidence; do not spend the production Grok subscription merely to prove the
   gate.
9. For the administrator extension, open one canary conversation directly.
   Verify only user/assistant messages are returned, the target Profile files
   are unchanged, and the retired administrator-read metadata table is absent.
   Publish the administrator-visibility disclosure.
10. Enable the Hermes feature flag only after the above checks. Public
   registration is now the product default; before production rollout, verify
   its per-source and global caps, and keep the explicit `false` switch ready
   for abuse-control rollback.

Rollback: disable registration first, restore the previous image, and restore
the pre-deploy volume backup only if the new identity database or tenant writes
must be removed. Do not delete `identity.sqlite3` alone: doing so can re-import
legacy sessions from `auth.json`.

Disabling `ONE_TRADING_HERMES_MULTIUSER_ENABLED` is the first Agent rollback
step. It stops new Agent access without deleting Profile data. Restore or remove
Profile directories only from a matching persistent-volume backup; never delete
individual Profile keys, Session databases, or memory files independently.

## Production verification evidence (2026-08-11)

- Shared-market optimization Deployment `6a7b3099408580a2d37e8a01` is
  `RUNNING`; restored baseline Deployment `6a7b25d50d41a78958bb0954` is
  `REMOVED`. `/health` is `200`, public auth status reports
  `multi_user=true` and `registration_enabled=false`, and unauthenticated
  `/api/data/status` and `/api/data/catalog` correctly return `401`.
- The final page serves `index-Dm1qxy4s.js` and `index-BFh0o564.css`. The
  running container contains the shared-read allowlist, server-owned market
  preferences, catalog sanitizer, and managed-storage-only status code. Runtime
  logs show application startup complete, the expected shared overview/data
  requests returning `200`, and no new error or traceback.
- The immediate pre-switch backup is
  `/Users/simon/备份/codex/20260811-213230-one-trading-pre-multiuser-restore`.
  Its data and runtime archive SHA-256 values are recorded in
  `manifest.sha256`; it also keeps the exact restored multi-user release
  context. After the optimized deployment, both control SQLite databases pass
  integrity checks, identity remains at one user, seven sessions and one owner
  Profile, no tenant root was created, and all six owner-file SHA-256 values
  still match that backup exactly.
- Codex in-app browser used the existing owner session to open the production
  market dashboard and `/data`. The owner sees all five data tabs and the live
  shared market view; the page loaded the new assets with zero browser-console
  errors. No production ordinary user was created merely for acceptance; the
  ordinary-user UI and two-user isolation evidence below comes from the
  persistent local canary.
- The earlier Hermes hardening backup is
  `/Users/simon/备份/codex/20260811_124534-one-trading-zeabur-pre-hermes-tool-hardening`.
  Its data/runtime archive SHA-256 values match the remote generation values;
  all eight archived SQLite databases pass integrity checks, and the snapshot
  contains one user, seven sessions, one owner Profile, and all six original
  user files. The earlier pre-runtime backup remains at
  `/Users/simon/备份/codex/20260811_015858-one-trading-zeabur-pre-hermes-runtime-deploy`.
- Two temporary production users received different non-guessable Profiles,
  internal credentials, Sessions, and Holographic `memory_store.db` files.
  Each memory contained only its own canary fact. Cross-Profile Session reads,
  gateway auth, model bridge, and data bridge calls were denied. The same
  identities, credentials, Sessions, memories, bridges, and MCP access survived
  a service restart. The canary accounts, mappings, directories, sessions, and
  registration counters were then removed.
- The formal owner Profile is `ot-owner`, status `ready`. The authenticated
  product status route reports `connected=true`, `isolation=dedicated_profile`,
  Hermes `0.20.0`, model `grok-4.5`, model source
  `server_grok_subscription`, 68 admin-visible data views, and the read-only
  `one-trading-data` MCP.
- The root and `ot-owner` Profile both explicitly disable `bfl`; the live Hermes
  API exposes exactly `memory` and `session_search`. Correct owner Profile keys
  reach the gateway/model/data interfaces; wrong keys and owner keys presented
  to another Profile are rejected with `401`, without creating a new Profile.
  The gateway listens only on `127.0.0.1:8650`, and public traffic to the
  internal model/data bridges is rejected with `403`.
- Root and Profile credentials contain only their internal API/bridge/data key
  names, with no upstream model credential. Root/Profile directories are
  `0700`, config/credential files are `0600`, and credential hashes stayed
  stable across deployment/restart. Identity, catalog, and owner-memory
  integrity checks are `ok`; the original six user-file hashes are unchanged.
- Public auth status reports multi-user mode with registration disabled.
  Registration returns `403`; unauthenticated Agent status returns `401`.
  No Grok generation request was made during the production canary, so model
  quota remained unchanged.
- Codex in-app browser opened the final HTTPS domain and verified the
  authenticated `/ai/hermes` interface, dedicated-Profile/sandbox wording,
  static assets `index-BpCaduXt.js` and `index-C3MiXj1w.css`, and zero console
  warnings or errors.

## Local verification evidence

- Final full backend suite: 377 passed, one skipped.
- Final full frontend suite: 32 files / 124 tests passed; production build
  passed and produced the same asset names served online. Targeted Ruff and
  `git diff --check` passed.
- A persistent local image
  `one-trading-shared-market-multiuser:20260811`
  (`sha256:2e89d49b32b01b30995e5ad1ac2c15923a80175c9dbab77280bb24aee24f7cd8`)
  proved Alice and Bob receive equal normalized market overview, data status,
  catalog and server market preferences. Alice's navigation and watchlist
  stayed different from Bob's; ordinary control/clear/rescan/provider writes
  returned `403`, while the owner control summary returned `200`.
- Hermes 0.20 focused real-runtime suite: 32 passed. Two temporary accounts
  created different Profiles, Session databases, and Holographic
  `memory_store.db` files;
  cross-Profile Session reads failed, the Profile MCP discovered its two
  read-only tools, and both users completed a real streamed turn through
  different Profile bridge paths and bearer keys.
- The production Docker image built successfully with Hermes Agent 0.20.0,
  `mcp`, and `aiohttp==3.14.1`. A fresh-volume container proved the gateway and
  FastAPI supervisor chain, loopback-only `127.0.0.1:8650` listener, 200 health
  response, `0700` root/Profile modes, `0600` config/credential modes, and a
  root `.env` containing only one internal `API_SERVER_KEY`. The smoke also
  proved BFL disabled and the exact `memory`/`session_search` tool surface.
  Graceful SIGTERM stopped both child processes.
- Codex in-app browser: Alice and Bob showed different Profile IDs after a UI
  logout/login switch; no horizontal overflow or console errors were observed.
- Administrator-console candidate: the shared login redirected the owner to
  `/admin/users` and an ordinary account to `/`. The ordinary account had no
  administrator navigation and a direct `/admin/users` visit returned it to
  the workbench. Direct API checks returned `403` for the ordinary account and
  `200` for the owner.
- The administrator browser path displayed safe account summaries, read one
  target Profile directly, and returned only visible user/assistant messages.
  The seeded private tool and system traces remained absent. No reason input or
  audit table was present.
- The final ordinary browser path contains `数据` but not `用户管理` or the
  monitoring console. `/data` exposes only `数据总览` and `数据目录`, labels the
  content as shared market data, removes operational storage/source traces and
  all mutation controls, and the dashboard does not issue administrator
  pipeline/alert calls or show shared-data refresh actions.
- Backend full regression passed `377` tests with one skip. Frontend full
  regression passed `32` files / `124` tests; the production build passed.
- `Dockerfile.one-trading` built the candidate successfully. A fresh bounded
  container smoke (Hermes runtime deliberately disabled for this packaging
  check) returned local-container health, bootstrapped the owner, proved the
  final ordinary/admin API boundary: sanitized shared status/catalog reads are
  `200`, administrator operations are `403`, the retired audit route is JSON
  `404`, and SQLite integrity is `ok`.
- Local runtime tests used temporary data/Profile roots; production evidence is
  recorded separately above.

## Residual operational constraints

- Public registration stays off. Enabling it requires a separate invite,
  abuse, privacy, and capacity decision; the deployed Agent feature does not
  implicitly authorize open sign-up.
- The current container process runs as root to preserve the existing PVC
  ownership contract. Hermes is still constrained by loopback-only listeners,
  per-Profile credentials, `0700`/`0600` filesystem modes, read-only product
  data tools, and the explicit toolset denylist. Moving the whole PVC to a
  non-root UID is a separate data-ownership migration and was not mixed into
  this release.
- On the deployed SQLite 3.46 runtime, Hermes uses `journal_mode=DELETE` where
  required to avoid an upstream WAL reset incompatibility. Integrity and
  restart persistence were verified; this is an intentional compatibility
  mode, not evidence of a damaged database.
