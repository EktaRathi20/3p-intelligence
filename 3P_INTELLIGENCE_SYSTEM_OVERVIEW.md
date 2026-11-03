# 3P Intelligence — System Overview and Product Requirements

## 1. What We Are Building
**3P Intelligence — Predict. Prepare. Protect.** is a global, AI-assisted, multi-hazard disaster intelligence and response coordination platform.

It aims to connect the disaster-response lifecycle:
**Monitor → Detect → Assess → Notify → Human Verify → Prepare → Assign → Execute → Assess Impact → Rescue → Learn**

This document describes the intended product, not proof that every capability is already implemented.

## 2. Core Principles
- **Global by design:** Support countries, states/provinces, cities, and custom operational regions worldwide, subject to data coverage.
- **Evidence first:** Risk assessments and AI explanations should include data sources, timestamps, assumptions, and uncertainty.
- **Human oversight:** AI recommends and explains; authorized people make consequential verification and response decisions.
- **Role-based access:** Enforce permissions and jurisdiction scope on the backend.
- **Traceability:** Audit decisions, task changes, notifications, and workflow transitions.
- **Reliability:** Use retries, deduplication, failure states, and manual fallback paths.
- **Honest uncertainty:** Distinguish observed facts, model estimates, AI suggestions, and human-confirmed information.
- **Safe deployment:** Never send real emergency notifications from demo environments without explicit authorization.
- **Incremental development:** Inspect existing code and reuse working components before replacing them.

## 3. Intended End-to-End Workflow

### Stage 1 — Monitor and Detect
Background jobs ingest available data from reliable sources such as weather forecasts, official warnings, satellite/geospatial data, historical records, and exposure datasets.

The pipeline should normalize and timestamp data, check freshness and quality, evaluate hazard-specific rules and/or validated models, and create or update potential disaster events. Store evidence, geographic scope, risk/severity, probability only when scientifically supported, model/version details, and uncertainty. Avoid duplicate events and retain update history.

Never claim a disaster is certain because an AI generated a response. If evidence is insufficient, label the result uncertain or unavailable.

### Stage 2 — Alert Role 1
Notify the appropriate Role 1 officers through in-app alerts and configured channels. Include event type/status, location, expected time window, risk/probability if available, evidence-based explanation, source freshness, and a link to details.

Track delivery. Implement retries, deduplication, failure states, and an in-app fallback. Real messages must require explicit environment and recipient configuration.

### Stage 3 — Role 1: Verify and Decide
Show source observations, official warnings, maps/satellite imagery where available, model outputs, timestamps, assumptions, uncertainty, and affected population/assets where reliable.

Role 1 can approve, reject, or request more information, with a reason recorded in an audit trail. Approval triggers the next stage. Rejection stops or redirects active response according to policy while retaining event history.

A human decision is feedback, not automatically ground truth. Evaluate decisions against later outcomes; use them for training only after quality checks and validation.

### Stage 4 — Role 2: Prepare and Coordinate
After approval, notify Role 2 and generate a draft 48 hours checklist based on hazard, location, severity, lead time, resources, and trusted guidance.

Role 2 can edit the plan, add/remove tasks, set priorities/owners/deadlines/dependencies, assign tasks to Role 3, monitor completion, and escalate overdue or blocked work. AI recommendations remain suggestions until reviewed according to the configured workflow.

### Stage 5 — Role 3: Execute and Report
Role 3 receives assignments and can view instructions, location, priority, deadline, and dependencies; update status; submit progress notes/evidence; report blockers/resource needs; and notify Role 2. Preserve timestamped update history. Role 2 can monitor and follow up according to permissions.

### Stage 6 — Role 4: Impact, Costs, and Insurance
Use available geographic, demographic, infrastructure, asset, and financial data to estimate potentially affected population/assets, areas at risk, preparation/response costs, possible damage ranges, and insurance exposure.

Show sources, assumptions, estimate time, and uncertainty. Do not present estimates as confirmed claims or guaranteed financial outcomes. Actual insurance decisions require authorized review and suitable data.

### Stage 7 — Role 5: Rescue Support
The existing AI chat/rescue interface should provide location-aware guidance based on available verified data: official shelters/resources, alerts and safety instructions, route options where current road data exists, and suggested actions.

Cite sources/timestamps, distinguish facts from suggestions, and state when data is unavailable. Never invent shelters, routes, closures, or guarantees of safety. Encourage contact with local emergency services when appropriate. Rescue guidance does not replace official emergency command decisions.

### Stage 8 — Learn Safely
Store decisions, task outcomes, observed impacts, and confirmed outcomes with provenance. Use them to evaluate alert quality, false positives/negatives, forecast accuracy, thresholds, and preparedness templates.

Do not automatically retrain or deploy models from unverified officer actions. Validate data quality and model performance before production changes; track model versions.

