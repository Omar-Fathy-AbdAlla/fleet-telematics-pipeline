# 🧾 Work Log: S3 → Airbyte → Snowflake (setup)

**Author:** Karim Mohamed
**Scope:** my setup of the batch path: a Snowflake account (`FLEET_DB`), AWS access for Airbyte, the S3 bucket survey, and the Airbyte source, destination and connection.
Steps 1–2 (EC2, Kafka, S3 bucket) are in [Notion_Documentation.md](Notion_Documentation.md).

> **Status:** this setup ends at step 5c. The team then loaded the data into a teammate's warehouse (`SUPPLYCHAIN_DW`, see [README.md](README.md#3-snowflake-team-warehouse)), which the dashboard uses.

**How I document each step (team rules from [Notion_Documentation.md](Notion_Documentation.md)):**
1. Write the step right after I finish it.
2. Each step = **what I did** (1–3 lines) + **screenshot** + **code** (if any).
3. Never show passwords, keys or tokens. Use `<YOUR_KEY>` and blur screenshots.

Screenshot naming: `tool-stepnumber-name.png` (for example `snowflake-3a-account.png`).

Status: ✅ done · ⏳ in progress · ⬜ not started

---

## Step 3: Snowflake setup ✅

### 3a. Create the Snowflake account ✅
**What I did:** Signed up at signup.snowflake.com with **Enterprise** edition on **AWS**, in the same region as the S3 bucket (avoids data transfer charges).

| Setting | Value |
|---|---|
| Edition | Enterprise |
| Cloud | AWS |
| Region | EU (Stockholm) `AWS_EU_NORTH_1`, same as the S3 bucket |
| Date | 2026-10-26 |

**Screenshot:** `snowflake-3a-account.png`

### 3b. Create the key pairs for the service users ✅
**What I did:** Created one RSA key pair per service user (`AIRBYTE_USER`, `DBT_USER`). The private key (`.p8`) stays on my PC. The public key (`.pub`) goes into Snowflake. Keys are stored outside the repo in `~/.snowflake_keys/`.

**Code (Git Bash):**
```bash
mkdir -p ~/.snowflake_keys && cd ~/.snowflake_keys

# Airbyte user
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out airbyte_rsa_key.p8 -nocrypt
openssl rsa -in airbyte_rsa_key.p8 -pubout -out airbyte_rsa_key.pub

# dbt user
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out dbt_rsa_key.p8 -nocrypt
openssl rsa -in dbt_rsa_key.p8 -pubout -out dbt_rsa_key.pub
```

**Result:** 4 files: `airbyte_rsa_key.p8`, `airbyte_rsa_key.pub`, `dbt_rsa_key.p8`, `dbt_rsa_key.pub`.

> ⚠️ Never commit or screenshot the `.p8` files. `.gitignore` blocks `*.p8` and `*.pub`.

### 3c. Run the setup script ✅
**What I did:** Ran `snowflake/01_setup.sql` (removed from the repo in commit `1b84625`, see git history) as `ACCOUNTADMIN` in a Snowflake worksheet. Placeholders were replaced **in the worksheet only**, not in the repo file.

| Placeholder | Replaced with |
|---|---|
| `<PASTE_AIRBYTE_PUBLIC_KEY_HERE>` | Body of `airbyte_rsa_key.pub` (no BEGIN/END lines, no line breaks) |
| `<PASTE_DBT_PUBLIC_KEY_HERE>` | Body of `dbt_rsa_key.pub` |

> The script grants the 3 roles to my own login automatically with `CURRENT_USER()`, so there is no username to replace.

**Code (print a public key on one line, ready to paste):**
```bash
grep -v "PUBLIC KEY" ~/.snowflake_keys/airbyte_rsa_key.pub | tr -d '\n'
grep -v "PUBLIC KEY" ~/.snowflake_keys/dbt_rsa_key.pub | tr -d '\n'
```

**What the script creates:**

| Object | Names |
|---|---|
| Warehouses (XSMALL, auto-suspend 60 s) | `AIRBYTE_WH`, `DBT_WH`, `BI_WH` |
| Database | `FLEET_DB` |
| Schemas | `RAW`, `STAGING`, `INTERMEDIATE`, `MARTS`, `SEEDS` |
| Roles | `AIRBYTE_ROLE`, `TRANSFORMER`, `REPORTER` |
| Service users (key pair) | `AIRBYTE_USER`, `DBT_USER` |
| Cost guard | `FLEET_MONTHLY_RM` (50 credits a month: notify at 75%, suspend at 90% and 100%) |

**Screenshot:** `snowflake-3c-setup-run.png`

### 3d. Verify ✅
**Code:**
```sql
SHOW SCHEMAS IN DATABASE FLEET_DB;
SHOW USERS LIKE '%_USER';
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS account_identifier;
```

