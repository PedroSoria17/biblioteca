# REQUIREMENTS_COMPLIANCE.md

## Exercise 02 — Monolithic Library Application

This document is the Markdown companion to `REQUIREMENTS_COMPLIANCE.xlsx`.

It is intended to be read easily by developers and coding assistants while working on the repository.

**Scope reviewed:** `apps/web-monolito01/backend-node/`  
**Excluded from scope:** `apps/services/`, SOAP work, microservices, XML service work and Exercise 03 material.

---

# 1. Status Summary

Current static review result:

| Status | Count |
|---|---:|
| Complies | 36 |
| Partially complies | 11 |
| Does not comply | 3 |
| Pending | 3 |
| **Total evaluated** | **53** |

Interpretation:

- **Complies:** the implementation exists and is consistent with the requirement by static review.
- **Partially complies:** the implementation exists but an important condition is still missing.
- **Does not comply:** there is a clear contradiction between the current implementation and the requirement.
- **Pending:** the requirement depends on execution, infrastructure or a later phase.

Static review is not final proof. Functional, security and database tests are still required.

---

# 2. Priority Changes

## P0-01 — Protect catalog and book detail

**Status:** Pending correction  
**Priority:** High

### Related requirements

- RF-04 — Authentication access control
- RF-05 — Catalog for authenticated users
- RF-07 — Book detail
- RA-12 — Only registered users access private areas

### Current finding

Authentication and authorization middleware already exist, but the book catalog and detail GET routes are currently public.

### Main file

`src/modules/libros/libro.routes.js`

### Required change

- Add authentication protection to `GET /libros`.
- Add authentication protection to `GET /libros/:isbn`.
- Keep login and registration public.

### Verification

- Visitor attempts `/libros` → redirected to login or controlled unauthenticated response.
- Visitor attempts `/libros/<isbn>` → redirected to login or controlled unauthenticated response.
- Registered User can access both.
- Administrator can access both.

---

## P0-02 — Search by ISBN and title

**Status:** Partial  
**Priority:** High

### Related requirement

- RF-06 — Search by ISBN and title

### Current finding

The current search is parameterized but only filters by title using `ILIKE`.

### Main files

- `src/modules/libros/libro.model.js`
- `src/views/libros/lista.ejs`

### Required change

Search must support:

- ISBN
- title

The query must remain parameterized.

### Verification

- Search a complete ISBN.
- Search a valid title fragment.
- Search a value with no matches.
- Search text containing special SQL characters.

---

## P0-03 — Harden image uploads and metadata management

**Status:** Partial  
**Priority:** High

### Related requirements

- RF-17 — Image management
- RNF-14 — Secure file validation

### Current finding

The system already supports image upload, deletion, cover selection, generated filenames and a 5 MB size limit.

Remaining problems:

- GIF is currently accepted.
- The exercise allows only JPG/JPEG, PNG and WebP.
- MIME validation is missing.
- Post-upload editing of some metadata is incomplete.

### Main files

- `src/middleware/upload.js`
- `src/modules/libros/libro.controller.js`
- image-related models
- `src/views/libros/formulario.ejs`

### Required change

- Remove GIF support.
- Validate allowed extension.
- Validate MIME.
- Keep maximum-size validation.
- Keep generated filenames.
- Preserve one-cover-per-book rule.
- Complete image metadata editing where necessary.

### Verification

Positive:

- JPG/JPEG accepted.
- PNG accepted.
- WebP accepted.

Negative:

- GIF rejected.
- Fake `.jpg` with non-image MIME rejected.
- Oversized image rejected.
- Unsupported extension rejected.

---

## P0-04 — Remove sensitive configuration fallbacks

**Status:** Does not comply  
**Priority:** High

### Related requirements

- RNF-02 — Protection of secrets
- RNF-12 — PostgreSQL minimum privilege

### Current finding

The application can read database configuration from environment variables, but the current code/example still contains insecure or misleading defaults.

Examples found during static review:

- PostgreSQL fallback values using `postgres`.
- A fallback session secret.
- `.env.example` oriented toward the `postgres` superuser.

### Main files

- `src/config/db.js`
- `src/app.js`
- `.env.example`

### Required change

- Remove real/default database password fallback.
- Make sensitive configuration explicit through environment variables.
- Make the session secret mandatory for the intended deployment.
- Use the application database naming in examples:
  - `PGDATABASE=library_db`
  - `PGUSER=library_user`
- Never put the real password in the repository.
- Do not run the application as PostgreSQL superuser.

### Verification

