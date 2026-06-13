# Open Source Operations And Reporting PRD

## Problem Statement

TinkerSpace Inventory Manager is close to a usable makerspace inventory platform, but it is not yet easy enough for non-technical makerspaces to self-host confidently, and it still lacks several operational controls expected from a serious open-source inventory tool.

Non-technical operators should be able to run the project from published Docker images without building the code locally, manually wiring services, or understanding Django deployment details. Once running, makerspace staff need stronger backend workflows for stock transfers, stock counting, operational analytics, printable QR batches, and exports that work in Excel and Google Sheets.

The system should keep its current strengths: QR-first workflows, makerspace scoping, RBAC, append-only audit logs, public inventory controls, and a gradual path from quantity-based handouts to serialized item handouts.

## Solution

Ship the project as an open-source, Docker-first application with production-ready images and a one-command hosting path. Add backend inventory operations for superadmin-only stock transfers, stocktake sessions, analytics, metrics, report exports, location/container QR management, and QR print batches.

This PRD covers the next major platform slice:

- Published Docker images for backend and frontend.
- A non-technical self-hosting path using Docker Compose.
- First-run setup support for creating the first superadmin and makerspace.
- Tenant-token bootstrap and per-tenant CORS for production multi-frontend deployments.
- Staff refresh tokens that last 7 days.
- Telegram request alerts that include requester email/phone, `requested_for`, and the full item list.
- Superadmin-only stock transfers between locations/containers/makerspaces.
- Stock counting and stocktake reconciliation.
- Analytics and metrics for what was taken, returned, damaged, missing, and currently out.
- Excel, CSV, and Google Sheets-friendly exports.
- Fully implemented location/container QR flows.
- A QR print-batch page where generated QR labels are collected for export/printing.
- A professional InvenTree-like frontend admin panel for inventory operations.
- A polished public inventory listing experience with search, filtering, and clean item detail views.
- Light theme by default with a persistent dark theme toggle.
- Guest admins can process returns for assigned makerspaces.
- Per-unit QR generation for serialized `InventoryAsset` records, with default names derived from the parent product.
- A migration path toward serialized handouts without forcing every item to be serialized immediately.

## User Stories

