# How to run the application (local, Windows)

The application has two parts. Run both, each in its own terminal:

| Part | What it does | Address |
|---|---|---|
| **Backend** (FastAPI, `backend/`) | Warehouse KPIs from Snowflake + live stream from Kafka, sent to the browser over SSE | http://localhost:8000 |
| **Dashboard** (React + Vite, `dashboard/`) | The web pages: 7 KPI dashboards + the Live Fleet Map | http://localhost:5173 |

```
Kafka (silver topics) ──┐
                        ├──> Backend :8000 ──> Dashboard :5173 ──> your browser
Snowflake (DBT_MARTS) ──┘
```

All commands are for **PowerShell** (the default VS Code terminal on Windows), starting from the project root `E:\KEMO\Samsung-BD\project`.

---

## 1. What you need

| Need | Version / value | Check with |
|---|---|---|
| Python | 3.14 | `python --version` |
| Node.js + npm | Node 24, npm 11 | `node -v`, `npm -v` |
| Snowflake login for the API | from the Snowflake owner | goes into `backend/.env` |
| Network access to Kafka | `16.16.254.130:9092` must be reachable from your PC | `Test-NetConnection 16.16.254.130 -Port 9092` → `TcpTestSucceeded : True` |

> If the Kafka test fails (`False`), the Kafka server's AWS security group does not allow your IP yet. Send your public IP (search "what is my ip") to the Kafka owner and ask them to allow it on TCP port 9092. The warehouse dashboards work without Kafka; only the Live Fleet Map needs it.

---

## 2. One-time setup

### 2.1 Backend
```powershell
# Python virtual environment, shared by the project (skip if .venv already exists)
python -m venv .venv

# backend packages: FastAPI, uvicorn, Snowflake connector, aiokafka
.venv\Scripts\python -m pip install -r backend\requirements.txt

# config file (git-ignored): copy, then fill the Snowflake values
Copy-Item backend\.env.example backend\.env
```
Open `backend/.env` and fill:

| Variable | Value |
|---|---|
| `SNOWFLAKE_API_ACCOUNT`, `SNOWFLAKE_API_USER`, `SNOWFLAKE_API_PASSWORD`, `SNOWFLAKE_API_DATABASE` | from the Snowflake owner |
| `SNOWFLAKE_API_SCHEMA` | `DBT_MARTS` |
| `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_TELEMETRY_TOPIC`, `KAFKA_REEFER_TOPIC`, `STREAM_HISTORY_MINUTES` | already filled in `.env.example`, keep them |

All variables are explained in [backend/README.md](backend/README.md#config-backendenv-git-ignored).

### 2.2 Dashboard
```powershell
cd dashboard
npm install
Copy-Item .env.example .env.local
cd ..
```
The dashboard always reads the backend (Snowflake KPIs + Kafka live map), so the backend must be running.
In `dashboard/.env.local`, keep `VITE_API_BASE_URL=http://localhost:8000/api` and `VITE_STREAM_URL=http://localhost:8000/api/stream`.

---

## 3. Start (every time)

Open **two terminals** in VS Code (**Terminal → New Terminal**, twice). Start the backend first.

### Terminal 1: backend
```powershell
cd E:\KEMO\Samsung-BD\project\backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000 --timeout-graceful-shutdown 3
```
Ready when you see `Application startup complete.` The backend then needs about 5-10 s to read the last 60 min from Kafka.

| Option | Why |
|---|---|
| `--reload` | Restarts the backend when you save a backend file (development only) |
| `--port 8000` | The port the dashboard calls |
| `--timeout-graceful-shutdown 3` | An open live-map tab keeps an SSE connection open forever; without this, stop and reload would wait for it forever. With it, open connections are closed after 3 s |

### Terminal 2: dashboard
```powershell
cd E:\KEMO\Samsung-BD\project\dashboard
npm run dev
```
Then open **http://localhost:5173**. The first page is the Live Fleet Map.

---

## 4. Check that it works

| Open | You should see |
|---|---|
| http://localhost:8000/health | `{"status":"ok", "login_user": ..., "schema":"DBT_MARTS"}`: the Snowflake login works |
| http://localhost:8000/docs | The list of endpoints (`/health`, `/api/tables`, `/api/kpis/{dashboard_id}`, `/api/stream`) |
| http://localhost:5173 (Live Fleet Map) | "Live KPIs" panel with numbers (about 5,000 trucks), trucks on the map, alerts in the feed |
| Any other dashboard page | KPI cards and charts from Snowflake |

**Normal on the live map:** it updates about **every 5 minutes**, and "Data age" shows about **10-15 min**. That is how often and how late the upstream job publishes to Kafka, not a problem of the app.

---

## 5. Stop

Press **Ctrl+C** in each terminal: the dashboard first, then the backend.

---

## 6. Problems and fixes

| What you see | Cause | Fix |
|---|---|---|
| Backend does not start: `ValidationError ... Field required` | A variable is missing in `backend/.env` | Add it (compare with `backend/.env.example`) |
| Backend log: `Stream source failed, reading again in 10 s` | Kafka not reachable | Check section 1 (network access to Kafka). The rest of the API keeps working |
| `/health` returns 503 `Snowflake error: ...` | Wrong Snowflake login or no access | Check the Snowflake values in `backend/.env` |
| Live map frozen after you saved a backend file | After `--reload` on Windows, the open tab's old connection is not closed, so it does not reconnect | Refresh the page (F5) |
| Live KPIs say "Waiting for the stream…" | Backend not running, or still reading Kafka | Start the backend, wait 10 s, refresh |
| `npm run dev` fails: port 5173 in use | Another dashboard is already running | Stop it, or close the other terminal |
| Backend fails: port 8000 in use (`[WinError 10048]`) | Another backend is already running | Find it: `Get-NetTCPConnection -LocalPort 8000 -State Listen` → stop that PID: `taskkill /PID <pid> /T /F` |
| Stream KPI cards (cold chain, idling, speeding, platform) show `-` / "No data" | They come from Kafka, and the backend has not read Kafka yet (start-up, or Kafka not reachable) | Wait about 10 s and check section 1 (network access to Kafka). See [backend/README.md](backend/README.md#live-stream-get-apistream) |

---

## More details
- Backend: endpoints, KPI formulas, live stream logic: [backend/README.md](backend/README.md), code structure: [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md)
- Dashboard: pages, data flow: [dashboard/README.md](dashboard/README.md)
- Event and field shapes between backend and dashboard: [dashboard/src/data/contract.js](dashboard/src/data/contract.js)
