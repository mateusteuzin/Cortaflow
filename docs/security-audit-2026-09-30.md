# Security audit - 2026-09-30

Scope: local source review of FastAPI authentication, authorization, tenant-scoped
queries, public booking data, Web Push, image uploads, PostgreSQL schema, runtime
headers, Docker and Python dependencies. No production database, Stripe account,
email provider or deployed environment was changed or queried with credentials.
Email and frontend changes are reviewed separately by the coordinating agent.

## Findings corrected in source

### High: public phone-only customer lookup

`GET /api/public/barbearias/{slug}/reservas/{telefone}` disclosed appointment dates,
services, assigned professional and status to anyone knowing a phone number.
The public loyalty endpoint disclosed attendance counts under the same condition.
Knowing a phone number is not proof of ownership; per-IP throttling did not fix
this authorization failure. Both endpoints now return HTTP 403 before querying
the database and direct the customer to the shop. Re-enabling self-service lookup
requires verified ownership, such as a short-lived one-time link or OTP, with an
explicit privacy design. The public booking creation flow remains available.

### High: authenticated Web Push SSRF

Subscription validation previously accepted any string beginning with `https://`.
The sender passed the endpoint to `pywebpush`, whose requests transport follows
redirects. A panel user could cause outbound requests to attacker-chosen HTTPS
destinations, including private services. Validation now accepts only the supported
browser provider hosts (FCM, Mozilla, Apple and Windows notification hosts), rejects
credentials, unexpected ports, whitespace and fragments, and repeats validation
for stored records before sending. The dedicated requests session disables
redirects and validates the URL at the transport boundary. Push timeout is ten
seconds. Failure logs omit provider exceptions that can contain subscription URLs.
New providers require a deliberate allowlist update.

### High/conditional: Supabase browser database exposure

The supplied SQL had no RLS or restrictions for Supabase `anon`/`authenticated`
roles. Exposure depends on actual grants and the deployed API configuration, which
were not accessible during this audit. New schema creation now enables RLS on all
16 private application tables. Migration
`sql/017_deny_browser_database_access.sql` enables RLS and explicitly revokes table
privileges for those browser roles when present. It has NOT been executed.

The migration must run as table owner after checking that the backend connection
uses an owner/BYPASSRLS role. No browser policies are provided because the app
authenticates and scopes tenants through FastAPI. This protects direct browser
access but does NOT make backend SQL tenant-isolated at the database layer:
owner/BYPASSRLS queries still depend on explicit tenant predicates. Verify real
grants, inherited grants, existing policies, views, security-definer functions,
Storage policies and REST exposure before deployment. Do not claim production
RLS protection merely because the migration exists locally.

### Medium: credentials and customer responses cacheable

Login/bootstrap responses and most API responses lacked `Cache-Control: no-store`.
All completed API responses now set it. Landing URLs carrying bootstrap `code`,
verification `token`, `checkout_token` or password-reset tokens additionally use
`Referrer-Policy: no-referrer` and `no-store`, closing same-origin referrer leakage
from credential-bearing navigation. Existing CSP, nosniff, clickjacking protections
and HTTPS HSTS remain active.

### Medium: retained rate-limit state

Rate-limit dictionaries permanently retained keys for inactive clients. Periodic
cleanup now removes buckets beyond the largest applicable window. This fixes
unbounded lifetime retention, not distributed enforcement or cardinality under a
large flood of active source addresses.

### Medium: vulnerable dependencies

The initial `pip-audit` report contained 38 advisory entries across PyJWT,
python-multipart and Starlette; counts include overlapping advisory identifiers
and do not establish that every advisory is reachable in this app. Pinned versions
are now FastAPI 0.142.2, Starlette 1.3.1, PyJWT 2.15.0 and python-multipart 0.0.31.
FastAPI was upgraded to support patched Starlette. Pydantic 2.10.4 remains
compatible. Follow-up `pip-audit -r requirements.txt` reports no known
vulnerabilities. Reports: `artifacts/dependency-audit.json` and
`artifacts/dependency-audit-fixed.json`. This is a dated advisory scan, not a claim
that the software is free of all vulnerabilities.