1. As a non-technical makerspace operator, I want to run the project from Docker images, so that I do not need to build the backend or frontend myself.
2. As a non-technical makerspace operator, I want a simple Docker Compose file, so that I can start the app with one command.
3. As a non-technical makerspace operator, I want a documented `.env` template, so that I know exactly which values I must change before hosting.
4. As a non-technical makerspace operator, I want clear setup docs, so that I can deploy without understanding Django internals.
5. As a first-time installer, I want a setup command or setup screen to create the first superadmin, so that I am not blocked after the containers start.
6. As a first-time installer, I want seed/demo data to be optional, so that I can choose between learning the app and starting clean.
7. As a maintainer, I want official Docker images published on each release, so that users can pin stable versions.
8. As a maintainer, I want image tags such as `latest` and version tags, so that deployments can choose between convenience and stability.
9. As a maintainer, I want health checks for backend, frontend, database, and object storage, so that operators can see whether the stack is working.
10. As a maintainer, I want upgrade notes and migration commands, so that self-hosted users can update safely.
11. As a superadmin, I want to transfer stock between locations, so that inventory can move from one room, cabinet, shelf, bin, box, or makerspace to another.
12. As a superadmin, I want transfers to be superadmin-only, so that ordinary staff cannot silently move stock across controlled locations.
13. As a superadmin, I want every stock transfer audited, so that I can trace who moved what and when.
14. As a superadmin, I want transfer records to include source and destination containers, so that physical movement matches the database.
15. As a superadmin, I want transfer records to include quantities or asset IDs, so that both quantity-counted and serialized stock can be moved.
16. As a superadmin, I want invalid transfers rejected, so that stock cannot become negative or cross tenant boundaries incorrectly.
17. As an inventory manager, I want to start a stocktake session, so that I can count actual physical stock in a room or container.
18. As an inventory manager, I want to scan location/container QR codes during stocktake, so that counts are tied to the right physical place.
19. As an inventory manager, I want to enter counted quantities, so that the system can compare actual stock to expected stock.
20. As an inventory manager, I want the stocktake to show variances, so that I can resolve missing, excess, or damaged items.
21. As a superadmin, I want to approve stocktake adjustments, so that count corrections are controlled.
22. As a superadmin, I want stocktake adjustments audited, so that inventory changes have an accountable reason.
23. As a staff member, I want analytics showing what has been taken, so that I can understand item demand.
24. As a staff member, I want analytics showing active loans, so that I can follow up on hardware that is still out.
25. As a staff member, I want analytics showing returns, damaged items, and missing items, so that I can see operational risk.
26. As a makerspace manager, I want metrics by item, user, makerspace, container, and date range, so that I can understand usage patterns.
27. As a makerspace manager, I want exportable reports, so that I can share data with teams who use Excel or Google Sheets.
28. As a makerspace manager, I want exports in CSV and XLSX, so that the data works across common spreadsheet tools.
29. As a makerspace manager, I want exports to preserve filters and date ranges, so that downloaded files match what I reviewed.
30. As a makerspace manager, I want a Google Sheets-friendly export flow, so that non-technical users can open reports in Google Sheets without manual cleanup.
31. As a superadmin, I want to export audit and inventory reports, so that external reviews can be supported.
32. As a staff member, I want location QR codes to represent rooms, cabinets, shelves, bins, and containers, so that scans can identify physical storage.
33. As a staff member, I want nested location/container QR codes, so that I can model Room -> Cabinet -> Shelf -> Bin -> Box.
34. As a staff member, I want to scan a location QR and see its contents, so that I can verify what should be there.
35. As a staff member, I want to move a box or item into a scanned location, so that physical organization stays current.
36. As a staff member, I want QR scan history for locations and containers, so that storage changes can be traced.
37. As a superadmin, I want to revoke location/container QR codes, so that retired or incorrect labels cannot be reused.
38. As a superadmin, I want generated QR codes collected into a print batch, so that I can print many labels at once.
39. As a superadmin, I want a print-ready QR page, so that labels can be exported to PDF or printed directly.
40. As a superadmin, I want label size options, so that QR labels fit common sticker sheets and label printers.
41. As a superadmin, I want each label to include human-readable text, so that staff can identify labels without scanning.
42. As a superadmin, I want QR print batches to be saved, so that I can reprint labels later.
43. As an inventory manager, I want quantity-based handouts to continue working, so that the system remains usable for consumables and low-value items.
44. As an inventory manager, I want selected products to use serialized assets, so that high-value tools can be tracked individually.
45. As an inventory manager, I want the handout workflow to gradually support scanned asset handouts, so that serialized tracking can be adopted product by product.
46. As an inventory manager, I want reports to distinguish quantity-counted and serialized items, so that analytics remain accurate during the transition.
47. As a space manager, I want a professional admin panel similar in quality and density to InvenTree, so that managing inventory feels reliable and production-ready.
48. As an inventory manager, I want a table-first admin interface with filters, saved views, bulk actions, and fast search, so that I can manage large inventories efficiently.
49. As an inventory manager, I want clear inventory detail pages with stock, locations, QR labels, movement history, stocktake history, and active loans, so that each item has one operational home.
50. As a superadmin, I want a dashboard with makerspace-wide operational metrics, so that I can quickly see stock health, active loans, overdue items, missing items, and recent activity.
51. As a staff member, I want scanner-friendly admin screens, so that QR workflows are usable at the physical storage location.
52. As a public visitor, I want a clean public inventory catalog, so that I can browse available items without seeing internal operational data.
53. As a public visitor, I want public inventory search and filters, so that I can quickly find hardware by name, category, availability, or makerspace.
54. As a public visitor, I want public item detail pages, so that I can understand what an item is before requesting it.
55. As a requester, I want the public request flow to feel simple and trustworthy, so that I can request hardware without needing staff help.
56. As any user, I want the app to default to a light theme, so that it feels approachable in normal lab and classroom environments.
57. As any user, I want a dark theme toggle, so that I can use the app comfortably in low-light spaces.
58. As any user, I want my theme preference remembered, so that the app keeps the same appearance between visits.
59. As an operator, I want the frontend to feel like a serious open-source operations tool, so that makerspaces trust it enough to adopt it.
60. As a staff member, I want Telegram request alerts to include requester email, phone, requested-for notes, and requested items, so that I can triage requests without opening the admin panel.
61. As a requester, I want my contact information to reach staff in Telegram alerts, so that staff can follow up if the request needs clarification.
62. As a frontend operator, I want a tenant-token bootstrap endpoint, so that each deployed frontend can discover its makerspace, public API key, enabled modules, branding, and safe API base URLs at runtime.
63. As a platform operator, I want CORS enforced per tenant/frontend, so that one makerspace frontend cannot silently act as another makerspace frontend.
64. As a staff user, I want refresh sessions to last 7 days, so that I do not need to log in repeatedly during normal weekly operations.
65. As a guest admin, I want permission to process returns for my assigned makerspace, so that handover volunteers can also close returned loans at the desk.
66. As a superadmin, I want guest-admin returns to use the same evidence, QR scan, remark, and audit requirements as other returns, so that return permissions do not weaken traceability.
67. As an inventory manager, I want to generate QR codes for each serialized unit, so that every physical asset can be tracked independently.
68. As an inventory manager, I want generated unit names to default from the parent product name, so that creating serialized assets is fast and labels remain understandable.
69. As a staff member, I want per-unit QR labels to appear in print batches, so that serialized asset labels can be printed with container and product labels.

