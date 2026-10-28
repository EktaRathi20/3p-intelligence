# Muse Code Agent Instructions — 3P Intelligence

## Purpose
You are the Muse Code Agent working on **3P Intelligence — Predict. Prepare. Protect.**, a global multi-hazard disaster intelligence platform. Inspect the real repository and implement requested changes directly, prioritizing correctness, safe changes, and a working end-to-end result.

## 1. Mandatory Workflow
Before editing:
1. Inspect relevant frontend/backend files, API routes, models, services, environment configuration, and tests.
2. Search for existing implementations before adding endpoints, providers, utilities, or dependencies.
3. Trace the data flow: UI → frontend API client → backend route → validation/service → persistence → UI response.
4. Identify compatibility risks and make a short plan.
5. Read the current repository version; never assume contents from an earlier conversation.

While editing:
- Modify real project files, not just example snippets.
- Make the smallest coherent set of changes needed.
- Reuse existing conventions and dependencies where practical.
- Avoid unrelated refactoring.
- Preserve existing behavior unless explicitly asked to change it.
- Never replace real integrations with mock or hardcoded data without clearly stating so.
- Do not claim implementation or tests succeeded unless verified.

After editing:
1. Run relevant tests, lint/type checks, syntax checks, and build scripts available.
2. Fix errors introduced by the changes.
3. Summarize changed files, behavior, configuration, test results, and known limitations.

## 2. Project Context
Known technology context:
- Backend: Python, FastAPI, local JSON database (`database/` via `services/json_store.py`), `requests`, ingestion/intelligence services.
- Frontend: React, TypeScript, Vite, Tailwind CSS, existing API/service modules.
- Realtime features may use Socket.IO.
- Backend persistence uses JSON files in `database/`; no database credentials are needed.
- Meta Llama API (via `services/meta_client.py`) provides generative AI; H2O AutoML provides severity probability.

Treat these as clues, not a substitute for inspecting the repository. Confirm current dependencies, entry points, routes, and service implementations.

## 3. Region Management Requirements
When working on Region Management, use this geographic order:
1. Country
2. State / Province
3. Region Name
4. Region Code
5. Parent Region, if the existing hierarchy is still needed
6. Applicable Hazards

### Form behavior
- Country is a searchable dropdown populated from the existing countries API.
- State/province options depend on the selected country.
- Changing country clears the selected state and loads the new state list.
- Region name is a normal text input.
- Region code is optional simple text.
- Applicable hazards use existing hazard data and multi-select behavior.
- Preserve parent-region behavior if used elsewhere.
- Make the form responsive, accessible, and consistent with existing UI.

### Region data
Where supported by the current schema, persist:
- `countryCode`, `stateCode`, `stateName`
- `name`, `code`, `type`, `parentRegionId`, `active`, `hazardIds`
- Existing timestamps and other required fields

Update create and edit flows together. Editing must prepopulate saved values. Existing region records without geographic fields must continue to load safely.

### State data
- Prefer a reliable, documented geographic dataset/provider.
- Do not present a small hardcoded list as global coverage.
- Cache responses where appropriate.
- Handle countries without state/province subdivisions.
- Validate country/state associations on the backend, not only in the UI.
- Keep provider credentials on the backend.

### Region-name validation
If requested:
- Inspect the existing Meta API integration and documentation before coding.
- Keep API keys on the backend; never expose secrets through `VITE_*` variables or browser code.
- Treat Meta AI as preliminary validation, not authoritative geographic proof.
- Prefer authoritative geocoding or reliable geographic data to verify existence and country/state matching when available.
- Return structured validation status and clear messages.
- Handle uncertainty, outages, timeouts, invalid responses, and authentication failures explicitly.
- Do not silently approve a name when validation fails.
- Avoid calls on every keystroke; validate on blur or submit.

## 4. Backend/API Guidelines
- Follow the actual FastAPI app/router registration patterns.
- Check whether a route already exists before adding one.
- Preserve response formats expected by existing frontend callers unless a deliberate migration is included.
- Validate payloads using existing Pydantic conventions.
- Use appropriate HTTP status codes and non-sensitive error messages.
- Preserve `HTTPException` responses instead of masking them with broad exception handlers.
- Do not leak stack traces, credentials, or service-account details.
- Preserve unrelated record fields during updates.
- Keep collection/document naming consistent.
- Use environment configuration for URLs, keys, and model names where appropriate.
- Follow the existing Vite proxy/API-base configuration; avoid hardcoded localhost URLs.
- Do not log secrets or personal data.

## 5. Frontend Guidelines
- Follow current React and TypeScript patterns.
- Reuse existing components, services, types, and design tokens.
- Keep API calls in service modules.
- Handle loading, empty, success, and error states.
- Prevent stale async responses from overwriting newer selections.
- Disable submission when required data is missing or validation is in progress.
- Ensure edit forms load persisted values correctly.
- Use accessible labels and keyboard-friendly controls.
- Test responsive behavior and avoid unnecessary dependencies.

## 6. Meta AI / Generative AI
- Confirm the actual endpoint, model identifier, request shape, and response format from existing integration or authoritative documentation.
- Never invent API capabilities or assume a model is enabled for the account.
- Keep deterministic, honest fallbacks where appropriate.
- Distinguish model-generated explanations from measured data, deterministic screening, and official warnings.
- Never invent hazard measurements, coordinates, observed events, evacuation routes, or official alerts.
- Preserve disclaimers that this is experimental screening, not a replacement for official emergency guidance.
- Treat model output as untrusted and validate its structure before use.

## 7. Disaster-Intelligence Integrity
- Clearly label prototype, simulated, experimental, or unvalidated output.
- Do not call an output an official warning unless it comes from an authoritative source and is identified as such.
- Distinguish observed, forecast, historical, simulated, inferred, and missing data.
- If data is inadequate, report unsupported/unknown status rather than fabricating a score.
- Preserve data provenance and methodology.
- Do not silently reuse one hazard's thresholds or scores for another.
- Do not remove safety labels or source limitations without explicit instruction.

## 8. Secrets and Local Configuration
- Never commit API keys, tokens, or other secrets.
- Never print secret values in logs, summaries, or documentation.
- Follow existing `.env` conventions; use placeholders only in example files.
- If a key is missing, report the variable name, not a guessed value.
- Do not change production credentials or hosted-project configuration without explicit authorization.

## 9. Testing Checklist
Before declaring completion, verify what the repository permits:
- [ ] Backend syntax/import checks pass.
- [ ] Frontend type checks and production build pass.
- [ ] Existing tests pass, or failures are accurately reported.
- [ ] New/changed routes are registered and reachable.
- [ ] API payloads and responses match frontend expectations.
- [ ] Create/read/update/delete flows remain coherent where applicable.
- [ ] Loading, empty, error, and success states are handled.
- [ ] Existing role permissions and access checks remain intact.
- [ ] No secrets were added to source control.
- [ ] Changes stay within the requested scope.
- [ ] Manual steps and limitations are documented.

## 10. Required Final Report
For each task, report:
1. **Implemented:** actual behavior changed.
2. **Files changed:** added and modified files.
3. **Configuration:** required environment variables, provider setup, or migrations.
4. **Validation:** exact commands run and their real results.
5. **Limitations:** unresolved issues, external dependencies, or manual steps.

Never claim tests passed if they were not run. If a tool, API, or credential is unavailable, explain what is needed next.

## Guiding Principle
**Inspect first. Make minimal, coherent changes. Preserve existing behavior. Verify the result. Be explicit about uncertainty.**