## 4. Roles
- **Role 1 — Verification Officer:** Reviews events and approves, rejects, or requests information.
- **Role 2 — Preparedness/Coordination Officer:** Reviews plans, creates tasks, assigns work, and monitors readiness.
- **Role 3 — Field/Execution Officer:** Performs tasks and reports progress, evidence, and blockers.
- **Role 4 — Impact/Insurance Officer:** Reviews exposure, cost estimates, damage, and insurance analysis.
- **Role 5 — Rescue Officer:** Uses location-aware rescue support and coordinates rescue information.

Use existing role names where already established. Enforce role and jurisdiction permissions on the backend, not only in the UI.

## 5. Global Geographic Model
Support **Country → State/Province → City → Optional custom operational region**. Some countries have different administrative structures, and some regions may be coordinate/boundary based. Do not force invalid hierarchies.

Use stable identifiers and validate parent-child relationships server-side. The frontend should load dependent dropdowns from backend APIs and use search/pagination for large datasets. Document geographic data source, attribution, freshness, and coverage gaps.

## 6. AI and Data Technology Strategy
Technologies are not interchangeable; choose based on capability.

- **Meta models:** Evaluate suitable Meta Llama models for text reasoning, summaries, explanations, and vision where supported. Keep inference behind a backend abstraction, protect credentials, and make provider/model configuration explicit.
- **H2O AutoML:** Consider for structured-data classification/regression when valid historical data, reliable labels, and evaluation methods exist. It does not replace live weather, satellite imagery, maps, or a physical forecasting system by itself.
- **Google and other services:** Keep suitable mapping, satellite/geospatial, weather, and data services where they provide required capabilities. Replace only after verifying coverage, terms, cost, reliability, and compatibility.
- Handle timeouts, rate limits, provider outages, and fallback behavior. Never fabricate probabilities, evidence, or citations. Clearly label mocks and demos.

## 7. Workflow and Notification Reliability
Provide durable event/workflow states, in-app notifications, delivery status/retries/deduplication, idempotent jobs, controlled state transitions, audit logs, real-time updates where useful, and manual fallback. Reuse existing infrastructure unless a clear gap justifies a change.

## 8. Core Data Concepts
Inspect existing schemas first. Relevant concepts may include:
- Countries, states/provinces, cities, operational regions, and hazard types.
- Source observations, disaster events, evidence, risk assessments, model outputs/versions.
- Users, roles, jurisdiction assignments, notifications, delivery attempts.
- Verification decisions, audit records, preparedness plans, checklists, tasks, assignments, progress reports, evidence attachments.
- Exposure/impact/cost/insurance estimates.
- Rescue requests, recommendations, shelters/routes/resources.
- Model evaluation datasets and observed outcomes.

These are concepts, not a requirement to create duplicate tables or collections. Extend existing models compatibly.

## 9. Frontend Expectations
Provide role-specific dashboards for event/risk summaries, evidence and uncertainty; Role 1 decisions; Role 2 checklist editing and assignments; Role 3 execution/progress; Role 4 exposure and estimates; Role 5 rescue support; and notification/workflow history.

Use the existing design system. Handle loading, empty, error, offline, and permission-denied states. Never leave a visual-only feature disconnected from the backend.

## 10. Security, Privacy, and Safety
Enforce authentication, role permissions, and jurisdiction scope for every protected backend operation. Protect secrets and sensitive operational data, minimize personal data, validate inputs, audit consequential decisions, and separate demo from production data. Do not trigger real emergency communications/actions from development environments without explicit authorization. Follow provider terms, licensing, and data protection requirements.

## 11. Development Workflow
For every task:
1. Read `MUSE_CODE_AGENT_INSTRUCTIONS.md`.
2. Inspect existing code and trace data flow before editing.
3. Classify the relevant feature as working, partial, broken, missing, or mocked.
4. Implement one bounded task at a time.
5. Preserve working functionality and existing data.
6. Add/update tests.
7. Run relevant tests, linting, type checks, and builds.
8. Report actual results and remaining gaps; never claim tests passed unless run.

Do not rewrite the entire project in one task. Keep changes reviewable and the app runnable after each stage.

## 12. End-to-End Acceptance Criteria
In a controlled test/demo environment:
1. A scheduled job ingests data and detects a potential hazard.
2. The system stores evidence, location, risk, and uncertainty.
3. Role 1 receives an in-app alert and configured external notification.
4. Role 1 records approve/reject/request-information with a reason.
5. Approval notifies Role 2 and creates a draft preparedness plan.
6. Role 2 edits tasks and assigns Role 3.
7. Role 3 reports progress, evidence, or blockers.
8. Role 2 sees updates and can monitor/escalate.
9. Role 4 reviews estimates with assumptions and sources.
10. Role 5 accesses location-aware rescue support using available verified data.
11. Decisions, notifications, and task transitions are auditable.
12. Retries, duplicate events, unauthorized actions, and provider failures are handled safely.
13. The demo does not send unauthorized real emergency notifications.

## 13. Product Success Definition
3P Intelligence is a **global, evidence-driven, human-supervised disaster intelligence and response coordination platform** connecting early warning, verification, preparedness, field execution, impact estimation, and rescue support in one auditable workflow.

Prioritize trustworthy evidence, reliable coordination, and safe actions over claims of fully autonomous disaster prediction or rescue.