## Implementation Decisions

- Docker distribution should publish separate backend and frontend images, plus a recommended production Compose file that references the published images rather than local build contexts.
- The backend image should continue to run migrations and static collection on startup unless a deployment-specific override disables it.
- A documented first-run path should create the first superadmin and first makerspace. This can be a management command first, then a setup UI later.
- Required production environment variables should be documented in a single self-hosting guide with safe defaults clearly separated from values that must change.
- Health endpoints should be added for the backend and surfaced through Docker health checks.
- Production multi-frontend support should use tenant-token bootstrap: a frontend starts with a tenant token or public code, calls a bootstrap endpoint, and receives only the makerspace/client configuration it is allowed to use.
- Per-tenant CORS should be enforced from registered frontend origins and API clients, not from a single global allowlist only.
- Bootstrap responses should include public makerspace identity, enabled modules, public API key or publishable client details, theme/branding metadata, and safe public endpoint roots. They must not expose server HMAC secrets, staff-only endpoints, evidence URLs, QR internals, audit logs, or private inventory fields.
- Staff refresh token lifetime should be 7 days. Access tokens may remain short-lived, but refresh cookies/tokens should support normal weekly staff usage.
- Telegram request messages must include requester contact email, requester contact phone, `requested_for`, and the full requested item list with quantities.
- Guest admins should gain `RETURN_REQUEST` for their assigned makerspaces. This amends the role design so guest admins may process returns but still cannot accept/reject, edit inventory, manage QR, manage staff, view full audit, or manage makerspace settings.
- Guest-admin returns must use the same backend return workflow as staff returns: matching box/tool QR scan where required, return evidence, required remark, item-level resolutions, accountability records, stock updates, and audit logs.
- Stock transfers should be implemented as a first-class backend workflow, not as direct product edits.
- Stock transfers must be superadmin-only for now, even if lower roles can view transfer history.
- A transfer should support quantity-counted products and serialized assets.
- A transfer should support source and destination containers/locations using the existing nested `Box` model unless a later migration splits physical locations into a separate model.
- The existing `Box` concept should be promoted into the canonical location/container hierarchy for now: rooms, cabinets, shelves, bins, handout boxes, and storage boxes are all QR-taggable containers with optional parent containers.
- Transfer actions should call inventory availability services for quantity math and should not update quantity buckets ad hoc.
- Stocktake should be modeled as sessions with counted lines, expected quantities, variances, approval state, and final adjustment records.
- Inventory managers may create and perform stocktake sessions within their makerspace, but final adjustments that change stock should require superadmin approval unless explicitly relaxed later.
- Analytics should be served from backend API endpoints and should be scoped by makerspace and RBAC.
- Analytics should include at minimum: top taken items, active loans, returns, damaged quantities, missing quantities, requester accountability, QR scan counts, direct handouts, and usage over time.
- Exports should be generated server-side so they match backend permission checks and filters.
- CSV and XLSX are required export formats. XLSX should use the existing `openpyxl` dependency.
- Google Sheets support should start as Google Sheets-compatible CSV/XLSX exports. Direct Google Drive/Sheets API publishing is a later optional integration unless explicitly prioritized.
- QR generation should create or append to a `QrPrintBatch` so generated labels can be reviewed and printed together.
- QR print batches should support labels for containers/locations, products, and assets.
- QR print batches should export as print-ready HTML and PDF-ready browser output first. Direct label-printer integrations can come later.
- QR labels should include the QR code, target type, target label, makerspace name/code, and optional short instructions.
- Per-unit QR generation should be based on `InventoryAsset`. For individual/serialized products, the backend should be able to create one or more assets and generate active QR codes for each asset in one workflow.
- Default generated asset labels should derive from the parent product name plus a stable sequence or asset tag, while still allowing manual override.
- Per-unit QR generation should optionally append all created unit QR labels to a selected or newly created QR print batch.
- Serialized handouts should be introduced gradually through product tracking mode. Quantity-counted products continue using quantities; individual-mode products require asset scans when configured.
- OpenAPI should document all new APIs so future SDK generation remains possible.
- The frontend should be redesigned around a professional operations-console pattern similar to InvenTree: dense tables, clear side navigation, item detail pages, status badges, filters, bulk actions, and audit/activity panels.
- The admin frontend should prioritize operational speed over marketing-style presentation. It should be table-first, searchable, keyboard-friendly where practical, and designed for repeated staff use.
- The public frontend should be a polished catalog/listing experience, not an internal admin view. It should expose only safe public fields and hide locations, QR internals, request history, evidence, and audit data.
- Light theme should be the default theme. Dark theme should be available through a persistent toggle and should apply consistently to public and admin surfaces.
- Theme choice should be stored client-side first, with optional user-profile persistence later for logged-in staff.
- The design system should define reusable table, filter, badge, toolbar, drawer/detail, modal, empty-state, loading, and export components so the admin UI does not become a set of one-off screens.

