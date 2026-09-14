REQUIREMENTS_COMPLIANCE.md

Exercise 02 — Monolithic Library Application

This document is the Markdown companion to REQUIREMENTS_COMPLIANCE_UPDATED.xlsx.

Scope reviewed: apps/web-monolito01/backend-node/
Excluded from scope: apps/services/, SOAP work, microservices, XML service work and Exercise 03 material.

1. Current Status

After the code corrections P0-01 to P0-05 and manual validation against the real PostgreSQL database library_db, the status is:

Status

Count

Complies

43

Partially complies

6

Does not comply

1

Pending

3

Total evaluated

53

The manual validation used:

Node.js running locally on Windows.

PostgreSQL in the GCP VM.

SSH local port forwarding to reach PostgreSQL securely.

Real users stored in library_db.

A regular Registered User.

The existing Administrator account.

2. Validation Confirmed

The following functional flows were manually validated against the real database:

User registration.

Login as Registered User.

Login as Administrator.

Catalog access control.

Book detail access control.

Search by ISBN.

Search by title.

Book creation.

Book deletion.

Image upload and image-management flow.

Concept creation and deletion.

Genre creation and deletion.

Author creation and deletion.

General catalog CRUD flows.

Book relationship workflows used during book creation.

This confirms that the main application flow is operating correctly after the P0 corrections.

3. P0 Status

P0-01 — Protect catalog and book detail

Status: Validated

Confirmed manually:

Visitor cannot access /libros.

Visitor cannot access a private book detail directly.

Registered User can access catalog and detail.

Administrator can access catalog, detail and administrative functions.

Related requirements:

RF-04

RF-05

RF-07

RA-12

P0-02 — Search by ISBN and title

Status: Validated

Confirmed manually against real data:

search by ISBN works;

search by title works.

Related requirement:

RF-06

A SQL Injection/special-character test will still be included formally in the final test matrix.

P0-03 — Image-management hardening

Status: Functionally validated, negative security cases still pending formal evidence

Confirmed:

image upload flow works;

image-management flow works.

Still required for the formal test plan:

GIF rejection;

fake MIME rejection;

file larger than 5 MB rejection;

one-cover-per-book negative/consistency case;

controlled error evidence.

Related requirements:

RF-17

RNF-14

P0-04 — Secure environment configuration

Status: Validated

Confirmed:

application starts with real environment variables;

application connects using:

library_db

library_user;

no real password was added to versioned files;

missing required environment variables were already verified to produce controlled startup errors.

Related requirements:

RNF-02

RNF-12

Still required before final publication:

verify .env remains ignored;

inspect Git status/history for accidental secrets;

document the effective PostgreSQL privileges of library_user.

P0-05 — Server-side validation

Status: Functionally validated, negative-input cases still pending formal evidence

Normal application workflows operate after the new validation layer.

The final test matrix must still explicitly validate:

invalid email;

negative price;

negative stock;

non-integer stock;

invalid publication year;

invalid numeric route/relationship IDs;

incomplete book-author/book-genre/book-concept association;

invalid image inputs.

Related requirement:

RF-21

4. Requirements Updated to Complies

The following requirements are now considered implemented and functionally validated:

RF-04 — Authentication access control

RF-05 — Catalog consultation

RF-06 — ISBN/title search

RF-07 — Book detail

RF-08 — Book CRUD

RF-09 — Author CRUD

RF-10 — Genre CRUD

RF-11 — Format CRUD

RF-12 — Category CRUD

RF-13 — Concept CRUD

RF-14 — Multiple authors per book

RF-15 — Multiple genres per book

RF-16 — Book-specific concepts/definitions

RF-19 — User/role administration

RNF-02 — Protection of secrets/configuration

RNF-04 — Authentication and authorization separation

RNF-12 — PostgreSQL application user

RA-12 — Registered users only in private areas

5. Requirements That Remain Partial

RF-17 — Image management

The positive flow works.

Still needs negative evidence for:

GIF;

MIME spoofing;

oversize file;

validation-error behavior.

RF-21 — Server-side validation

The implementation is present and normal workflows work.

Still needs explicit negative-input tests.

RNF-09 — Basic performance

The application works for the academic workload, but the current title-search strategy and the existing GIN index are not perfectly aligned.

This is low priority unless performance becomes a problem.

RNF-10 — Usability

The interface works, but formal navigation/usability evidence has not yet been documented.

RNF-13 — Secure session handling

Current session functionality works.

Production hardening will be reviewed during reverse-proxy deployment.

RNF-14 — Secure file validation

Implementation is present, but explicit negative file tests still need to be captured.

6. Remaining Non-Compliant Requirement

RA-14 — Node.js must listen on 127.0.0.1:3000

Status: Does not comply yet

This is intentionally deferred until the deployment phase.

Later, src/server.js must explicitly bind Node.js to:

127.0.0.1:3000

and the public application must be exposed only through Apache or NGINX.

7. Pending Requirements

RNF-15 — Basic availability

Pending runtime evidence from the final deployed environment.

RNF-16 — Reverse proxy deployment

Pending final deployment.

RA-15 — /library under Apache/NGINX

Pending final deployment.

8. Important Functional Gap Outside P0

The implementation now works, but the final database deliverables still require work.

The next major phase should address:

db/00_create_database.sql

db/01_schema.sql

db/02_seed_30_per_table.sql

db/03_all_quieries_before_stored_procedures.sql

db/04_stored_procedures.sql

db/05_triggers.sql

db/06_views.sql

The final seed must also include a Cloud Computing book with definitions for the concepts requested by the exercise:

IaaS

PaaS

SaaS

FaaS

Bucket

Public Cloud

Private Cloud

Hybrid Cloud

Multicloud

Serverless

9. Testing Still Required

The fact that the positive application flow works does not replace the required test matrix.

The final TEST_PLAN must include positive and negative cases such as:

login/logout;

authorization by role;

search;

each CRUD;

duplicate ISBN;

negative stock;

invalid price;

invalid FK;

restricted deletion;

second Administrator;

second cover image;

invalid upload extension;

invalid MIME;

file too large;

SQL Injection/special characters;

book-author relationship;

book-genre relationship;

book-concept relationship;

final reverse proxy deployment.

10. Recommended Next Step

With P0 implementation now stable, proceed to the database deliverables phase.

Recommended order:

Review the current sql/schema.sql.

Convert it into the required db/01_schema.sql.

Create db/00_create_database.sql.

Build db/02_seed_30_per_table.sql.

Add the required Cloud Computing dataset.

Define the application queries before stored procedures.

Implement stored procedures.

Separate/complete triggers.

Create views.

Execute and document PostgreSQL integrity tests.