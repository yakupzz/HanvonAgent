# Multi-Stack Project — Claude Code Instructions (2026 Edition)

## Project overview

Templates for **Web SaaS**, **Desktop**, and **Mobile** applications using agent-driven development.

---

## Stack Selection

Choose one based on your feature request:

### Web Stack
A landing page with pricing, authentication, and Stripe payments.  
**Agents:** `web-planner`, `web-ui-agent`, `web-builder`, `web-reviewer`

### Desktop Stack
Professional desktop applications with modern UI, databases, and cross-platform support.  
**Agents:** `desktop-planner`, `desktop-ui-agent`, `desktop-builder`, `desktop-reviewer`

### Mobile Stack (2026)
Native iOS + Android apps with offline-first, real-time sync, and AI integration.  
**Agents:** `mobile-planner`, `mobile-ui-agent`, `mobile-builder`, `mobile-reviewer`

---

## Stack (Web — 2026 Edition)

| Layer         | Choice                                      |
|---------------|---------------------------------------------|
| Framework     | Next.js 16 (App Router, Turbopack)          |
| Language      | TypeScript 5.5+                             |
| Styling       | Tailwind CSS v4 + shadcn/ui                 |
| State         | Zustand (client state)                      |
| Data Fetching | TanStack Query (server state)               |
| Forms         | React Hook Form + Zod validation            |
| Database      | Prisma ORM + Supabase PostgreSQL            |
| Auth          | Better Auth (TypeScript-first)              |
| Payments      | Stripe                                      |
| APIs          | tRPC (type-safe RPC)                        |
| Testing       | Vitest (unit) + Playwright (E2E)            |
| Deploy        | Vercel                                      |

## Stack (Desktop — 2026 Edition)

| Layer      | Choice                                      |
|------------|---------------------------------------------|
| Framework  | PySide6 (Qt 6.x)                            |
| Language   | Python 3.10+                                |
| Database   | SQLAlchemy ORM + PostgreSQL/SQLite          |
| Validation | Pydantic v2                                 |
| Forms      | Qt native (QLineEdit, QSpinBox, etc.)       |
| Testing    | pytest + pytest-qt                          |
| Architecture | MVC (Model-View-Controller)               |

## Stack (Mobile — 2026 Edition)

| Layer          | Choice                                      |
|----------------|---------------------------------------------|
| Framework      | Flutter 3.x (Dart)                          |
| Language       | Dart 3.x                                    |
| State          | Riverpod + code generation                  |
| Backend        | Firebase (Firestore, Auth, Cloud Functions) |
| Offline        | Hive + Drift (local databases)              |
| Real-time      | Firebase Realtime DB + WebSocket            |
| Networking     | Dio + Retrofit + GraphQL                    |
| Push Notif     | Firebase Cloud Messaging (FCM)              |
| Analytics      | Firebase Analytics + Sentry                 |
| Testing        | Flutter test + Appium + Patrol              |
| AI/ML          | Google ML Kit + TensorFlow Lite (on-device) |
| Payments       | Stripe + Firebase In-App Purchases          |
| Security       | Biometric (fingerprint, Face ID) + Secure Storage |
| Deploy         | Google Play + App Store + Firebase Hosting  |

## Rules (Web)

### Code Quality

### Code Quality

- **Immutable patterns.** Use spread operators, `.map/.filter/.reduce`. No direct mutation.
- **File size.** 200–400 lines ideal, 800 absolute max.
- **Function size.** Max 50 lines, max 4 levels of nesting.
- **TDD.** Required for auth, payments, APIs, and anything security-sensitive.

### Data & Validation

- **Zod schemas.** Validate at every boundary — API inputs, forms, LLM outputs, file uploads.
- **Type safety.** Prefer `tRPC` for APIs (auto-generates client types).
- **Forms.** Use React Hook Form with Zod validation; no bare `<input>`.
- **Mutations.** Server actions (`'use server'`) for data changes; tRPC procedures for complex logic.

### State Management

- **Client state.** Zustand for UI state (filters, modals, themes).
- **Server state.** TanStack Query for API responses (caching, invalidation, sync).
- **Database.** Prisma for all DB queries (type-safe, migrations).

### Security & Secrets