**Result:**
- Schemas found: `RAW`, `STAGING`, `INTERMEDIATE`, `MARTS`, `SEEDS`
- `RSA_PUBLIC_KEY_FP` set (starts with `SHA256:`) for `AIRBYTE_USER` and `DBT_USER`
- Account identifier (needed by Airbyte and dbt): `RSGNWLJ-PK32132` (Snowflake host: `RSGNWLJ-PK32132.snowflakecomputing.com`)

**Screenshot:** `snowflake-3d-verify.png`

---

## Step 4: AWS access for Airbyte + bucket survey ✅

### 4a. AWS identity for Airbyte ✅ (my IAM user `Karim`)
**Permission check (2026-10-26):** my IAM user can read the bucket in the S3 console ✅, but cannot create IAM users ❌ and cannot open CloudShell ❌.
**Decision (2026-10-26): Airbyte uses my IAM user `Karim`.** My user cannot create its own access key (no IAM permissions: `iam:ListAccessKeys`, `iam:GetAccountSummary` and others are denied), so the account owner creates an access key **for user `Karim`** and sends it privately. Trade-off: Airbyte gets all of `Karim`'s permissions, and the pipeline depends on my user. Later option: switch to a dedicated `airbyte-s3-reader`.

**Prepared for the later option:** a read-only policy for a dedicated user `airbyte-s3-reader` (`aws/airbyte_s3_readonly_policy.json`, removed from the repo in commit `1b84625`, see git history):
- `s3:ListBucket`, `s3:GetBucketLocation` on the bucket
- `s3:GetObject` on all objects in the bucket

**Screenshot:** `aws-4a-iam-user.png`

### 4b. Create an access key for Airbyte ✅
**Result (2026-10-27):** the owner created access key `…LKJI` for user `Karim` and sent it privately. Saved in `~/.aws/credentials` (not in the repo), and `.env` was rebuilt with `bash tools/build_env.sh`. Check: `who am I` = `user/Karim`, bucket region `eu-north-1`, list root OK (`bronze/`, `fleet/`), list `fleet/bronze/tms/trips/` OK.

**Screenshot:** `aws-4b-access-key.png` (blur the key)

### 4c. Run the bucket survey ✅
**What I did:** Ran [tools/s3_survey.py](tools/s3_survey.py) to list every folder in the bucket (file count, size, first and last file date) and print the first lines of one sample file per folder. This decides the Airbyte stream list.

**Code:**
```bash
# one-time: virtual env + dependencies (.venv is git-ignored)
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt

# credentials: C:\Users\dev\.aws\credentials (outside the repo, read by boto3)
.venv/Scripts/python tools/s3_survey.py fleet-telematics-lakehouse-team11 > tools/s3_survey.txt
```

**Result (2026-10-27):** 583 objects in 18 folder groups (sizes in MB, all small because the generator started on 2026-10-26).

| Folder | Files | Format | Airbyte stream? |
|---|---|---|---|
| `fleet/bronze/registry/trucks`, `registry/trailers`, `hr/drivers` | 3 each | CSV.gz (daily snapshot) | Yes |
| `fleet/bronze/tms/customers`, `facilities`, `routes` | 3 each | CSV.gz (daily snapshot) | Yes |
| `fleet/bronze/tms/loads`, `trips`, `delivery_events` | 103 each | CSV.gz (every 15 min) | Yes |
| `fleet/bronze/fuel_card/fuel_purchases` | 89 | CSV.gz | Yes |
| `fleet/bronze/cmms/maintenance_records` | 44 | CSV.gz | Yes |
| `fleet/bronze/safety/safety_incidents` | 1 | CSV.gz | Yes |
| `fleet/bronze/prices/diesel_prices` | 3 | CSV.gz | Yes |
| `bronze/telemetry.raw/dt=/hour=` | 4 | JSON lines (uncompressed), from Kafka Connect | To decide |
| `fleet/bronze/weather/open_meteo` | 6 | JSON.gz (one JSON array per file) | To decide |
| `fleet/ground_truth/gen_anomaly_labels` | 102 | JSONL.gz (evaluation only) | To decide |
| `fleet/silver/telemetry` | 7 | Parquet (written by Spark, 1 empty folder marker) | No (not Bronze) |

Not found in the bucket: `fleet/bronze/stream_direct/`, `fleet/bronze/prices/eia/`, `bronze/reference/`, and no Kafka Connect folder for reefer.

**Script fixes:** `tools/s3_survey.py` now skips empty (0-byte) objects when picking a sample (S3 returned `InvalidRange`) and writes UTF-8 output (Windows `cp1252` could not encode some characters).
(`tools/s3_survey.txt` is git-ignored.)

