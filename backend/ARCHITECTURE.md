# Backend architecture

How `backend/app/` is organised, why, and how to add a new endpoint.
Run steps, config and the endpoint list are in [README.md](README.md).

## 1. Why layers
The backend serves 8 dashboards (40 KPIs: 24 from the warehouse, 16 from Kafka) and a live stream ([../dashboard/src/data/contract.js](../dashboard/src/data/contract.js)).
If routes, logic and SQL all live in one file, that file becomes very large, and every change touches it.
So the code is split by **job**, and each job has one folder:

| Folder | Job | Knows about |
|---|---|---|
| `api/` | HTTP: URL, which service to call, response schema | services, schemas |
| `services/` | Logic: what to compute and how results are combined | `domain/` contracts only |
| `domain/` | Contracts: which data functions exist (Python `Protocol`) | nothing |
| `infrastructure/` | Real data access: Snowflake connection, SQL files, repositories | Snowflake, `core/config` |
| `schemas/` | Exact JSON shape of each response (Pydantic) | nothing |
| `core/` | Shared setup: settings from `.env`, error handler | `.env` |

**The one rule:** services never import Snowflake. They only see the contracts in `domain/repositories.py`.
`api/dependencies.py` is the single place that says "use the Snowflake version".

```
            api/routes  ──calls──>  services  ──uses contract──>  domain/repositories.py
                │                                                        ▲
         api/dependencies.py ──builds service with──>  infrastructure/repositories  (implements it)
                                                              │
                                              sql_loader + snowflake_client ──> Snowflake
```

## 2. One request, step by step: `GET /api/kpis/fuel?kpi_ids=19&kpi_ids=20`
1. `main.py` has included `api/router.py`, which mounts `api/routes/kpis.py` under `/api`.
2. FastAPI reads `dashboard_id = "fuel"` from the path and `kpi_ids = [19, 20]` from the query (`Query()` collects repeated `kpi_ids`).
   It sees `Depends(get_kpi_service)` and calls `api/dependencies.py`, which builds `KpiService(SnowflakeKpiRepository())`.
3. The route checks that `"fuel"` is a key of `DASHBOARD_SERIES` (else 404), then calls `service.dashboard("fuel", [19, 20])`.
4. The service builds the period: `current_end` = today (UTC) − 1 day, `current_start` = `current_end` − 29 days, `previous_start` = `current_start` − 30 days.
5. For each KPI id it looks up `KPI_QUERIES` (`19 → "total_fuel_spend"`) and calls `repository.fetch_rows("kpis/total_fuel_spend", params)`.
   A KPI id not in `KPI_QUERIES` (stream KPI) is not queried: `value` and `previous` stay `None`.
6. `SnowflakeKpiRepository.fetch_rows()` gets the SQL with `load_sql(...)` (reads the file once, then from memory), runs it with
   `snowflake_client.fetch_all(sql, params)`, and returns the rows with lower-case keys and `Decimal` turned into `float`.
7. The KPI query returns two rows (`period = 'value'` and `'previous'`); the service turns them into `{kpi_id, value, previous}`.
8. For each name in `DASHBOARD_SERIES["fuel"]` it runs `series/<name>.sql` the same way, or returns `None` for a name in `SERIES_NOT_IN_WAREHOUSE`.
9. FastAPI checks the dict against `response_model=DashboardResponse` and sends the JSON.
10. If Snowflake fails at any step, `core/errors.py` turns it into HTTP 503 with the Snowflake message.

## 3. Every file
```
backend/app/
  main.py
  core/        config.py, errors.py
  domain/      repositories.py, stream_source.py
  infrastructure/
               snowflake_client.py, sql_loader.py, kafka_stream_source.py
               queries/kpis/*.sql (one per KPI), queries/series/*.sql (one per chart)
               repositories/snowflake_system_repository.py, snowflake_kpi_repository.py
  services/    system_service.py, kpi_service.py,
               stream_service.py, fleet_state.py, stream_history.py, stream_kpis.py, platform_stats.py
  schemas/     system.py, dashboard.py, stream.py
  api/         dependencies.py, router.py
               routes/health.py, tables.py, kpis.py, stream.py
```
Each folder has an empty `__init__.py` so Python treats it as a package (needed for `from ..core.config import settings`).

### `main.py` (builds the app, nothing else)
| Line | What it does |
|---|---|
| `lifespan` | Code after `yield` runs on shutdown: closes the shared Snowflake connection |
| `app.add_middleware(CORSMiddleware, ...)` | Lets the dashboard (`http://localhost:5173`) call the API from the browser |
| `app.add_exception_handler(SnowflakeError, snowflake_error_handler)` | Any Snowflake error → 503 |
| `app.include_router(api_router)` | Adds all routes from `api/router.py` |

### `core/`
- **`config.py`**: `Settings` reads `backend/.env` once (`ENV_FILE` = `Path(__file__).parents[2] / ".env"`: `[0]` is `core/`, `[1]` is `app/`, `[2]` is `backend/`).
- **`errors.py`**: `snowflake_error_handler` turns any Snowflake error into HTTP 503 with the Snowflake message.