- **Secrets.** Always via `process.env`, never in code.
- **Auth.** Better Auth only; never implement custom auth.
- **API routes.** Validate input with Zod; check auth before executing.
- **Payments.** Stripe webhook verification mandatory; use server actions.

## Rules (Desktop)

### Code Quality

- **TDD is mandatory.** Write failing test → implement → refactor. No exceptions.
- **File size.** 200–400 lines ideal, 800 absolute max.
- **Function size.** Max 50 lines, max 4 levels of nesting.
- **MVC pattern.** Separate models (SQLAlchemy), services (business logic), widgets (UI).

### Database & Validation

- **SQLAlchemy for database.** Never write raw SQL.
- **Pydantic schemas.** Validate all inputs (file operations, database, user input).
- **Relationships.** Define FK and associations in models; lazy-load where needed.
- **Migrations.** Use alembic for schema changes.

### UI & Events

- **Qt widgets.** Use native widgets (QLineEdit, QPushButton, QTableWidget, etc.).
- **Signal/slot discipline.** Widgets emit → services handle → UI updates.
- **No blocking UI.** Long operations in QThread; progress signals to main thread.
- **Error handling.** Try/catch at service layer; show in UI (QMessageBox, status bar).
- **Tab order & shortcuts.** Every dialog accessible via keyboard.

### Security & Secrets

- **Secrets via env vars.** Never hardcode API keys, database credentials.
- **Input validation.** Pydantic on all inputs (file operations, DB queries, user input).
- **SQL injection prevention.** SQLAlchemy parameterized queries only.
- **File operations.** No path traversal; validate file paths; size limits.
- **Passwords (if auth).** Bcrypt hashing; never plain text.

## Rules (Mobile)

### Code Quality

- **TDD is mandatory.** Write failing test → implement → refactor. No exceptions.
- **File size.** 200–400 lines ideal, 600 absolute max (mobile screens are small).
- **Function size.** Max 40 lines, max 3 levels of nesting.
- **Immutability.** Use Dart immutable patterns (final, const, copyWith).
- **Code generation.** Riverpod, Freezed, Retrofit — use code gen, don't write boilerplate.

### Performance & Battery

- **Offline-first.** Build with offline sync in mind — Hive + cloud sync.
- **Battery optimization.** Minimize CPU/GPU; batch operations; use efficient queries.
- **Network efficiency.** Compress payloads; use GraphQL to fetch only needed fields.
- **Frame rate.** 60 FPS on phone, 120 FPS on tablet — profile with DevTools.
- **Memory.** Monitor memory usage; dispose streams and listeners; avoid memory leaks.

### UI & Navigation

- **Responsive design.** Support phone (360–600dp), tablet (600–900dp), and landscape.
- **Navigation.** Use Go Router for deep linking; stack-based navigation; clear state.
- **Accessibility.** Semantics, contrast ratio (WCAG AA), font scaling, screen reader support.
- **State management.** Riverpod providers for UI state, server state, and side effects.
- **Animations.** Use AnimationController, Tweens; keep animations under 300ms.

### Backend Integration

- **Firebase for MVP.** Firestore (database), Auth (sign-up/login), Cloud Functions (logic).
- **Real-time sync.** Use Firestore streams with Riverpod for automatic UI updates.
- **API contracts.** REST or GraphQL; Retrofit for code gen; Dio for HTTP.
- **Error handling.** Catch network errors, permission errors, auth errors; show in UI.
- **Timeout & retry.** Network calls timeout after 30s; retry with exponential backoff.

### Security & Permissions

- **Secrets.** Firebase config in secure storage (flutter_secure_storage), never in code.
- **Auth.** Firebase Auth + Biometric (fingerprint, Face ID) for 2FA.
- **Input validation.** Validate all user inputs (forms, search, uploads).
- **Permissions.** Request location, camera, microphone with user consent; explain why.
- **Data encryption.** Sensitive data (tokens, passwords) in encrypted secure storage.
- **API authentication.** Bearer tokens; refresh tokens for long sessions; revoke on logout.

### Testing & Monitoring

- **Unit tests.** 80%+ coverage for services, providers, business logic.
- **Widget tests.** Screen layouts, interactions, navigation.
- **E2E tests.** Patrol or Appium for critical user flows (sign-up, payment, etc.).
- **Crash monitoring.** Sentry for error tracking and analytics.
- **Performance monitoring.** Firebase Performance Monitoring; track API latency.

