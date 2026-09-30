# CortaFlow Professional SaaS Implementation Plan

Goal: implement the approved visual brief and audit the supplied security checklist.
Spec: ../specs/2026-09-30-cortaflow-design.md
Stack: FastAPI, PostgreSQL, vanilla HTML/CSS/JavaScript.

## Decisions

Execute in the current downloaded directory: this is not a Git checkout.
Use independent security and email workers; frontend changes belong to the main agent.
Never connect to production, send real messages or execute migrations during validation.
Keep existing API and DOM contracts unless they expose personal information.
Security findings that require infrastructure access remain explicitly unverified.

## Tasks

- [ ] Consolidate semantic design tokens and professional component styling for panel, booking and public landing.
- [ ] Fix booking request races, stale selection, inaccessible selection state and misleading delivery copy; test these with mocked API responses in a real browser.
- [ ] Unify transactional email presentation; run delivery/escaping regression tests.
- [ ] Audit authentication, tenant filters, public data access, headers, uploads, dependencies and Docker; fix evidenced weaknesses with regression tests.
- [ ] Run the existing suite and dependency audit; fix relevant failures.
- [ ] Verify desktop/mobile, light/dark panel and complete booking with simulated data; inspect screenshots.
- [ ] Deliver a running local server, screenshots and security report with verified and outstanding controls.

## Review Focus

Out-of-order availability responses cannot replace the latest selection.
No public phone-only endpoint may disclose personal reservation or attendance data.
Long names and slow network cannot break the booking screen or enable stale slots.
Email user input must remain escaped and delivery errors must not undo reservations.
RLS script presence is not proof that production RLS is active or backend connections obey it.