## Proposed Backend Modules

- Self-hosting and release module: image publishing, health checks, setup command, deployment documentation.
- Tenant bootstrap module: tenant-token/public-code discovery, module flags, frontend-safe config, and per-tenant CORS origin enforcement.
- Auth session module: staff access/refresh token lifetime policy, 7-day refresh sessions, refresh cookie hardening, and logout/rotation behavior.
- Notification payload module: consistent Telegram/email message builders that include contact fields, requested-for notes, item lists, and safe action links.
- Container/location module: nested QR-taggable containers, contents lookup, scan resolution, reassignments, history.
- Stock transfer module: superadmin-only transfer workflow, validation, audit logging, transfer history.
- Stocktake module: count sessions, count lines, variance review, approval, adjustment application.
- Analytics module: metrics queries over requests, request items, QR scans, direct loans, return events, accountability records, and inventory products.
- Export module: shared report export service for CSV and XLSX.
- QR print batch module: collect generated QR labels into batches and render/export print-ready label pages.
- Serialized handout bridge: extend handout workflows so individual-mode products can require asset QR scans while quantity-mode products remain unchanged.
- Per-unit QR module: create serialized `InventoryAsset` records from a product, assign stable asset tags/names, generate asset QR codes, and append labels to print batches.
- Frontend design system module: shared light/dark theme tokens, table patterns, filters, badges, forms, modals, scanner panels, and export controls.
- Admin console module: InvenTree-like inventory management screens for dashboard, products, assets, containers, transfers, stocktake, reports, QR batches, users, and audit logs.
- Public catalog module: light, searchable public inventory listing with item detail pages and a streamlined request flow.

## API Requirements

### Self-Hosting

- `GET /api/v1/health/`
- `GET /api/v1/health/readiness/`

### Tenant Bootstrap And Auth

- `GET /api/v1/bootstrap?tenant=<token-or-public-code>`
- `POST /api/v1/auth/refresh`

The bootstrap endpoint must be anonymous-safe and return only public/client-safe tenant configuration. Staff refresh must support a 7-day refresh lifetime.

### Containers And Location QR

- `GET /api/v1/admin/makerspace/:id/containers`
- `POST /api/v1/admin/makerspace/:id/containers`
- `GET /api/v1/admin/containers/:id`
- `PATCH /api/v1/admin/containers/:id`
- `POST /api/v1/admin/containers/:id/move`
- `GET /api/v1/admin/containers/:id/contents`
- `GET /api/v1/admin/containers/:id/history`
- `POST /api/v1/admin/qr/containers`
- `POST /api/v1/admin/products/:id/assets/generate`
- `POST /api/v1/admin/assets/:id/qr`