## Workflow

### Web Workflow

Features follow this agent chain:

```text
USER REQUEST
    ↓
web-planner    → produces implementation plan
    ↓
web-ui-agent   → produces component brief
    ↓
web-builder    → writes tests + code (TDD)
    ↓
web-reviewer   → quality + security check
    ↓
(if CRITICAL found → loop back to web-builder)
    ↓
COMMIT
```

### Desktop Workflow

Features follow this agent chain:

```text
USER REQUEST
    ↓
desktop-planner    → produces implementation plan
    ↓
desktop-ui-agent   → produces component brief
    ↓
desktop-builder    → writes tests + code (TDD)
    ↓
desktop-reviewer   → quality + security check
    ↓
(if CRITICAL found → loop back to desktop-builder)
    ↓
COMMIT
```

### Mobile Workflow

Features follow this agent chain:

```text
USER REQUEST
    ↓
mobile-planner    → produces implementation plan
    ↓
mobile-ui-agent   → produces screen & navigation brief
    ↓
mobile-builder    → writes tests + code (TDD)
    ↓
mobile-reviewer   → quality + performance + security check
    ↓
(if CRITICAL found → loop back to mobile-builder)
    ↓
COMMIT
```

## Agents

Defined in `.claude/agents/`:

### Web Stack Agents

| Agent           | Role                              | Tools                          |
|-----------------|-----------------------------------|--------------------------------|
| web-planner     | Planning + architecture (web)     | Read, Grep, Glob               |
| web-ui-agent    | Design + React components         | Read, Grep, Glob               |
| web-builder     | Next.js + tRPC + Prisma (TDD)     | Read, Write, Edit, Bash, Grep  |
| web-reviewer    | Quality + security (web)          | Read, Grep, Glob, Bash         |

### Desktop Stack Agents

| Agent            | Role                              | Tools                          |
|------------------|-----------------------------------|--------------------------------|
| desktop-planner  | Planning + architecture (desktop) | Read, Grep, Glob               |
| desktop-ui-agent | Design + PySide6 UI components    | Read, Grep, Glob               |
| desktop-builder  | PySide6 + SQLAlchemy (TDD)        | Read, Write, Edit, Bash, Grep  |
| desktop-reviewer | Quality + security (desktop)      | Read, Grep, Glob, Bash         |

### Mobile Stack Agents

| Agent           | Role                              | Tools                          |
|-----------------|-----------------------------------|--------------------------------|
| mobile-planner  | Planning + architecture (mobile)  | Read, Grep, Glob               |
| mobile-ui-agent | Design + Flutter screens          | Read, Grep, Glob               |
| mobile-builder  | Flutter + Firebase (TDD)          | Read, Write, Edit, Bash, Grep  |
| mobile-reviewer | Quality + performance + security  | Read, Grep, Glob, Bash         |

**Note:** No agent has `Task` tool — subagents cannot spawn other subagents. Main Claude orchestrates.

---

## Session Tracking — `.claude/state.md`

Each workflow session must be documented in `.claude/state.md` for audit trail, progress tracking, and regression prevention.

### When to Update

**Every agent must update `state.md` after completing its work:**

1. **Planner** → Adds plan section with scope, risks, dependencies
2. **UI Agent** → Adds design decisions, component brief summary, design tokens
3. **Builder** → Adds files created/modified, test results, implementation notes
4. **Reviewer** → Adds findings by severity (CRITICAL/HIGH/MEDIUM/LOW), verdict, open items

### Format

```markdown
## Session N — [Feature Name]

**Started:** [ISO timestamp]
**Task:** [1-line description]

---

## [HH:MM:SS · PLANNER]
**Plan:** [scope, risks, dependencies]
**Files affected:** [list]

## [HH:MM:SS · UI-AGENT]
**Design:** [tokens, layout decisions]
**Files affected:** [list]

## [HH:MM:SS · BUILDER]
**Implementation:** [what was built]
**Files created/modified:** [list]
**Tests:** [pass/fail status]
**Open items:** [none | list]

## [HH:MM:SS · REVIEWER]
**Findings:**
- [CRITICAL] issue 1
- [HIGH] issue 2
- [MEDIUM] issue 3

**Verdict:** PASS | PASS WITH NITS | FAIL

**Next steps:** [if failed, what builder should fix]
```