### `domain/repositories.py` (the contracts)
```python
class KpiRepository(Protocol):
    def fetch_rows(self, query: str, params: dict) -> list[dict]: ...
```
A `Protocol` lists the methods a class must have. It has no code (`...`).
Any class with a matching `fetch_rows` method counts as a `KpiRepository`, with no inheritance needed.
The service is typed against this contract, so a test can pass a fake class instead of Snowflake.

`fetch_rows(query, params)` takes the query name (`"kpis/..."` or `"series/..."`) instead of one method per KPI, so 24 KPIs and 17 charts do not need 41 methods.

### `infrastructure/`
- **`snowflake_client.py`**: the only file that opens a connection. `fetch_all()` catches an expired login (`ReauthenticationRequest`,
  or Snowflake codes 390111 / 390112 / 390114 = "log in again"), closes the dead connection, opens a new one and runs the query once more.
  Any other error is raised as before (→ 503).
- **`sql_loader.py`**: `load_sql("kpis/margin_proxy")` returns the text of `queries/kpis/margin_proxy.sql`.
  `@cache` stores the result, so each file is read from disk only once.
  The name always comes from code (`KPI_QUERIES`, `DASHBOARD_SERIES`), never from a URL, so a user cannot make it read another file.
- **`queries/kpis/*.sql`**: one file per KPI. Each returns one row per period: `PERIOD` (`'value'` = current, `'previous'`) and `KPI_VALUE`.
  **`queries/series/*.sql`**: one file per chart, returning the chart's rows. Both use the parameters `%(previous_start)s`, `%(current_start)s`,
  `%(current_end)s`: replace them with dates to paste a file into a Snowflake worksheet. Never write a `%` sign in them (the connector reads `%` as a parameter).
- **`repositories/snowflake_kpi_repository.py`**: `fetch_rows(query, params)` = `fetch_all(load_sql(query), params)`, with keys lower-cased
  (the dashboard reads `kpi_1`, `week_start`, ...) and `Decimal` turned into `float` (JSON has no Decimal).
- **`repositories/snowflake_system_repository.py`**: `current_session()` and `list_tables()`. Their short SQL stays here as strings (decision: only KPI SQL in `.sql` files).

### `services/`
- **`kpi_service.py`**: `PERIOD_DAYS = 30`, `DATA_LAG_DAYS = 1`, `KPI_QUERIES` (kpi_id → SQL file), `DASHBOARD_SERIES` (dashboard → chart files),
  `SERIES_NOT_IN_WAREHOUSE` (charts returned as null), `Period` (the 3 dates), `period_ending()`, and `KpiService.dashboard()`.
  `__init__(self, repository: KpiRepository)` receives the repository from outside (dependency injection). The service never creates it.
- **`system_service.py`**: `health()` is the old `/health` logic (`status: "ok"` + lower-cased keys). `tables()` passes the table list through.

### `schemas/`
The exact JSON fields. They appear in `/docs`, and FastAPI checks every response against them.
- **`system.py`**: `HealthResponse`, `TableRow`. `schema` is already a name inside Pydantic's `BaseModel`, so the field is
  `schema_: str | None = Field(alias="schema")`. FastAPI writes the alias, so the JSON key is still `schema`.
- **`dashboard.py`**: `KpiValue` (`kpi_id, value, previous`) and `DashboardResponse` (`dashboard, period, as_of, kpis, series`), as in `contract.js`.
  `series` is `dict[str, list[dict] | None]` because every chart has its own columns.

### `api/`
- **`dependencies.py`**: one function per service, e.g. `get_kpi_service()` returns `KpiService(SnowflakeKpiRepository())`.
  This is the only file that imports both services and Snowflake repositories.
- **`routes/*.py`**: each file has `router = APIRouter(...)` and one function per URL. Example:
  ```python
  @router.get("/tables", response_model=list[TableRow])
  def tables(service: Annotated[SystemService, Depends(get_system_service)]) -> list[dict]:
      return service.tables()
  ```
  `Depends(...)` makes FastAPI call `get_system_service()` and pass the result in as `service`.
  `tags=[...]` only groups the routes in `/docs`.
- **`router.py`**: joins the route files. `/health` stays at the root; `tables`, `kpis` and `stream` get `prefix="/api"`.

### Live stream files (`GET /api/stream`)
Same layers as the KPIs, but the data is pushed (Kafka → memory → SSE) instead of asked for (HTTP → Snowflake).
- **`domain/stream_source.py`**: `StreamSource` contract, one method `messages(since)` that yields `StreamMessage`s forever: `kind` (`"telemetry"` | `"reefer"`),
  `row` (dict, `None` when not JSON), `partition` + `offset` (to know a message read again) and `timestamp` (Kafka time, UTC).
