# CLAUDE.md

## Project Context

This repository currently corresponds to **Exercise 02** of the course **Integración de Aplicaciones Computacionales**.

The active scope is the monolithic online library application.

## Current Scope

Work only on the monolithic application located under:

`apps/web-monolito01/backend-node/`

The following items are intentionally outside the scope of Exercise 02 and must not be reintroduced unless explicitly requested:

- `services/`
- SOAP-related work
- Microservices
- XML microservice exercises
- Exercise 03 files or prompts

## Required Architecture

The application must remain a **server-side rendered monolith** using:

- Node.js
- Express
- EJS
- PostgreSQL
- `pg` for direct database access

Do not introduce:

- REST APIs
- GraphQL
- SOAP
- Microservices
- JSON as the normal frontend-backend exchange mechanism
- XML as the normal frontend-backend exchange mechanism
- A separate SPA frontend

HTML forms must submit directly to the Express monolith, and EJS must remain the presentation mechanism.

---

## Sources of Truth

Before making changes, review the relevant project documentation.

### Requirements

- `docs/REQUIREMENTS.md`

### Engineering decisions

- `docs/ENGINEERING_DECISIONS.md`

### Current implementation status

- `docs/REQUIREMENTS_COMPLIANCE.md`
- `docs/REQUIREMENTS_COMPLIANCE.xlsx`

### Database design

- `docs/NORMALIZATION_4FN.xlsx`
- `docs/DB_DESIGN_ER_4FN.drawio`
- `docs/DB_DESIGN_ER_4FN.png` when available

### Architecture

- `docs/ARCHITECTURE_MONOLITHIC.drawio`
- `docs/ARCHITECTURE_MONOLITHIC.png` when available

### Existing exercise context

- `01-prompt-monolito.md`

If there is a contradiction between the implementation and the documentation, do not silently choose one. Report the contradiction before modifying the code.

---

## Database Context

The application uses PostgreSQL.

Expected application database:

- Database: `library_db`
- Application user: `library_user`

Never hardcode the real password.

The final model is documented as normalized to **4NF**.

Important relational rules include:

- A book may have multiple authors.
- An author may participate in multiple books.
- A book may have multiple genres.
- A genre may classify multiple books.
- A book may contain multiple concepts.
- A concept may appear in multiple books.
- The definition belongs to the `book-concept` relationship.
- A book may have multiple images.
- Format and category are independent catalogs.
- There may be at most one Administrator.
- There may be at most one cover image per book.

Do not collapse bridge tables back into lists or repeated columns.

---

## Security Rules

Always preserve or improve the following controls:

- Use parameterized PostgreSQL queries through `pg`.
- Never concatenate user-controlled input into SQL.
- Never hardcode credentials, passwords, tokens, SSH keys, or session secrets.
- Keep `.env` outside version control.
- Keep only non-sensitive placeholders in `.env.example`.
- Store passwords only as secure hashes.
- Keep authentication and authorization as separate concerns.
- Validate server-side even when HTML validation exists.
- Do not expose SQL errors, stack traces, credentials, or internal paths to end users.
- Validate uploaded files by:
  - allowed extension,
  - MIME type,
  - maximum size,
  - system-generated filename.
- Only JPG/JPEG, PNG and WebP are allowed for book images.
- The application must use a PostgreSQL application user with minimum required privileges.

---

## Role Model

The system has three relevant actors:

### Visitor

May:

- access login,
- access registration,
- access explicitly public pages.

May not:

- view the private catalog,
- view private book details,
- use administrative operations.

### Registered User

May:

- login/logout,
- view the catalog,
- search by ISBN or title,
- view book details and related information.

May not:

- create, modify, or delete administrative data.

### Administrator

May:

- perform all registered-user operations,
- manage books,
- manage authors,
- manage genres,
- manage formats,
- manage categories,
- manage concepts,
- manage book-author relations,
- manage book-genre relations,
- manage book-concept definitions,
- manage images,
- manage users where applicable.

There must be at most one Administrator.

---

## Development Workflow

For every requested change:

1. Read `CLAUDE.md`.
2. Read the related requirement(s) in `docs/REQUIREMENTS.md`.
3. Check the current status in `docs/REQUIREMENTS_COMPLIANCE.md`.
4. Inspect the existing implementation before editing.
5. Identify the smallest set of files that need to change.
6. Explain the intended change before editing when requested.
7. Implement only the requested requirement.
8. Do not refactor unrelated code.
9. Preserve the current monolithic architecture.
10. Report all modified files.
11. Explain how the change should be tested.
12. Do not mark a requirement as complete without a verification step.

When possible, prefer small, reviewable changes over broad rewrites.

---

## Change Discipline

Do not:

- redesign the full application unless explicitly requested,
- replace working modules without a concrete reason,
- rename large parts of the project unnecessarily,
- change the database model without checking the 4NF documentation,
- add new dependencies without justification,
- introduce an ORM,
- move the project to TypeScript,
- replace EJS with a frontend framework,
- reintroduce Exercise 03 material,
- modify `apps/services/` even if it appears again later, unless explicitly requested.

If a requested change requires one of these actions, explain why before proceeding.

---

## Required Evidence

Each completed change should leave enough evidence to be documented later.

For each change report:

- requirement ID,
- files modified,
- reason for each modification,
- risk introduced,
- validation performed,
- result observed.

These records will later support:

- `docs/TEST_PLAN.xlsx` or `.md`
- `docs/SECURITY_REVIEW.md`
- `AI_PROMPT_HISTORY.md`
- `AI_CHANGELOG.md`
- final engineering report
- final evidence website

---

## Current Priority Backlog

Work in this order unless explicitly instructed otherwise.

### P0-01 — Protect catalog and book detail

Related requirements:

- RF-04
- RF-05
- RF-07
- RA-12

Expected change:

- Require authentication for `GET /libros`.
- Require authentication for `GET /libros/:isbn`.
- Keep login and registration public.

Validation:

- Authenticated user can access catalog and detail.
- Visitor is redirected to login or receives the controlled unauthenticated response.

---

### P0-02 — Search by ISBN and title

Related requirement:

- RF-06

Expected change:

- Search must support ISBN and title.
- Keep the SQL parameterized.

Validation:

- Search by complete ISBN.
- Search by a title fragment.
- Search without matches.
- Search using special characters without altering SQL behavior.

---

### P0-03 — Harden image uploads

Related requirements:

- RF-17
- RNF-14

Expected change:

- Allow only JPG/JPEG, PNG and WebP.
- Remove GIF support.
- Validate MIME in addition to extension.
- Keep maximum file-size validation.
- Keep system-generated filenames.
- Add or complete image metadata editing if missing.

Validation:

- Valid JPG/PNG/WebP is accepted.
- GIF is rejected.
- A file with a fake image extension and invalid MIME is rejected.
- Oversized file is rejected.
- Cover-image rule is preserved.

---

### P0-04 — Remove sensitive fallbacks and enforce application DB user

Related requirements:

- RNF-02
- RNF-12

Expected change:

- Do not keep a hardcoded PostgreSQL password fallback.
- Do not keep a default production session secret.
- Use environment variables.
- `.env.example` must not contain a real password.
- Database name/example user should reflect `library_db` and `library_user`.

Validation:

- Application starts with correctly configured environment variables.
- Missing required secrets fail clearly.
- Repository contains no real credentials.

---

### P0-05 — Complete server-side validation

Related requirement:

- RF-21

Expected change:

Review and complete server-side validation for:

- email format,
- numeric IDs,
- book values,
- relationship inputs,
- image metadata,
- other fields that currently rely only on HTML or PostgreSQL.

Validation:

- Invalid input is rejected in a controlled way.
- No internal SQL or stack information is shown to the user.

---

## Deployment Work

Do not implement final deployment changes until explicitly requested.

Later, the application must:

- listen on `127.0.0.1:3000`,
- be published through Apache or NGINX,
- work under `/library`,
- preserve login,
- preserve sessions,
- preserve static assets,
- preserve image uploads,
- preserve redirects.

This work is intentionally deferred until the implementation, database, security and testing phases are completed.

---

## Final Rule

Before changing code, understand the existing implementation first.

The goal is not to generate a new application. The goal is to **bring the current application into compliance with Exercise 02 while preserving what already works**.