### Stock Transfers

- `GET /api/v1/admin/makerspace/:id/stock-transfers`
- `POST /api/v1/admin/makerspace/:id/stock-transfers`
- `GET /api/v1/admin/stock-transfers/:id`

Only superadmin can create transfers. Other roles may view scoped transfers only if granted by the existing inventory/audit permissions.

### Stocktake

- `GET /api/v1/admin/makerspace/:id/stocktakes`
- `POST /api/v1/admin/makerspace/:id/stocktakes`
- `GET /api/v1/admin/stocktakes/:id`
- `POST /api/v1/admin/stocktakes/:id/count-lines`
- `POST /api/v1/admin/stocktakes/:id/complete`
- `POST /api/v1/admin/stocktakes/:id/approve`
- `POST /api/v1/admin/stocktakes/:id/apply-adjustments`

### Analytics And Exports

- `GET /api/v1/admin/makerspace/:id/analytics/summary`
- `GET /api/v1/admin/makerspace/:id/analytics/taken-items`
- `GET /api/v1/admin/makerspace/:id/analytics/active-loans`
- `GET /api/v1/admin/makerspace/:id/analytics/returns`
- `GET /api/v1/admin/makerspace/:id/analytics/damaged-missing`
- `GET /api/v1/admin/makerspace/:id/reports/:report_key/export?format=csv|xlsx`

### QR Print Batches

- `GET /api/v1/admin/makerspace/:id/qr-print-batches`
- `POST /api/v1/admin/makerspace/:id/qr-print-batches`
- `GET /api/v1/admin/qr-print-batches/:id`
- `POST /api/v1/admin/qr-print-batches/:id/items`
- `GET /api/v1/admin/qr-print-batches/:id/print`
- `GET /api/v1/admin/qr-print-batches/:id/export`

### Guest Admin Returns

- `GET /api/v1/guest-admin/makerspace/:id/active-loans`
- `POST /api/v1/guest-admin/requests/:id/return`

Guest-admin return endpoints must call the same return workflow service used by the staff/admin API.

## Data Model Additions

### StockTransfer

- makerspace
- source_container nullable
- destination_container nullable
- source_makerspace nullable for cross-makerspace transfers
- destination_makerspace nullable for cross-makerspace transfers
- created_by
- reason
- status
- created_at
- applied_at

### StockTransferLine

- transfer
- product nullable
- asset nullable
- quantity
- from_status
- to_status
- notes

### StocktakeSession

- makerspace
- container nullable
- status: draft | counting | completed | approved | applied | cancelled
- started_by
- approved_by nullable
- started_at
- completed_at nullable
- approved_at nullable
- notes

### StocktakeLine

- stocktake
- product nullable
- asset nullable
- container nullable
- expected_quantity
- counted_quantity
- variance_quantity
- condition: available | damaged | lost | unknown
- notes

### InventoryAdjustment

- makerspace
- stocktake nullable
- transfer nullable
- product nullable
- asset nullable
- delta_available
- delta_damaged
- delta_lost
- reason
- created_by
- created_at

### TenantFrontend

- makerspace
- token_or_public_code
- frontend_type
- allowed_origins
- enabled_modules
- theme_config
- branding_config
- is_active
- created_at
- updated_at

### QrPrintBatch

- makerspace
- title
- status: draft | printed | archived
- created_by
- created_at
- printed_at nullable

### QrPrintBatchItem

- batch
- qr_code
- label_text
- target_type
- target_id
- sort_order

### InventoryAsset Generation Metadata

- product
- generated_name
- asset_tag
- serial_number nullable
- created_from_batch nullable
- created_by
- created_at

## Testing Decisions

Tests should verify external behavior and business invariants rather than internal implementation details.