- Application runs using the configured application user.
- Missing sensitive variables produce a clear controlled startup failure.
- Git repository contains no real credentials.

---

## P0-05 — Complete server-side validation

**Status:** Partial  
**Priority:** High

### Related requirement

- RF-21 — Server-side validation

### Current finding

Server-side validation already exists in several controllers and catalog operations, but coverage is incomplete.

Areas to review:

- email format,
- numeric relationship IDs,
- image MIME,
- ranges,
- relationship input,
- optional/required fields.

### Required change

Centralize or complete validation without unnecessary architectural changes.

### Verification

Invalid values should be rejected before producing unintended database changes and should return controlled messages.

---

# 3. Functional Requirements Review

## RF-01 — User registration

**Status:** Complies

Current implementation includes public registration, basic validation, password hashing and unique email protection.

### Still needed

Formal runtime evidence:

- valid registration,
- duplicate email,
- invalid input.

---

## RF-02 — Login

**Status:** Complies

Current implementation:

- checks an active user,
- compares password hash,
- creates a session,
- recognizes administrator status,
- uses a generic authentication error.

### Still needed

Runtime tests for:

- valid credentials,
- invalid password,
- unknown email,
- inactive user.

---

## RF-03 — Logout

**Status:** Complies

Logout destroys the session and redirects the user.

### Still needed

Verify that private routes become inaccessible after logout.

---

## RF-04 — Authentication access control

**Status:** Does not comply

The middleware exists, but catalog and detail routes are currently public.

### Action

See P0-01.

---

## RF-05 — Catalog consultation

**Status:** Partially complies

The catalog exists but is not currently restricted to authenticated users.

### Action

See P0-01.

---

## RF-06 — Search by ISBN and title

**Status:** Partially complies

Current search supports title only.

### Action

See P0-02.

---

## RF-07 — Book detail

**Status:** Partially complies

Book detail already displays:

- ISBN,
- publication year,
- format,
- category,
- price,
- stock,
- authors,
- genres,
- concepts,
- definitions,
- images.

The remaining issue is authentication.

### Action

See P0-01.

---

## RF-08 — Book CRUD

**Status:** Complies

Create, read, update and delete operations exist and administrative routes are protected.

### Observation

~~When a book is deleted, database image records may be removed by cascading behavior while physical files can remain in the filesystem.~~

**Implemented (2026-09-07, Prompt 05):** `libro.controller.js` now reads the book's `imagenes_libro` rows before deleting it, deletes the book in PostgreSQL first, and only then attempts to unlink each associated physical file (via the shared `src/lib/uploadsFs.js` helper, tolerant of already-missing files). **Not yet validated at runtime** against `library_db_test` — see the manual test steps in the Prompt 05 delivery report.

### Recommended improvement

~~Delete associated physical image files when deleting a book.~~ Done in code; pending runtime confirmation.

---

## RF-09 — Author CRUD

**Status:** Complies

Administrative CRUD exists.

### Still needed

Runtime tests for:

- create,
- edit,
- delete,
- referential-integrity rejection.

---

## RF-10 — Genre CRUD

**Status:** Complies

Administrative CRUD exists and genre name uniqueness is protected in PostgreSQL.

### Optional improvement

Handle duplicate-value database errors with a friendlier validation message.

---

## RF-11 — Format CRUD

**Status:** Complies

Administrative CRUD exists and format name is unique.

### Still needed

Test deletion when referenced by a book.

---

## RF-12 — Category CRUD

**Status:** Complies

Administrative CRUD exists and category name is unique.

### Still needed

Test deletion when referenced by a book.

---

## RF-13 — Concept CRUD

**Status:** Complies

Concepts are independent catalog entries and the definition is correctly stored in the book-concept relationship.

### Still needed

Verify that one concept can appear in two books with different definitions.

---

## RF-14 — Multiple authors per book

**Status:** Complies

The system uses a bridge table and supports book-author relationships.

### Still needed

Test:

- multiple authors,
- duplicate association,
- author order.

---

## RF-15 — Multiple genres per book

**Status:** Complies

The system uses the `libro_genero` bridge relation.

### Still needed

Test multiple genres and duplicate association behavior.

---

## RF-16 — Book-specific concepts and definitions

**Status:** Complies

The schema and implementation correctly place the definition on the `(ISBN, concepto_id)` relationship.

### Remaining deliverable

Add a Cloud Computing book containing the concepts requested by the exercise, including:

- IaaS
- PaaS
- SaaS
- FaaS
- Bucket
- Public Cloud
- Private Cloud
- Hybrid Cloud
- Multicloud
- Serverless

---

## RF-17 — Image management

