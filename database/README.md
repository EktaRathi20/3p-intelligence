# Local JSON database

This directory is the backend's database. Each file stores one collection as
a JSON object mapping **document id → document fields** (fields exclude the
id; the backend injects `id` on read, matching the previous API shapes).

| File | Collection | Contents |
|---|---|---|
| `roles.json` | roles | Role definitions (`role_1` … `role_5`) |
| `users.json` | users | Demo users (`user_1` … `user_5`) |
| `regions.json` | regions | Operational regions (created via the API) |
| `hazards.json` | hazards | Hazard types (`flood`, `cyclone`, …) |
| `countries.json` | countries | Countries keyed by ISO alpha-2 code |
| `states.json` | states | States/provinces keyed by dataset provider id |
| `cities.json` | cities | Cities keyed by dataset provider id (large, generated) |
| `settings.json` | settings | `regionManagement` and `geoSync` records |
| `tasks.json` | tasks | Operational tasks assigned by Role 2 to Role 3 (created via the API) |
| `notifications.json` | notifications | Operational notifications from Role 2 to field teams (created via the API) |

## Notes

- `roles.json`, `users.json`, and `hazards.json` ship with seed data. To
  reset them, run (from the repo root):
  `python Backend/scripts/seed_roles.py` and
  `python Backend/scripts/seed_hazards.py`.
- `countries.json`, `states.json`, and `cities.json` start empty and are
  populated by `python Backend/scripts/sync_geo_data.py`
  (see `Backend/docs/GEO_DATA_SETUP.md`).
- `cities.json` can exceed 100 MB after a full sync and is gitignored.
  The other files are small and committed.
- All backend access goes through `Backend/services/json_store.py`, which
  performs atomic writes (temp file + rename) and guards concurrent access
  with a process-wide lock.
- Override the directory with the `DATABASE_DIR` environment variable
  (used by tests to point at a temporary copy).