- Docker/self-hosting tests should verify images build in CI, containers pass health checks, migrations run, and the frontend can reach the backend through the documented proxy path.
- Tenant bootstrap tests should verify tenant-token/public-code discovery, inactive tenant denial, per-tenant CORS behavior, and that private fields are never returned.
- Auth tests should verify staff refresh tokens/cookies remain valid for 7 days, rotate/refresh correctly, and fail after expiry or account restriction.
- Telegram notification tests should verify email, phone, requested-for, and item quantities are included while still respecting authorization on Telegram actions.
- Guest admin return tests should verify guest admins can return scoped loans and cannot return cross-makerspace loans, skip evidence, skip remarks, or bypass item resolution rules.
- Stock transfer tests should verify only superadmin can create transfers, transfers cannot make stock negative, transfer records are audited, and source/destination constraints are enforced.
- Stocktake tests should verify session lifecycle, variance calculation, approval requirements, adjustment application, and audit logging.
- Analytics tests should verify metrics from known request/return/direct-loan fixtures and enforce makerspace scoping.
- Export tests should verify CSV and XLSX content, filters, headers, and permission checks.
- Location/container QR tests should verify nested containers, QR creation, scan resolution, contents lookup, move history, and cycle prevention.
- QR print batch tests should verify generated QR codes are added to batches, print pages contain all expected labels, revoked QR codes are handled clearly, and cross-makerspace batch access is denied.
- Per-unit QR tests should verify asset generation count, generated labels, product-derived default names, active QR creation, print-batch append behavior, and cross-makerspace denial.
- Serialized handout tests should verify quantity-mode products still work and individual-mode products can require scanned assets when that setting is enabled.
- Frontend admin tests should verify table filtering, pagination/search behavior, bulk action affordances, permission-based visibility, and no leakage of cross-makerspace data.
- Public catalog tests should verify search/filter behavior, request flow behavior, and that internal fields such as locations, QR codes, audit logs, and evidence are never rendered.
- Theme tests should verify light theme default, dark theme toggle behavior, persistence across reloads, and readable contrast in both themes.

Existing test patterns to reuse:

- QR API tests for QR generation, scan, revoke, and immutability.
- Public self-checkout tests for stock movement and scan logging.
- Return flow tests for quantity updates, evidence, and accountability.
- RBAC tests for superadmin-only actions and makerspace scoping.
- Admin API tests for import/export-style request validation.

## Out Of Scope

- Native mobile applications.
- Direct USB/Bluetooth label-printer control.
- Direct Google Sheets OAuth publishing in the first implementation slice.
- Procurement, purchase orders, suppliers, and vendor management.
- Payment, deposits, or penalty automation.
- Replacing the current quantity-based workflow entirely with serialized handouts.
- Fine-grained custom permissions beyond the current role/action matrix.
- Multi-node high-availability deployment automation.
- Pixel-perfect cloning of InvenTree. The goal is equivalent professional quality and inventory-management ergonomics, not copying another product's UI exactly.

## Acceptance Criteria

- A non-technical user can deploy the app from published Docker images using documented Compose instructions.
- The first superadmin and first makerspace can be created without manually opening a Django shell.
- A tenant-token bootstrap endpoint supports production multi-frontend deployment without exposing private backend secrets.
- Per-tenant CORS rules are enforced from registered frontend/client origins.
- Staff refresh sessions last 7 days while preserving account restriction and logout behavior.
- Telegram request messages include requester email, requester phone, requested-for notes, and requested item quantities.
- Guest admins can process returns for assigned makerspaces through the same audited return workflow as staff.
- Superadmin can transfer stock between containers/locations and every transfer is audited.
- Non-superadmin users cannot create stock transfers.
- Inventory managers can run stocktake sessions and superadmin can approve/apply stock adjustments.
- Staff can view analytics for taken items, active loans, returns, damaged items, and missing items.
- Staff can export filtered reports as CSV and XLSX.
- Location/container QR codes can be generated, scanned, nested, moved, revoked, and viewed through backend APIs.
- Generated QR labels can be collected into a print batch and rendered as a print-ready page.
- Serialized asset/unit QR codes can be generated in bulk from a product and added directly to a print batch.
- Quantity-based handouts keep working while serialized handout support is introduced product by product.
- Admin users can manage inventory through a professional table-first frontend with filters, item detail pages, QR actions, reports, stocktake, transfers, and audit views.
- Public users can browse a polished searchable inventory catalog without seeing internal operational data.
- The app defaults to light theme and provides a persistent dark theme toggle.

## Further Notes

This PRD intentionally builds on the current architecture instead of replacing it. The existing `Box` model already supports nesting and QR payloads, so the pragmatic path is to evolve it into the location/container hierarchy before introducing a separate location model.

The most important architectural rule is that inventory movement must not become scattered across views. Transfers, stocktake adjustments, issue, return, and direct handout flows should all pass through explicit backend services that own quantity math, status changes, validation, and audit logging.