**Status:** Partially complies

### Action

See P0-03.

---

## RF-18 — Price and stock

**Status:** Complies

Application logic and PostgreSQL constraints reject negative values.

### Still needed

Test both through the application and directly in PostgreSQL.

---

## RF-19 — User administration

**Status:** Complies

The current application includes administrative user operations.

### Observation

The project does not appear to provide a separate admin-side "create user" flow; public registration already creates users.

### Later validation

Confirm whether the professor expects Create to be present specifically inside the `/usuarios` administrative section.

---

## RF-20 — Single Administrator

**Status:** Complies

The database contains a partial unique index that prevents a second Administrator.

The application also contains an administrative transfer flow.

### Recommended hardening

~~Validate that the target user exists before transferring Administrator status so an invalid target cannot leave the system without an Administrator.~~

**Implemented (2026-09-07, Prompt 05):** `sp_usuario_transferir_administracion` (`db/04_stored_procedures.sql`) now locks and validates the target user (`SELECT ... FOR UPDATE`) before touching the current Administrator: it raises a controlled error if the target does not exist or is inactive, and only then demotes/promotes. If the target is already the Administrator, it is a controlled no-op. **Not yet validated at runtime** against `library_db_test` — see the manual test steps in the Prompt 05 delivery report.

---

## RF-21 — Server-side validation

**Status:** Partially complies

### Action

See P0-05.

---

## RF-22 — Controlled error handling

**Status:** Complies

Internal errors are logged on the server and a generic message is shown to the user.

### Still needed

Test:

- 404,
- 403,
- internal error,
- absence of SQL/stack leakage.

---

# 4. Non-Functional Requirements Review

## RNF-01 — Password security

**Status:** Complies

Passwords are hashed with bcryptjs.

---

## RNF-02 — Secrets and credentials

**Status:** Partially complies

### Action

See P0-04.

---

## RNF-03 — SQL Injection protection

**Status:** Complies

The reviewed queries use PostgreSQL parameters.

### Still needed

Run SQL Injection-oriented test cases with special characters.

---

## RNF-04 — Authentication and authorization separation

**Status:** Complies

Separate middleware exists for authenticated users and Administrators.

### Important

The authentication middleware still needs to be applied to catalog and detail routes.

---

## RNF-05 — Data integrity

**Status:** Complies

The PostgreSQL schema contains:

- PK,
- FK,
- UNIQUE,
- CHECK,
- unique Administrator protection,
- unique cover-image protection.

### Still needed

Negative database tests and screenshots/evidence.

---

## RNF-06 — 4NF model

**Status:** Complies

The model and documentation have been prepared up to 4NF.

### Remaining repository work

Place/export:

- `docs/NORMALIZATION_4FN.xlsx`
- `docs/DB_DESIGN_ER_4FN.drawio`
- `docs/DB_DESIGN_ER_4FN.png`

---

## RNF-07 — Maintainability

**Status:** Complies

The monolith already separates configuration, middleware, modules, models/controllers, views and static resources.

---

## RNF-08 — Server-side rendering

**Status:** Complies

EJS is used and the application does not require a JSON API for normal operation.

---

## RNF-09 — Basic performance

**Status:** Partially complies

Search is performed by PostgreSQL.

### Observation

The schema includes a GIN full-text-style index for title, but the current search uses `ILIKE`, so the index does not directly optimize that query.

### Priority

Low for the current academic data volume.

---

## RNF-10 — Usability

**Status:** Partially complies

The application contains forms, navigation, messages and error views.

### Still needed

Formal navigation/usability tests and screenshots.

---

## RNF-11 — Error traceability

**Status:** Complies

Errors are logged server-side and controlled messages are displayed.

---

## RNF-12 — PostgreSQL minimum privilege

**Status:** Does not comply

### Action

See P0-04.

---

## RNF-13 — Secure session handling

**Status:** Partially complies

Login and logout session behavior exists.

### Remaining work

Before production/reverse-proxy deployment review:

- mandatory session secret,
- cookie configuration,
- `secure` when HTTPS is used,
- `sameSite`,
- proxy trust configuration if necessary.

---

## RNF-14 — Secure file validation

**Status:** Partially complies

### Action

See P0-03.

---

## RNF-15 — Basic availability

**Status:** Pending

This requires runtime evidence from the VM.

---

## RNF-16 — Reverse proxy deployment

**Status:** Pending

Deferred intentionally to the final phase.

Required later:

- Node.js on `127.0.0.1:3000`,
- Apache or NGINX,
- public `/library`,
- working routes,
- working static files,
- working sessions,
- working uploads,
- working redirects.