### Defense in depth: container privileges and build context

Docker runs the API as an unprivileged system user and grants write access only
to the local image upload directory. The container explicitly defaults to
`ENVIRONMENT=production`, activating the existing strong SECRET_KEY startup
check. `.dockerignore` excludes real dotenv files, uploaded customer images,
local virtual environments and temporary output from build context. Container
build/run was not verified because no Docker daemon validation was performed.

### Medium: incomplete Stripe subscription contract validation

The catalog validator checked BRL unit amount and `interval=month` but accepted
`interval_count=12`, arbitrary quantity or absent cadence/quantity fields. This
could classify a different billing contract as the normal monthly SaaS plan.
It now requires exactly one item with quantity one and a one-month interval.
Malformed or incomplete subscriptions fail closed with HTTP 409. The regression
test was observed failing for all five altered-contract examples before the fix.

## Controls checked and remaining work

- Authentication rejects missing, expired and invalid tokens, fixes HS256 as the
  allowed algorithm, validates issuer/audience/type, and checks `auth_version`
  against the database. Logout/password reset revoke existing tokens. Production
  checks reject the development secret and short/placeholder secrets.
- The default bearer lifetime is eight hours, configurable from 15 minutes to
  seven days. There is no idle expiration, device session registry, refresh-token
  rotation, per-device revocation or MFA. These require coordinated product and
  frontend work. Browser localStorage bearer tokens remain vulnerable to theft
  after an XSS; CSP reduces but does not eliminate this risk.
- Owner-only routes use `owner_user`; barber agenda/profile operations scope to
  the linked barber and shop. Product/service/customer/expense mutations include
  the session shop. Tenant isolation regression tests pass, but tests using mocked
  cursors do not replace live multi-tenant PostgreSQL integration checks.
- Login/register/reset throttles are in-memory per process. Multiple workers and
  serverless cold starts can bypass aggregate limits. A shared atomic store and
  edge abuse protection remain necessary for strong production brute-force
  protection. Vercel client identity trusts its forwarded header; verify the actual
  trusted proxy contract. Self-hosted proxy trust also needs deployment review.
- Uploads require panel authentication, reject SVG/HTML MIME types, cap the read
  at five MiB, verify supported raster signatures and generate filenames scoped
  to the authenticated shop. They do not fully decode/re-encode image contents,
  reject decompression bombs by decoded dimensions, or enforce a whole HTTP
  request limit before multipart parsing. Add an edge request-size limit and
  image decoding/re-encoding validation if hostile authenticated uploads are in
  scope. Private data must never be uploaded to the public image bucket.
- Stripe webhook signature, idempotency and server-controlled price checks have
  passing regression coverage. Client redirects alone do not activate a plan.
  Production webhook secrets, customer mappings and replay handling must still
  be verified against the actual deployment configuration.

## Verification

Regression cases were written and observed failing before the corresponding
runtime fixes. Targeted security/authentication/storage tests passed. A full run
after patched dependency installation and Stripe contract validation passed all 175 tests:

```text
.venv/Scripts/python.exe -m unittest discover -s tests
Ran 175 tests in 0.963s - OK
.venv/Scripts/python.exe -m pip check
No broken requirements found.
.venv/Scripts/python.exe -m pip_audit -r requirements.txt --format json --output artifacts/dependency-audit-fixed.json
No known vulnerabilities found
```

Three initial failing barber access tests were stale: two expected old date
parameters instead of existing half-open datetime bounds and one omitted a plan
from its fixture. Updated assertions still enforce shop, linked barber, owner
identity and complete date bounds; no production authorization was weakened.

No live PostgreSQL migration, real webhook delivery, network penetration test,
Docker build, production deployment or production secret rotation was performed.