### Rules

- **Timestamp format:** ISO 8601 with session-local HH:MM:SS (e.g., 15:42:36)
- **Severity levels:** Only use CRITICAL, HIGH, MEDIUM, LOW — nothing else
- **Open items:** If an issue is waved (low priority or by design), list it under the agent's "Open items" so it's not forgotten
- **CRITICAL or HIGH blocks merge** — loop back to builder before commit
- **MEDIUM/LOW go to state.md "Future" section** at end of session for future sprints

## Skills

Defined in `.claude/skills/`. See `.claude/skills/README.md` for source attribution.

| Skill             | Used by        | Source                                           |
|-------------------|----------------|--------------------------------------------------|
| `plan`            | web-planner    | community (alirezarezvani/claude-skills)         |
| `ui-ux-pro-max`   | web-ui-agent   | nextlevelbuilder/ui-ux-pro-max-skill             |
| `api-design`      | web-builder    | wshobson/agents (backend-development plugin)     |
| `code-review`     | web-reviewer   | anthropics/claude-code (official)                |
| `security-review` | web-reviewer   | anthropics/claude-code-security-review           |

### Desktop Stack Skills

| Skill             | Used by         | Source                                           |
|-------------------|-----------------|--------------------------------------------------|
| `plan`            | desktop-planner | community (alirezarezvani/claude-skills)         |
| `database-design` | desktop-builder | community (Python SQLAlchemy patterns)           |
| `code-review`     | desktop-reviewer| anthropics/claude-code (official)                |
| `security-review` | desktop-reviewer| anthropics/claude-code-security-review           |

### Mobile Stack Skills (2026)

| Skill                   | Used by          | Source                                           |
|-------------------------|------------------|--------------------------------------------------|
| `plan`                  | mobile-planner   | community (alirezarezvani/claude-skills)         |
| `flutter-performance`   | mobile-builder   | community (Flutter optimization patterns)        |
| `firebase-architecture` | mobile-builder   | community (Firebase best practices)              |
| `mobile-testing`        | mobile-builder   | community (Flutter + E2E testing)                |
| `code-review`           | mobile-reviewer  | anthropics/claude-code (official)                |
| `security-review`       | mobile-reviewer  | anthropics/claude-code-security-review           |


# Auto-Resume System

## STARTUP CHECK (Her session başında çalıştır)
Before doing ANYTHING else, run:
```bash
if [ -f .claude_progress.md ]; then
  echo "▶️ RESUMING" && cat .claude_progress.md
else
  echo "🆕 NEW SESSION"
fi
```

## RULES
1. Her görev başında `.claude_progress.md` oluştur
2. Her büyük adımdan sonra dosyayı güncelle
3. Token/rate limit yaklaşınca durumu kaydet, STATUS: WAITING yaz
4. Resume edilince dosyayı oku, kaldığın yerden devam et — sıfırdan başlama

## PROGRESS FILE FORMAT

```markdown
# Claude Progress — [Görev Adı]
**Session:** [ISO timestamp]
**Task:** [1 satır açıklama]
**STATUS:** IN_PROGRESS | WAITING | COMPLETE

## Tamamlanan Adımlar
- [x] Adım 1 — açıklama
- [x] Adım 2 — açıklama

## Şu Anki Adım
- [ ] Adım 3 — devam ediyor
  - Son aksiyon: [ne yapıldı]
  - Sonraki aksiyon: [ne yapılacak]

## Kalan Adımlar
- [ ] Adım 4
- [ ] Adım 5

## Bağlam (Context)
[State'i geri yüklemek için gereken önemli bilgiler]
[Hangi dosyalar değişti, hangi değerler kullanıldı vb.]
```

## KURALLAR (Detay)

- **Yeni görev başlarken:** `.claude_progress.md` oluştur, STATUS: IN_PROGRESS yaz
- **Her büyük adım sonrası:** `[x]` ile işaretle, dosyayı güncelle
- **Context window dolmadan önce:** STATUS: WAITING yap, "Sonraki aksiyon" alanını doldur
- **Session başında:** dosya varsa oku → kaldığın yerden devam et, yoksa yeni session
- **Görev bitince:** STATUS: COMPLETE yap, dosyayı sil (`rm .claude_progress.md`)