- **`infrastructure/kafka_stream_source.py`**: `KafkaStreamSource`, an aiokafka consumer on both topics with **no consumer group** (each backend instance must
  read every truck, and nothing is committed: the history is read again on every start). `_seek_to()` moves each partition to the first message produced
  at or after `since` (`offsets_for_times`). A message that is not JSON is passed on with `row = None` (rejected and counted in `FleetState`).
- **`services/fleet_state.py`**: `FleetState`, plain logic (no Kafka, no asyncio). `apply()` keeps a row only if it is inside the history window and newer
  than the stored row of that truck, and updates the alerts. `take_changes()` drops old rows and returns the events not sent yet (empty = send nothing).
  `snapshot()` is what a new viewer gets. `kpis()` builds `LiveKpis`. `stream_kpis()` builds `StreamKpis` (only again when rows were added).
  `apply(message)` first asks `PlatformStats` if the message is new, counts it (rejected → raises, logged by `StreamService`). `stream_kpis` are sent
  after new messages and at least every `STREAM_KPIS_EVERY` (1 min). Constants: `FLAG_ALERTS`, `FEED_SIZE` (40), `STREAM_KPIS_EVERY`.
- **`services/stream_history.py`**: `StreamHistory`, every row of the last `kept(STREAM_HISTORY_MINUTES)` (2 windows + 30 min) with only the `COLUMNS` the
  stream KPIs read; `add()` returns `"added"`, `"duplicate"` (`vehicle_id` + `event_ts` already kept) or `"old"`, `rows()` drops expired rows first.
- **`services/platform_stats.py`**: `PlatformStats`, platform KPIs 54, 57, 58, 60 from the messages: `is_new()` (partition + offset + Kafka time),
  `count()` per minute of Kafka time (received, duplicates, rejected), `kpis(now)`.
- **`services/stream_kpis.py`**: plain functions, rows → `StreamKpis` values. `calculate()` groups rows per truck/trailer (`_tracks`, with the minutes
  each row counts for), finds flag runs (`_runs`) and excursions (`_excursions`), then `_window_kpis()` for the window and the previous one and `_series()`.
  Constants: `INTERVAL_CAP` (15 min), `EXCESSIVE_IDLING_AFTER` (30 min, also used by the alert), `MARGIN`, `STREAM_KPI_IDS`, `AMBIENT_BANDS`.
- **`services/stream_service.py`**: `StreamService` runs two background tasks: `_read()` (source → `FleetState`, retries every 10 s on any error) and
  `_send_changes()` (every second, puts the changes in each viewer's queue). `events()` is one viewer: snapshot, then its queue, and it removes the queue
  when the browser leaves.
- **`schemas/stream.py`**: `AlertRow`, `LiveKpis` and `StreamKpis` (the events the backend builds), `EventName`. Telemetry and reefer rows are sent as Kafka has them, so no model.
- **`api/routes/stream.py`**: `response_class=EventSourceResponse` (FastAPI's built-in SSE); each `(event, data)` becomes a `ServerSentEvent`.
  `?events=` (a list of `EventName`, unknown name → 422) keeps only those events.
- **`api/dependencies.py`**: `stream_service` is **one object for the whole app** (all viewers share one Kafka reader and one fleet state);
  `main.py` starts it in `lifespan` and stops it on shutdown.

## 4. How to add things
- **A new warehouse KPI:** add `queries/kpis/<name>.sql` (returning `PERIOD`, `KPI_VALUE`) and one line `<kpi_id>: "<name>"` in `KPI_QUERIES`.
- **A new chart:** add `queries/series/<name>.sql` and its name to the dashboard's tuple in `DASHBOARD_SERIES`.
- **A new endpoint:** one small addition per layer: SQL (`queries/`) → contract (`domain/repositories.py`) → Snowflake repository →
  service → schema (`schemas/`) → `api/dependencies.py` → route file (`api/routes/`) → `api/router.py`.

- **A new live KPI:** one field in `LiveKpis` (`schemas/stream.py`), its value in `FleetState.kpis()` and a tile in `liveKpiTiles()` (`dashboard/src/pages/LiveMapPage.jsx`).
- **A new platform KPI from the stream:** a counter in `PlatformStats.count()` and its value in `PlatformStats.kpis()` (`PLATFORM_KPI_IDS`).
- **A new stream KPI:** its rule in `_window_kpis()` and its id in `STREAM_KPI_IDS` (`services/stream_kpis.py`); a column it needs goes in `COLUMNS` (`services/stream_history.py`).
- **A new flag alert:** one line in `FLAG_ALERTS` + its type in `AnomalyType` (`schemas/stream.py`) and `ANOMALY_TYPES` (`dashboard/src/kpis/definitions.js`).

## 5. URLs
`/health`, `/api/tables`, `/api/kpis/{dashboard_id}`, `/api/stream`. The old `/api/kpis/validation` (KPI 9 + 28 join checks) was removed on 2026-10-29;
the join checks live in `tools/validate_marts.py`.