---

## Step 5: Airbyte source, destination, connection ✅

### 5a. Source: Amazon S3 ✅ (S3 connector v4.16.1)
**What I did:** In Airbyte Cloud, created the source `fleet-s3-bronze` (Amazon S3, delivery method **Replicate Records**) with a first test stream. After the owner sent a working key (`…LKJI`, user `Karim`), the connection test passed and the source was saved (2026-10-27).

| Field | Value |
|---|---|
| Bucket | `fleet-telematics-lakehouse-team11` |
| Authentication | IAM user access key (user `Karim`) |
| Stream name | `trips` |
| Globs | `fleet/bronze/tms/trips/**/*.csv.gz` (default `**` removed) |
| Format | CSV, header from CSV, inference type **None** (all columns as text) |
| Validation policy | Emit record |

**Screenshot:** `airbyte-5a-source.png`

### 5b. Destination: Snowflake ✅
**What I did:** Created the destination `fleet-snowflake-raw` (Snowflake connector v5.2.0) with key-pair authentication.

| Field | Value |
|---|---|
| Host | `RSGNWLJ-PK32132.snowflakecomputing.com` |
| Role / Warehouse | `AIRBYTE_ROLE` / `AIRBYTE_WH` |
| Database / Default schema | `FLEET_DB` / `RAW` |
| Username | `AIRBYTE_USER` |
| Authorization | Key Pair: full `airbyte_rsa_key.p8`, including BEGIN/END lines, no passphrase |

**Code (copy the private key to the clipboard without showing it):**
```bash
cat ~/.snowflake_keys/airbyte_rsa_key.p8 | clip
```

**Test from my PC (same login as Airbyte):** login OK as `AIRBYTE_USER`, `AIRBYTE_ROLE`, `AIRBYTE_WH`, `FLEET_DB.RAW`, region `AWS_EU_NORTH_1`; create and drop a test table in `RAW` OK.

**Screenshot:** `airbyte-5b-destination.png`

### 5c. Connection + streams ✅
**What I did:** Added 12 more CSV streams to the source (13 in total, same settings as `trips`), then created the connection `fleet-s3-bronze → fleet-snowflake-raw` (2026-10-28).

| Setting | Value | Why |
|---|---|---|
| Streams | `trucks`, `trailers`, `drivers`, `customers`, `facilities`, `routes`, `loads`, `trips`, `delivery_events`, `fuel_purchases`, `maintenance_records`, `safety_incidents`, `diesel_prices` | Globs: `<S3 folder>**/*.csv.gz` (see the 4c survey table) |
| Sync mode | **Incremental \| Append** (all streams) | Reads only new files and keeps every row. No primary key needed. De-duplication happens in dbt (keeps snapshot history and dirty rows) |
| Destination namespace | Destination default (`RAW`) | Tables land in `FLEET_DB.RAW` |
| Stream prefix | none | Table names = stream names |
| Schema changes | Propagate field changes only | New columns are added automatically. All columns are text, so type changes cannot happen |
| Schedule | Every 1 hour | Airbyte's own schedule |

Not added: `telemetry_raw` (JSONL), weather (JSON array) and anomaly labels (evaluation only).

**Screenshot:** `airbyte-5c-connection.png`

---

## 🐞 Error log
| Date | Step | Error | Fix |
|---|---|---|---|
| 2026-10-26 | 3c | `New public key rejected by current policy. Reason: 'Invalid Public key'` on `CREATE USER AIRBYTE_USER` | The placeholder `<PASTE_AIRBYTE_PUBLIC_KEY_HERE>` was not replaced. Create the keys (3b), paste the real public key body, and re-run from section 7 |
| 2026-10-26 | 4a | CloudShell: `Unable to create the environment ... insufficient permissions` | My IAM user has no CloudShell or IAM permissions. Do the checks in the console instead. The AWS account owner creates the access key (see 4a) |
| 2026-10-26 | 5a | Airbyte S3 source: `Error listing files`. Local check: `SignatureDoesNotMatch` on every call | The key from the generator `.env` (`…CTEG`) has a secret that does not match its key ID (my copy was checked and is identical to what I received). It was also shared in chat. Owner deletes it and creates a fresh key for user `Karim` (see 4a, 4b). Also removed the default `**` glob from the stream |
| 2026-10-26 | 5b | Airbyte Snowflake destination: `HikariPool-1 - Connection is not available, request timed out after 30000ms` | The Snowflake login worked from my PC, so the form was wrong: the private key must be pasted in full (with the BEGIN/END lines, no quotes from `.env`) and the host without `https://`. Copied it with `cat ~/.snowflake_keys/airbyte_rsa_key.p8 \| clip` |