---

# 5. Architectural Restrictions Review

| ID | Restriction | Status |
|---|---|---|
| RA-01 | Monolithic solution | Complies |
| RA-02 | Node.js + Express | Complies |
| RA-03 | EJS server-side rendering | Complies |
| RA-04 | Direct PostgreSQL access with `pg` | Complies |
| RA-05 | Parameterized SQL | Complies |
| RA-06 | No REST API | Complies |
| RA-07 | No GraphQL | Complies |
| RA-08 | No SOAP inside Exercise 02 monolith | Complies |
| RA-09 | No microservices | Complies |
| RA-10 | No JSON/XML frontend-backend exchange | Complies |
| RA-11 | HTML forms submit directly to monolith | Complies |
| RA-12 | Registered users only in private areas | Partially complies |
| RA-13 | Maximum one Administrator | Complies |
| RA-14 | Node.js on `127.0.0.1:3000` | Does not comply yet |
| RA-15 | Apache/NGINX under `/library` | Pending |

---

# 6. Required Deliverables Status

| Deliverable | Current state | Next action |
|---|---|---|
| `docs/NORMALIZATION_4FN.xlsx` | Created | Copy into repository |
| `docs/DB_DESIGN_ER_4FN.drawio` | Created | Copy into repository |
| `docs/DB_DESIGN_ER_4FN.png` | Pending export | Export from draw.io |
| `docs/ARCHITECTURE_MONOLITHIC.drawio` | Created | Copy into repository |
| `docs/ARCHITECTURE_MONOLITHIC.png` | Pending export | Export from draw.io |
| `docs/REQUIREMENTS.md` | Created | Copy into repository |
| `docs/ENGINEERING_DECISIONS.md` | Created | Copy into repository |
| `docs/REQUIREMENTS_COMPLIANCE.xlsx` | Created | Copy into repository |
| `docs/REQUIREMENTS_COMPLIANCE.md` | This document | Keep in repository |
| `db/00_create_database.sql` | Missing | Create later |
| `db/01_schema.sql` | Partial | Adapt current `sql/schema.sql` |
| `db/02_seed_30_per_table.sql` | Missing/incomplete | Expand seed |
| `db/03_all_quieries_before_stored_procedures.sql` | Missing | Create later |
| `db/04_stored_procedures.sql` | Missing | Create later |
| `db/05_triggers.sql` | Partial | Separate/complete current trigger logic |
| `db/06_views.sql` | Missing | Create later |
| `docs/SECURITY_REVIEW.md` | Missing | Create after implementation fixes |
| `docs/TEST_PLAN.xlsx` or `.md` | Missing | Create after implementation fixes |
| `AI_PROMPT_HISTORY.md` | Missing | Create when recording AI-assisted changes |
| `AI_CHANGELOG.md` | Missing | Create when recording AI-assisted changes |
| Reverse proxy | Deferred | Final phase |
| Evidence website | Deferred | Final phase |

---

# 7. Database Seed Gap

The current seed is not yet sufficient for the final exercise requirement.

Current static review found approximately:

| Table / relation | Current rows |
|---|---:|
| formatos | 4 |
| categorias | 4 |
| generos | 6 |
| autores | 8 |
| conceptos | 5 |
| usuarios | 4 |
| libros | 10 |
| libro_autor | 12 |
| libro_genero | 12 |
| imagenes_libro | 10 |
| libro_concepto | 5 |

A final `db/02_seed_30_per_table.sql` still needs to be prepared according to the exercise instructions.

Do not overwrite the current working seed until the new script has been reviewed.

---

# 8. Recommended Implementation Order

Use this sequence:

1. **P0-01** Protect catalog and detail.
2. **P0-02** Add ISBN + title search.
3. **P0-03** Harden uploads.
4. **P0-04** Remove sensitive configuration fallbacks.
5. **P0-05** Complete server-side validation.
6. Reorganize database scripts.
7. Expand seed data.
8. Add stored procedures, triggers and views.
9. Run negative integrity tests.
10. Create `SECURITY_REVIEW`.
11. Create test matrix.
12. Document AI-assisted changes.
13. Implement `127.0.0.1:3000` and `/library`.
14. Configure Apache/NGINX.
15. Build final evidence website.

---

# 9. Working Rule

Do not attempt to fix every item in one change.

For each item:

1. implement one requirement or a tightly related group,
2. test it,
3. record evidence,
4. update this compliance document if the status changes,
5. then continue to the next item.

This keeps changes reviewable and makes the final engineering evidence easier to defend.
