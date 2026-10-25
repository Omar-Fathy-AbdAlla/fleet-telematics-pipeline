#!/usr/bin/env python3
"""
fleet_generator.py - continuous US trucking fleet simulator -> Kafka + S3 (RAW data only)
=========================================================================================
Simulates a fleet (default 5,000 Class-8 trucks) for days/weeks without stopping and lands
raw data the way real source systems would:

  STREAMING   telemetry + reefer (trailer refrigeration) sensors
                -> Kafka topics (JSON, key = vehicle_id)
                -> a configurable share of the fleet (DIRECT_S3_PCT) is "bulk uploaded":
                   written straight to S3 as gzip JSON-lines micro-batches
  BATCH       TMS / fuel-card / maintenance / safety / registry exports
                -> S3 as CSV.gz files (dirty on purpose: nulls, case/space noise, duplicates)
  REFERENCE   weather (Open-Meteo), diesel price (EIA), master data -> S3
  TRUTH       injected anomalies -> S3 ground_truth/ (never use inside detection rules)

Physics, not copied columns: trucks obey hours-of-service (11 h driving, 30 min break after
8 h, 10 h rest), refuel at 18% tank (fuel purchases therefore reconcile with consumption),
reefer boxes follow a heat-leak / compressor model driven by REAL ambient temperature, and
anomalies (excessive idling, route deviation, refrigeration failure) are injected and logged.
Numeric parameters were calibrated on public datasets (mpg, revenue per mile, detention,
maintenance cost, incident rate); see README.md for the list and the assumptions.

Run:  python fleet_generator.py run            (configuration via .env / environment)
      python fleet_generator.py run --s3-mode local --kafka-mode null --until-sim-hours 24 --backfill-days 1
      python fleet_generator.py init-topics
      python fleet_generator.py fetch-routes    (optional: real road geometry from OSRM, cached)

Reliability for multi-day runs: checkpoint + resume (+ catch-up of the gap), deterministic
event ids (replays are idempotent), Kafka spool and S3 outbox on local disk when the network
or broker is down, graceful SIGTERM/SIGINT shutdown, heartbeat file for Docker health checks.
Delivery is at-least-once: consumers must de-duplicate on event_id.
"""
from __future__ import annotations

import argparse
import base64
import bisect
import collections
import csv
import functools
import gzip
import hashlib
import heapq
import io
import json
import logging
import logging.handlers
import math
import os
import pickle
import signal
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

try:  # optional, ~5x faster JSON
    import orjson
except Exception:  # pragma: no cover
    orjson = None

VERSION = "1.0.0"
log = logging.getLogger("fleet")


# ----------------------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------------------
def jdumps(o) -> bytes:
    if orjson is not None:
        return orjson.dumps(o)
    return json.dumps(o, separators=(",", ":")).encode()


@functools.lru_cache(maxsize=1 << 16)
def iso_sec(s: int) -> str:
    return datetime.fromtimestamp(s, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso(t: float) -> str:
    return iso_sec(int(t))


def day_str(t: float) -> str:
    return iso_sec(int(t))[:10]


def hour_str(t: float) -> str:
    return iso_sec(int(t))[11:13]


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.split(" #")[0].strip().strip('"').strip("'"))


def E(name, default, cast=str):
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    if cast is bool:
        return v.strip().lower() in ("1", "true", "yes", "y", "on")
    return cast(v)


@dataclass
class Cfg:
    fleet_size: int = 5000
    tick_seconds: int = 60
    seed: int = 42
    speedup: float = 1.0
    backfill_days: float = 0.0
    until_sim_hours: float = 0.0
    max_gap_hours: float = 6.0
    s3_mode: str = "s3"                 # s3 | local
    s3_bucket: str = ""
    s3_prefix: str = "fleet"
    aws_region: str = "us-east-1"
    kafka_mode: str = "kafka"           # kafka | file | null
    kafka_bootstrap: str = "localhost:9092"
    topic_telemetry: str = "fleet.telemetry.v1"
    topic_reefer: str = "fleet.reefer.v1"
    kafka_partitions: int = 12
    kafka_retention_hours: int = 48
    kafka_horizon_hours: float = 24.0   # older than this (backfill) goes straight to S3
    direct_s3_pct: float = 10.0         # % of trucks that bulk-upload straight to S3
    s3_flush_seconds: int = 600
    batch_flush_seconds: int = 900
    out_dir: str = "./out"
    state_dir: str = "./state"
    log_dir: str = "./logs"
    ckpt_seconds: int = 300
    parked_mult: int = 5                # parked (engine-off) trucks report every Nth tick
    dirty_rate: float = 0.02
    delivery_slack: float = 0.22        # planned transit time = HOS plan * (1 + slack)
    wait_mean_hours: float = 60.0       # idle time between loads
    reefer_load_share: float = 0.503
    lanes: int = 58
    customers: int = 2500
    use_openmeteo: bool = True
    eia_api_key: str = ""
    p_late: float = 0.01
    p_dup: float = 0.004
    p_malformed: float = 0.0002
    p_gps_null: float = 0.004
    p_speed_null: float = 0.003

    @staticmethod
    def from_env() -> "Cfg":
        return Cfg(
            fleet_size=E("FLEET_SIZE", 5000, int), tick_seconds=E("TICK_SECONDS", 60, int), seed=E("SEED", 42, int),
            speedup=E("SIM_SPEEDUP", 1.0, float), backfill_days=E("BACKFILL_DAYS", 0.0, float),
            until_sim_hours=E("UNTIL_SIM_HOURS", 0.0, float), max_gap_hours=E("MAX_GAP_HOURS", 6.0, float),
            s3_mode=E("S3_MODE", "s3"), s3_bucket=E("S3_BUCKET", ""), s3_prefix=E("S3_PREFIX", "fleet"),
            aws_region=E("AWS_REGION", "us-east-1"), kafka_mode=E("KAFKA_MODE", "kafka"),
            kafka_bootstrap=E("KAFKA_BOOTSTRAP", "localhost:9092"), topic_telemetry=E("KAFKA_TOPIC_TELEMETRY", "fleet.telemetry.v1"),
            topic_reefer=E("KAFKA_TOPIC_REEFER", "fleet.reefer.v1"), kafka_partitions=E("KAFKA_PARTITIONS", 12, int),
            kafka_retention_hours=E("KAFKA_RETENTION_HOURS", 48, int), kafka_horizon_hours=E("KAFKA_HORIZON_HOURS", 24.0, float),
            direct_s3_pct=E("DIRECT_S3_PCT", 10.0, float), s3_flush_seconds=E("S3_FLUSH_SECONDS", 600, int),
            batch_flush_seconds=E("BATCH_FLUSH_SECONDS", 900, int), out_dir=E("OUT_DIR", "./out"), state_dir=E("STATE_DIR", "./state"),
            log_dir=E("LOG_DIR", "./logs"), ckpt_seconds=E("CKPT_SECONDS", 300, int), parked_mult=E("PARKED_MULT", 5, int),
            dirty_rate=E("DIRTY_RATE", 0.02, float), delivery_slack=E("DELIVERY_SLACK", 0.22, float),
            wait_mean_hours=E("WAIT_MEAN_HOURS", 60.0, float), reefer_load_share=E("REEFER_LOAD_SHARE", 0.503, float),
            lanes=E("LANES", 58, int), customers=E("CUSTOMERS", 2500, int), use_openmeteo=E("USE_OPENMETEO", True, bool),
            eia_api_key=E("EIA_API_KEY", ""), p_late=E("P_LATE", 0.01, float), p_dup=E("P_DUP", 0.004, float),
            p_malformed=E("P_MALFORMED", 0.0002, float), p_gps_null=E("P_GPS_NULL", 0.004, float), p_speed_null=E("P_SPEED_NULL", 0.003, float),
        )


# ----------------------------------------------------------------------------------------
# reference data (US network)
# ----------------------------------------------------------------------------------------
CITIES = [  # name, state, lat, lon
    ("Seattle", "WA", 47.6062, -122.3321), ("Portland", "OR", 45.5152, -122.6784), ("Los Angeles", "CA", 34.0522, -118.2437),
    ("Phoenix", "AZ", 33.4484, -112.0740), ("Salt Lake City", "UT", 40.7608, -111.8910), ("Denver", "CO", 39.7392, -104.9903),
    ("Dallas", "TX", 32.7767, -96.7970), ("Houston", "TX", 29.7604, -95.3698), ("Oklahoma City", "OK", 35.4676, -97.5164),
    ("Kansas City", "MO", 39.0997, -94.5786), ("Minneapolis", "MN", 44.9778, -93.2650), ("Chicago", "IL", 41.8781, -87.6298),
    ("Indianapolis", "IN", 39.7684, -86.1581), ("Columbus", "OH", 39.9612, -82.9988), ("Detroit", "MI", 42.3314, -83.0458),
    ("Nashville", "TN", 36.1627, -86.7816), ("Memphis", "TN", 35.1495, -90.0490), ("Atlanta", "GA", 33.7490, -84.3880),
    ("Charlotte", "NC", 35.2271, -80.8431), ("Miami", "FL", 25.7617, -80.1918), ("Jacksonville", "FL", 30.3322, -81.6557),
    ("Philadelphia", "PA", 39.9526, -75.1652), ("New York", "NY", 40.7128, -74.0060), ("Boston", "MA", 42.3601, -71.0589),
    ("Pittsburgh", "PA", 40.4406, -79.9959),
]
NC_ = len(CITIES)
CLAT = np.array([c[2] for c in CITIES])
CLON = np.array([c[3] for c in CITIES])
STATE_DIESEL_OFFSET = {"CA": 1.10, "WA": 0.65, "OR": 0.45, "UT": 0.15, "AZ": 0.35, "CO": 0.0, "TX": -0.25, "OK": -0.25, "MO": -0.2,
                       "MN": -0.05, "IL": 0.20, "IN": 0.05, "OH": -0.05, "MI": 0.05, "TN": -0.20, "GA": -0.15, "NC": -0.10, "FL": 0.0,
                       "PA": 0.45, "NY": 0.40, "MA": 0.30}
FIRST = ["James", "Mary", "Robert", "Patricia", "Michael", "Linda", "William", "Barbara", "David", "Susan", "Thomas", "Jessica", "Daniel",
         "Sarah", "Kevin", "Karen", "Brian", "Nancy", "George", "Lisa"]
LAST = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez",
        "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]
MAKES = ["Peterbilt", "Freightliner", "Mack", "Volvo", "International", "Kenworth"]
CUST_A = ["First", "Metro", "Continental", "Pacific", "National", "Summit", "Premier", "Atlas", "Liberty", "Heritage"]
CUST_B = ["Logistics", "Wholesale", "Supply Chain", "Distribution", "Freight", "Retail", "Foods", "Industries", "Goods", "Trading"]
STATES_LIC = ["TX", "NC", "MI", "TN", "FL", "OH", "GA", "IL", "CA", "PA", "NY", "IN", "MO", "WA", "AZ"]

MI_PER_DEG = 69.0
ROAD_FACTOR = 1.17            # road miles = great-circle miles * factor (when no real geometry is cached)

# commodity classes for refrigerated loads (deg F) - simulation assumptions, not regulatory values
COMMODITIES = [("PHARMA", 0.10, 41.0, 36.0, 46.0), ("CHILLED", 0.45, 36.0, 33.0, 41.0), ("FROZEN", 0.45, -5.0, -10.0, 0.0)]
# reefer physics (deg F, minutes)
K_LEAK, DOOR_FACTOR, CAP0, CAP_DERATE, DEADBAND = 0.0015, 2.5, 0.40, 0.004, 1.5
P_REEFER_FAIL, P_IDLE_ANOM, P_DEVIATION = 0.12, 0.15, 0.10
INCIDENT_PER_MILE = 1.39e-6
MAINT_PER_YEAR = 8.1
MAINT_TYPES = ["Inspection", "Repair", "Preventive", "Engine", "Tire", "Transmission", "Brake"]
INCIDENT_TYPES = [("DOT Violation", 0.229), ("Equipment Damage", 0.206), ("Accident", 0.206), ("Customer Complaint", 0.200), ("Moving Violation", 0.159)]

SCHEMAS = {
    "trucks": ["truck_id", "unit_number", "make", "model_year", "vin", "acquisition_date", "acquisition_mileage", "fuel_type",
               "tank_capacity_gallons", "status", "home_terminal", "snapshot_date"],
    "trailers": ["trailer_id", "trailer_number", "trailer_type", "length_feet", "model_year", "vin", "acquisition_date", "status",
                 "current_location", "snapshot_date"],
    "drivers": ["driver_id", "first_name", "last_name", "hire_date", "termination_date", "license_number", "license_state",
                "date_of_birth", "home_terminal", "employment_status", "cdl_class", "years_experience", "snapshot_date"],
    "customers": ["customer_id", "customer_name", "customer_type", "credit_terms_days", "primary_freight_type", "account_status",
                  "contract_start_date", "annual_revenue_potential"],
    "facilities": ["facility_id", "facility_name", "facility_type", "city", "state", "latitude", "longitude", "dock_doors", "operating_hours"],
    "routes": ["route_id", "origin_city", "origin_state", "destination_city", "destination_state", "typical_distance_miles",
               "base_rate_per_mile", "fuel_surcharge_rate", "typical_transit_days"],
    "loads": ["load_id", "customer_id", "route_id", "load_date", "load_type", "weight_lbs", "pieces", "revenue", "fuel_surcharge",
              "accessorial_charges", "load_status", "booking_type"],
    "trips": ["trip_id", "load_id", "driver_id", "truck_id", "trailer_id", "dispatch_date", "dispatch_ts", "arrival_ts",
              "actual_distance_miles", "actual_duration_hours", "fuel_gallons_used", "average_mpg", "idle_time_hours", "trip_status"],
    "delivery_events": ["event_id", "load_id", "trip_id", "event_type", "facility_id", "scheduled_datetime", "actual_datetime",
                        "detention_minutes", "on_time_flag", "location_city", "location_state"],
    "fuel_purchases": ["fuel_purchase_id", "trip_id", "truck_id", "driver_id", "purchase_date", "location_city", "location_state",
                       "gallons", "price_per_gallon", "total_cost", "fuel_card_number"],
    "maintenance_records": ["maintenance_id", "truck_id", "maintenance_date", "maintenance_type", "odometer_reading", "labor_hours",
                            "labor_cost", "parts_cost", "total_cost", "facility_location", "downtime_hours", "service_description"],
    "safety_incidents": ["incident_id", "trip_id", "truck_id", "driver_id", "incident_date", "incident_type", "location_city",
                         "location_state", "at_fault_flag", "injury_flag", "vehicle_damage_cost", "cargo_damage_cost", "claim_amount",
                         "preventable_flag", "description"],
    "diesel_prices": ["effective_date", "fuel_type", "price_per_gallon", "source"],
}
ENTITY_SOURCE = {"trucks": "registry", "trailers": "registry", "drivers": "hr", "customers": "tms", "facilities": "tms", "routes": "tms",
                 "loads": "tms", "trips": "tms", "delivery_events": "tms", "fuel_purchases": "fuel_card", "maintenance_records": "cmms",
                 "safety_incidents": "safety", "diesel_prices": "prices"}


def gc_interp(lat1, lon1, lat2, lon2, n=240):
    """great-circle points between two coordinates; returns lat[], lon[], length in miles"""
    p1, p2, l1, l2 = np.radians([lat1, lat2, lon1, lon2])
    d = 2 * np.arcsin(np.sqrt(np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin((l2 - l1) / 2) ** 2))
    f = np.linspace(0, 1, n)
    if d < 1e-9:
        return np.full(n, lat1), np.full(n, lon1), 0.0
    A, B = np.sin((1 - f) * d) / np.sin(d), np.sin(f * d) / np.sin(d)
    x = A * np.cos(p1) * np.cos(l1) + B * np.cos(p2) * np.cos(l2)
    y = A * np.cos(p1) * np.sin(l1) + B * np.cos(p2) * np.sin(l2)
    z = A * np.sin(p1) + B * np.sin(p2)
    return np.degrees(np.arctan2(z, np.hypot(x, y))), np.degrees(np.arctan2(y, x)), float(d * 3958.7613)


def haversine_mi(lat1, lon1, lat2, lon2):
    p1, p2, l1, l2 = np.radians(lat1), np.radians(lat2), np.radians(lon1), np.radians(lon2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin((l2 - l1) / 2) ** 2
    return 2 * 3958.7613 * np.arcsin(np.sqrt(a))


def nearest_city(lat, lon):
    dl = (lat[:, None] - CLAT[None, :]) * MI_PER_DEG
    dn = (lon[:, None] - CLON[None, :]) * MI_PER_DEG * np.cos(np.radians(lat))[:, None]
    return np.argmin(dl * dl + dn * dn, axis=1)


class Ref:
    """deterministic network: facilities, lanes/routes (+ 1-mile geometry grids), customers"""

    def __init__(self, cfg: Cfg, rng: np.random.Generator, cache_dir: Path):
        self.cfg = cfg
        # facilities: 1 per city + 25 extra
        self.fac = []
        for k in range(NC_):
            self.fac.append(dict(city=k, type=str(rng.choice(["Terminal", "Distribution Center"]))))
        for _ in range(25):
            self.fac.append(dict(city=int(rng.integers(NC_)), type=str(rng.choice(["Cross-Dock", "Warehouse", "Distribution Center", "Terminal"]))))
        for n, f in enumerate(self.fac, 1):
            c = CITIES[f["city"]]
            f.update(id=f"FAC{n:05d}", name=f"{c[0]} {f['type']}" + (f" {n}" if n > NC_ else ""),
                     lat=round(c[2] + rng.uniform(-0.04, 0.04), 4), lon=round(c[3] + rng.uniform(-0.04, 0.04), 4),
                     docks=int(rng.integers(16, 151)), hours=str(rng.choice(["24/7", "8AM-5PM", "7AM-7PM", "6AM-10PM"])))
        self.fac_by_city = {}
        for f in self.fac:
            self.fac_by_city.setdefault(f["city"], f)
        # lanes: nearest-neighbour tour (guarantees every city has >= 2 lanes) + random extra lanes
        gcd = np.zeros((NC_, NC_))
        for a in range(NC_):
            gcd[a] = haversine_mi(CITIES[a][2], CITIES[a][3], CLAT, CLON) * ROAD_FACTOR
        tour, left = [0], set(range(1, NC_))
        while left:
            nxt = min(left, key=lambda j: gcd[tour[-1], j])
            tour.append(nxt)
            left.remove(nxt)
        lanes = {frozenset((tour[i], tour[(i + 1) % NC_])) for i in range(NC_)}
        guard = 0
        while len(lanes) < cfg.lanes and guard < 100000:
            guard += 1
            a, b = int(rng.integers(NC_)), int(rng.integers(NC_))
            if a != b and 92 <= gcd[a, b] <= 3141:
                lanes.add(frozenset((a, b)))
        lanes = sorted(tuple(sorted(x)) for x in lanes)
        self.cache_dir = cache_dir
        self.routes = []
        for (a, b) in lanes:
            rate, fsr = float(np.round(rng.uniform(1.52, 2.79), 2)), float(np.round(rng.uniform(0.15, 0.34), 2))
            for (o, d) in ((a, b), (b, a)):
                self.routes.append(dict(o=o, d=d, rate=rate, fsr=fsr, lane=(a, b)))
        self.R = len(self.routes)
        geo = []
        for r in self.routes:
            lat, lon, L = self._geometry(r)
            r["len"] = float(L)
            r["transit_days"] = int(math.ceil(L / 550.0))
            geo.append((lat, lon, L))
        self.rlen = np.array([r["len"] for r in self.routes])
        self.rorig = np.array([r["o"] for r in self.routes])
        self.rdest = np.array([r["d"] for r in self.routes])
        self.Lmax = int(math.ceil(self.rlen.max())) + 3
        self.glat = np.zeros((self.R, self.Lmax))
        self.glon = np.zeros((self.R, self.Lmax))
        for k, (lat, lon, L) in enumerate(geo):
            m = np.arange(0, int(math.ceil(L)) + 1, dtype=float)
            f = np.clip(m / L, 0, 1) if L > 0 else m
            la, lo = np.interp(f, np.linspace(0, 1, len(lat)), lat), np.interp(f, np.linspace(0, 1, len(lon)), lon)
            self.glat[k, :len(m)], self.glon[k, :len(m)] = la, lo
            self.glat[k, len(m):], self.glon[k, len(m):] = la[-1], lo[-1]
        self.routes_from = [np.array([k for k, r in enumerate(self.routes) if r["o"] == c], dtype=np.int64) for c in range(NC_)]
        for r_ in range(self.R):
            r = self.routes[r_]
            r["id"] = f"RTE{r_ + 1:05d}"
        self.sig = hashlib.md5(np.round(self.rlen, 1).tobytes()).hexdigest()[:12]
        # customers
        self.cust = []
        for n in range(1, cfg.customers + 1):
            self.cust.append(dict(id=f"CUST{n:05d}", name=f"{rng.choice(CUST_A)} {rng.choice(CUST_B)}",
                                  type=str(rng.choice(["Contract", "Spot", "Dedicated"], p=[0.375, 0.315, 0.31])),
                                  credit=int(rng.choice([15, 30, 45, 60])),
                                  freight=str(rng.choice(["Automotive", "Food/Beverage", "Retail", "Electronics", "Consumer Goods", "Industrial"])),
                                  status="Active" if rng.random() < 0.84 else "Inactive",
                                  start=f"{int(rng.integers(2018, 2026))}-{int(rng.integers(1, 13)):02d}-{int(rng.integers(1, 28)):02d}",
                                  potential=int(rng.integers(100_000, 5_000_000))))

    def _geometry(self, r):
        a, b = r["lane"]
        f = self.cache_dir / f"{a}_{b}.json"
        if f.exists():  # real road geometry fetched with `fetch-routes` (cached, a->b)
            try:
                d = json.loads(f.read_text())
                co = np.array(d["coords"])  # [[lon, lat], ...]
                if r["o"] != a:
                    co = co[::-1]
                seg = haversine_mi(co[:-1, 1], co[:-1, 0], co[1:, 1], co[1:, 0])
                cum = np.concatenate([[0], np.cumsum(seg)])
                n = max(2, int(cum[-1] / 1.0))
                s = np.linspace(0, cum[-1], n)
                return np.interp(s, cum, co[:, 1]), np.interp(s, cum, co[:, 0]), float(cum[-1])
            except Exception as e:
                log.warning("bad route cache %s: %s (using great-circle)", f, e)
        lat, lon, L = gc_interp(CITIES[r["o"]][2], CITIES[r["o"]][3], CITIES[r["d"]][2], CITIES[r["d"]][3])
        return lat, lon, L * ROAD_FACTOR


# ----------------------------------------------------------------------------------------
# weather + diesel price providers (real when reachable, labelled synthetic otherwise)
# ----------------------------------------------------------------------------------------
def _http_get(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "fleet-generator/" + VERSION})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clim_temp_f(lat, lon, t):
    """crude US climatology (deg F) used only when Open-Meteo is unreachable"""
    doy = (t / 86400.0) % 365.25
    lh = ((t / 3600.0) + lon / 15.0) % 24
    mean = 82 - 1.3 * (lat - 25)
    amp = 14 + 0.6 * (lat - 25)
    return mean + amp * np.cos(2 * np.pi * (doy - 200) / 365.25) + 8 * np.cos(2 * np.pi * (lh - 15) / 24)


class Weather:
    def __init__(self, cfg: Cfg, s3, rng):
        self.cfg, self.s3, self.rng = cfg, s3, rng
        self.t0, self.temps, self.source, self.fetched_at = None, None, "none", 0.0

    def covers(self, t):
        return self.temps is not None and self.t0 <= t <= self.t0 + 3600 * (len(self.temps) - 25)

    def refresh(self, t, backfill_days=0.0):
        if self.covers(t) and (t - self.fetched_at) < 6 * 3600:
            return
        past = int(min(92, max(2, math.ceil(backfill_days) + 1)))
        if self.cfg.use_openmeteo:
            try:
                self._fetch(t, past)
                return
            except Exception as e:
                log.warning("Open-Meteo fetch failed (%s) -> SYNTHETIC climatology is used for ambient temperature", e)
        self._synthetic(t, past)

    def _fetch(self, t, past):
        q = dict(latitude=",".join(f"{x:.4f}" for x in CLAT), longitude=",".join(f"{x:.4f}" for x in CLON),
                 hourly="temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code", temperature_unit="fahrenheit",
                 wind_speed_unit="mph", precipitation_unit="inch", timezone="UTC", past_days=past, forecast_days=3)
        raw = _http_get("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q))
        data = json.loads(raw)
        data = data if isinstance(data, list) else [data]
        times = [datetime.strptime(s, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc).timestamp() for s in data[0]["hourly"]["time"]]
        temps = np.array([[np.nan if v is None else v for v in d["hourly"]["temperature_2m"]] for d in data]).T
        if temps.shape[1] != NC_ or np.isnan(temps).all():
            raise ValueError("unexpected response shape")
        for c in range(NC_):  # fill gaps
            col = temps[:, c]
            bad = np.isnan(col)
            if bad.any():
                col[bad] = np.interp(np.nonzero(bad)[0], np.nonzero(~bad)[0], col[~bad])
        self.t0, self.temps, self.source, self.fetched_at = times[0], temps, "open-meteo", t
        self.s3.put(f"bronze/weather/open_meteo/dt={day_str(t)}/fetch-{iso(t).replace(':', '')}.json.gz", gzip.compress(raw))
        log.info("weather: Open-Meteo window %s .. %s (%d hours)", iso(times[0]), iso(times[-1]), len(times))

    def _synthetic(self, t, past):
        t0 = (int(t) // 3600) * 3600 - past * 86400
        hrs = np.arange(0, (past + 3) * 24 + 1)
        tt = t0 + hrs * 3600.0
        self.temps = np.stack([clim_temp_f(CLAT[c], CLON[c], tt) + self.rng.normal(0, 1.0, tt.size) for c in range(NC_)], axis=1)
        self.t0, self.source, self.fetched_at = float(t0), "synthetic", t

    def ambient(self, city_idx, t):
        h = (t - self.t0) / 3600.0
        h = min(max(h, 0.0), len(self.temps) - 2.001)
        i, f = int(h), h - int(h)
        return self.temps[i, city_idx] * (1 - f) + self.temps[i + 1, city_idx] * f


class DieselPrice:
    def __init__(self, cfg: Cfg, s3):
        self.cfg, self.s3, self.weekly, self.source, self.last = cfg, s3, [], "model", 0.0

    def refresh(self, t):
        if t - self.last < 86400:
            return
        self.last = t
        if self.cfg.eia_api_key:
            try:
                url = ("https://api.eia.gov/v2/petroleum/pri/gnd/data/?api_key=" + self.cfg.eia_api_key +
                       "&frequency=weekly&data[0]=value&facets[product][]=EPD2D&facets[duoarea][]=NUS"
                       "&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=120")
                raw = _http_get(url)
                rows = json.loads(raw)["response"]["data"]
                w = sorted((datetime.strptime(r["period"], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp(), float(r["value"])) for r in rows)
                if w:
                    self.weekly, self.source = w, "eia"
                    self.s3.put(f"bronze/prices/eia/dt={day_str(t)}/eia-diesel-{iso(t).replace(':', '')}.json.gz", gzip.compress(raw))
                    log.info("diesel price: EIA weekly series loaded (%d weeks, latest %.3f)", len(w), w[-1][1])
                    return
            except Exception as e:
                log.warning("EIA fetch failed (%s) -> MODEL diesel price used", e)

    def national(self, t):
        if self.weekly:
            i = bisect.bisect_right([x[0] for x in self.weekly], t) - 1
            return self.weekly[max(0, i)][1]
        doy = (t / 86400.0) % 365.25
        return 3.80 + 0.30 * math.sin(2 * math.pi * (doy - 30) / 365.25)

    def at(self, t, state, rng):
        return round(self.national(t) + STATE_DIESEL_OFFSET.get(state, 0.0) + float(rng.normal(0, 0.05)), 3)


# ----------------------------------------------------------------------------------------
# sinks: S3 (or local mirror) with outbox, Kafka (or file/null) with spool
# ----------------------------------------------------------------------------------------
class S3Writer:
    def __init__(self, cfg: Cfg, outbox: Path):
        self.cfg, self.mode, self.outbox = cfg, cfg.s3_mode, outbox
        self.files = self.bytes = self.failed = 0
        outbox.mkdir(parents=True, exist_ok=True)
        if self.mode == "s3":
            if not cfg.s3_bucket:
                raise SystemExit("S3_BUCKET is required when S3_MODE=s3 (use --s3-mode local to test without AWS)")
            import boto3
            from botocore.config import Config
            self.client = boto3.client("s3", region_name=cfg.aws_region,
                                       config=Config(retries={"max_attempts": 8, "mode": "adaptive"}, max_pool_connections=16))
        else:
            self.root = Path(cfg.out_dir) / "s3" / (cfg.s3_bucket or "local-bucket")

    def _key(self, rel):
        return f"{self.cfg.s3_prefix.strip('/')}/{rel}".strip("/")

    def _put(self, key, data):
        if self.mode == "s3":
            self.client.put_object(Bucket=self.cfg.s3_bucket, Key=key, Body=data)
        else:
            p = self.root / key
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, p)

    def put(self, rel, data: bytes):
        key = self._key(rel)
        try:
            self._put(key, data)
            self.files += 1
            self.bytes += len(data)
        except Exception as e:
            self.failed += 1
            log.warning("S3 put failed for %s (%s) -> stored in outbox for retry", key, e)
            p = self.outbox / key
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

    def drain(self, max_files=25):
        n = 0
        for p in sorted(self.outbox.rglob("*")):
            if not p.is_file():
                continue
            key = p.relative_to(self.outbox).as_posix()
            try:
                self._put(key, p.read_bytes())
                p.unlink()
                self.files += 1
                n += 1
            except Exception:
                break
            if n >= max_files:
                break
        return n

    def backlog(self):
        return sum(1 for p in self.outbox.rglob("*") if p.is_file())


class KafkaOut:
    """producer with at-least-once semantics + on-disk spool when the broker is unreachable"""

    def __init__(self, cfg: Cfg, spool: Path, run_id: str):
        self.cfg, self.mode, self.spool_dir, self.run_id = cfg, cfg.kafka_mode, spool, run_id
        spool.mkdir(parents=True, exist_ok=True)
        self.sent = self.failed = self.spooled = 0
        self.last_fail = 0.0
        self.fail_since_drain = 0
        self.lib = None
        self._since_poll = 0
        self._spool_fh, self._spool_n, self._spool_idx = None, 0, 0
        self._lock = threading.Lock()
        if self.mode == "file":
            self.fdir = Path(cfg.out_dir) / "kafka"
            self.fdir.mkdir(parents=True, exist_ok=True)
            self.fh = {}
        elif self.mode == "kafka":
            self._ensure_topics()
            self._make_producer()

    # -- setup
    def _topics(self):
        return [self.cfg.topic_telemetry, self.cfg.topic_reefer]

    def _ensure_topics(self):
        try:
            from confluent_kafka.admin import AdminClient, NewTopic
            ac = AdminClient({"bootstrap.servers": self.cfg.kafka_bootstrap})
            cfgs = {"retention.ms": str(self.cfg.kafka_retention_hours * 3600 * 1000)}
            fs = ac.create_topics([NewTopic(t, num_partitions=self.cfg.kafka_partitions, replication_factor=1, config=cfgs) for t in self._topics()],
                                  request_timeout=10)
            for t, f in fs.items():
                try:
                    f.result(timeout=15)
                    log.info("kafka topic created: %s", t)
                except Exception as e:
                    if "EXISTS" in str(e).upper():
                        log.info("kafka topic exists: %s", t)
                    else:
                        log.warning("kafka topic %s: %s", t, e)
            return
        except ImportError:
            pass
        except Exception as e:
            log.warning("kafka admin (confluent) failed: %s", e)
            return
        try:
            from kafka.admin import KafkaAdminClient, NewTopic
            ac = KafkaAdminClient(bootstrap_servers=self.cfg.kafka_bootstrap)
            ac.create_topics([NewTopic(t, self.cfg.kafka_partitions, 1, topic_configs={"retention.ms": str(self.cfg.kafka_retention_hours * 3600 * 1000)})
                              for t in self._topics()])
        except Exception as e:
            log.info("kafka admin (kafka-python): %s", e)

    def _make_producer(self):
        try:
            from confluent_kafka import Producer
            self.p = Producer({"bootstrap.servers": self.cfg.kafka_bootstrap, "acks": "all", "enable.idempotence": True,
                               "linger.ms": 50, "batch.num.messages": 10000, "compression.type": "lz4",
                               "queue.buffering.max.messages": 500000, "reconnect.backoff.ms": 500, "reconnect.backoff.max.ms": 15000,
                               "log.connection.close": False,
                               "message.timeout.ms": int(os.environ.get("KAFKA_MESSAGE_TIMEOUT_MS", 120000))})
            self.lib = "confluent"
        except ImportError:
            from kafka import KafkaProducer
            self.p = KafkaProducer(bootstrap_servers=self.cfg.kafka_bootstrap, acks="all", linger_ms=50, batch_size=262144,
                                   compression_type="gzip", retries=5)
            self.lib = "kafka-python"
        log.info("kafka producer ready (%s) -> %s", self.lib, self.cfg.kafka_bootstrap)

    # -- send
    def send(self, topic: str, key: str, value: bytes):
        if self.mode == "null":
            self.sent += 1
            return
        if self.mode == "file":
            fh = self.fh.get(topic)
            if fh is None:
                fh = self.fh[topic] = open(self.fdir / f"{topic}.jsonl", "ab")
            fh.write(value + b"\n")
            self.sent += 1
            return
        kb = key.encode()
        try:
            if self.lib == "confluent":
                try:
                    self.p.produce(topic, value=value, key=kb, on_delivery=self._on_delivery)
                except BufferError:
                    self.p.poll(0.5)
                    self.p.produce(topic, value=value, key=kb, on_delivery=self._on_delivery)
                self._since_poll += 1
                if self._since_poll >= 2000:
                    self.p.poll(0)
                    self._since_poll = 0
            else:
                fut = self.p.send(topic, key=kb, value=value)
                fut.add_errback(lambda exc, t=topic, k=kb, v=value: self._failed(t, k, v))
            self.sent += 1
        except Exception:
            self._failed(topic, kb, value)

    def _on_delivery(self, err, msg):
        if err is not None:
            self._failed(msg.topic(), msg.key(), msg.value())

    def _failed(self, topic, key, value):
        self.failed += 1
        self.fail_since_drain += 1
        self.last_fail = time.time()
        self._spool(topic, key, value)

    def _spool(self, topic, key, value):
        with self._lock:
            if self._spool_fh is None:
                self._spool_idx += 1
                self._spool_fh = open(self.spool_dir / f"spool-{self.run_id}-{self._spool_idx:05d}.jsonl", "a")
                self._spool_n = 0
            self._spool_fh.write(json.dumps({"t": topic, "k": (key or b"").decode(), "v": base64.b64encode(value).decode()}) + "\n")
            self._spool_n += 1
            self.spooled += 1
            if self._spool_n >= 20000:
                self._spool_fh.close()
                self._spool_fh = None

    def poll(self):
        if self.mode == "kafka" and self.lib == "confluent":
            self.p.poll(0)
        elif self.mode == "file":
            for fh in self.fh.values():
                fh.flush()

    def flush(self, timeout=30):
        if self.mode != "kafka":
            self.poll()
            return
        try:
            self.p.flush(timeout)
        except TypeError:
            self.p.flush()

    def spool_backlog(self):
        return sum(1 for _ in self.spool_dir.glob("spool-*.jsonl"))

    def drain_spool(self):
        """re-send spooled messages once the broker looks healthy again"""
        if self.mode != "kafka" or time.time() - self.last_fail < 60:
            return 0
        files = sorted(self.spool_dir.glob("spool-*.jsonl"))
        if not files:
            return 0
        if self._spool_fh is not None:
            self._spool_fh.close()
            self._spool_fh = None
        f = files[0]
        self.fail_since_drain = 0
        n = 0
        for line in f.read_text().splitlines():
            d = json.loads(line)
            self.send(d["t"], d["k"], base64.b64decode(d["v"]))
            n += 1
        self.flush(60)
        if self.fail_since_drain == 0:
            f.unlink()
            log.info("kafka spool drained: %s (%d messages)", f.name, n)
            return n
        return 0

    def close(self):
        self.flush(60)
        if self._spool_fh is not None:
            self._spool_fh.close()
        for fh in getattr(self, "fh", {}).values():
            fh.close()


# ----------------------------------------------------------------------------------------
# emitter: routes streams to Kafka / S3-direct, buffers batch entities, dirty-data injection
# ----------------------------------------------------------------------------------------
DIRTY_TEXT = {"customers": ["customer_name"], "loads": ["load_status", "booking_type"], "trips": ["trip_status"],
              "delivery_events": ["location_city"], "fuel_purchases": ["location_city"], "maintenance_records": ["facility_location"]}


class Emitter:
    def __init__(self, cfg: Cfg, kafka: KafkaOut, s3: S3Writer, run_id: str, direct_mask: np.ndarray):
        self.cfg, self.kafka, self.s3, self.run_id, self.direct_mask = cfg, kafka, s3, run_id, direct_mask
        self.rows = collections.defaultdict(list)
        self.dbuf = collections.defaultdict(list)
        self.labels = []
        self.last_batch = self.last_direct = None
        self.seq = collections.Counter()
        self.counts = collections.Counter()
        self.wall_now = time.time()
        self.g = np.random.default_rng(cfg.seed + 7)

    # -- batch entities -------------------------------------------------------------------
    def batch(self, entity: str, row: dict):
        self.rows[entity].append(row)

    def label(self, d: dict):
        self.labels.append(d)

    def _dirty(self, entity, row):
        r, g = self.cfg.dirty_rate, self.g
        if r <= 0:
            return row
        row = dict(row)
        if entity == "trips":
            for k in ("driver_id", "truck_id", "trailer_id"):
                if g.random() < r:
                    row[k] = None
        elif entity == "fuel_purchases":
            for k in ("driver_id", "truck_id"):
                if g.random() < r:
                    row[k] = None
        for c in DIRTY_TEXT.get(entity, ()):
            v = row.get(c)
            if isinstance(v, str) and g.random() < 4 * r:
                row[c] = (v.lower(), v.upper(), v + " ")[int(g.integers(3))]
        return row

    @staticmethod
    def _csv_bytes(entity, rows):
        sio = io.StringIO()
        w = csv.writer(sio)
        cols = SCHEMAS[entity]
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])
        return gzip.compress(sio.getvalue().encode("utf-8"), compresslevel=6)

    def flush_batches(self, sim_t, force=False):
        if not force and (self.last_batch is not None and sim_t - self.last_batch < self.cfg.batch_flush_seconds):
            return
        self.last_batch = sim_t
        dt, hr = day_str(sim_t), hour_str(sim_t)
        for entity in list(self.rows):
            rows = self.rows.pop(entity)
            if not rows:
                continue
            out = []
            for r in rows:
                d = self._dirty(entity, r)
                out.append(d)
                if self.g.random() < 0.003 and entity in ("trips", "loads", "delivery_events", "fuel_purchases", "safety_incidents"):
                    out.append(d)  # duplicate delivery of the same row
            self.seq[entity] += 1
            key = f"bronze/{ENTITY_SOURCE[entity]}/{entity}/dt={dt}/hr={hr}/{entity}-{self.run_id}-{self.seq[entity]:06d}.csv.gz"
            self.s3.put(key, self._csv_bytes(entity, out))
            self.counts["rows_" + entity] += len(rows)
        if self.labels:
            lab, self.labels = self.labels, []
            self.seq["labels"] += 1
            body = gzip.compress(b"\n".join(jdumps(x) for x in lab) + b"\n")
            self.s3.put(f"ground_truth/gen_anomaly_labels/dt={dt}/labels-{self.run_id}-{self.seq['labels']:06d}.jsonl.gz", body)
            self.counts["labels"] += len(lab)

    # -- streams ---------------------------------------------------------------------------
    def stream(self, kind: str, vidx: int, msg: dict, ingest_t: float):
        msg["ingest_ts"] = iso(ingest_t)
        self._route(kind, vidx, jdumps(msg), ingest_t, msg["vehicle_id"])

    def stream_raw(self, kind: str, vidx: int, b: bytes, ingest_t: float, key: str):
        self._route(kind, vidx, b, ingest_t, key)

    def _route(self, kind, vidx, b, ingest_t, key):
        direct = bool(self.direct_mask[vidx]) or (self.wall_now - ingest_t > self.cfg.kafka_horizon_hours * 3600)
        if direct:
            self.dbuf[(kind, day_str(ingest_t), hour_str(ingest_t))].append(b)
            self.counts[kind + "_s3direct"] += 1
        else:
            self.kafka.send(self.cfg.topic_telemetry if kind == "telemetry" else self.cfg.topic_reefer, key, b)
            self.counts[kind + "_kafka"] += 1

    def flush_direct(self, sim_t, force=False):
        if not force and (self.last_direct is not None and sim_t - self.last_direct < self.cfg.s3_flush_seconds):
            return
        self.last_direct = sim_t
        for (kind, dt, hr), lines in list(self.dbuf.items()):
            if not lines:
                continue
            self.seq["direct_" + kind] += 1
            key = f"bronze/stream_direct/{kind}/dt={dt}/hr={hr}/{kind}-{self.run_id}-{self.seq['direct_' + kind]:06d}.jsonl.gz"
            self.s3.put(key, gzip.compress(b"\n".join(lines) + b"\n", compresslevel=5))
            del self.dbuf[(kind, dt, hr)]

    def flush_all(self, sim_t):
        self.flush_batches(sim_t, force=True)
        self.flush_direct(sim_t, force=True)
        self.kafka.flush(60)


# ----------------------------------------------------------------------------------------
# the fleet (vectorised state machine)
# ----------------------------------------------------------------------------------------
WAITING, LOADING, DRIVING, FUELING, BREAK, RESTING, UNLOADING, MAINT, INCIDENT, ANOM_IDLE = range(10)
ENGINE_ON = np.array([0, 1, 1, 1, 1, 0, 1, 0, 1, 1], bool)
IDLE_BURN = np.array([0, 1, 0, 1, 1, 0, 1, 0, 1, 1], bool)  # engine on but not driving
# steady-state mix measured for WAIT_MEAN_HOURS=60 (re-measure if you change it)
WARM_MIX = [(DRIVING, 0.22), (RESTING, 0.13), (WAITING, 0.59), (LOADING, 0.01), (UNLOADING, 0.02), (FUELING, 0.006), (BREAK, 0.012), (MAINT, 0.02)]
INF = float("inf")


class Fleet:
    def __init__(self, cfg: Cfg, ref: Ref, wx: Weather, diesel: DieselPrice, em: Emitter, rng: np.random.Generator, t0: float):
        self.cfg, self.ref, self.wx, self.diesel, self.em, self.rng = cfg, ref, wx, diesel, em, rng
        N = self.N = cfg.fleet_size
        self.dt = cfg.tick_seconds
        self.t, self.tick = float(t0), 0
        z = lambda dtype=float, v=0: np.full(N, v, dtype=dtype)
        self.state, self.until = z(np.int8), z()
        self.route, self.prog, self.rlen = z(np.int64), z(), z(float, 1.0)
        self.assigned = z(bool)
        self.speed, self.cruise, self.aggr = z(), z(), z(bool)
        self.lat, self.lon, self.heading = z(), z(), z()
        self.odo, self.fuel, self.tank, self.mpg = z(), z(), z(), z(float, 6.5)
        self.idle_gph, self.eng_temp, self.gph = z(), z(), z()
        self.hos_drive, self.hos_duty, self.hos_brk = z(), z(), z()
        self.trip_miles, self.trip_fuel, self.trip_idle = z(), z(), z()
        self.near, self.amb = z(np.int64), z()
        self.r_active, self.cargo, self.setpoint, self.tmax = z(bool), z(), z(), z()
        self.comp, self.door_until = z(bool), z()
        self.fail_at, self.fail_until, self.fail_start, self.fail_done = z(float, INF), z(), z(), z(bool)
        self.breach_open, self.breach_start, self.breach_peak = z(bool), z(), z()
        self.idle_at, self.idle_dur, self.idle_done, self.idle_t0 = z(float, INF), z(), z(bool), z()
        self.dev_at, self.dev_len, self.dev_amp = z(float, INF), z(float, 1.0), z()
        self.dev_t0, self.dev_done = z(float, np.nan), z(bool)
        self.cong_until, self.cong_factor = z(), z(float, 1.0)
        self.maint_due = z(bool)
        self.drv = np.arange(N)
        self.trl = z(np.int64, -1)
        self.phase = rng.integers(0, self.dt, N)
        self.seq_t, self.seq_r = z(np.int64), z(np.int64)
        self.trips, self.maint, self.incident = [None] * N, [None] * N, [None] * N
        self.ctr = collections.Counter()
        self.delayq = []
        self.veh_ids = [f"TRK{i + 1:05d}" for i in range(N)]
        self.dev_ids = [f"TU-{i + 1:05d}" for i in range(N)]
        # static attributes ----------------------------------------------------------------
        self.tank[:] = rng.choice([150, 200, 250], N, p=[0.25, 0.5, 0.25])
        self.aggr[:] = rng.random(N) < 0.08
        self.cruise[:] = rng.normal(62, 2.5, N) + 9.0 * self.aggr
        self.idle_gph[:] = np.clip(rng.normal(0.85, 0.12, N), 0.5, 1.3)
        self.odo[:] = rng.uniform(50_000, 700_000, N)
        self.trucks_info = [dict(unit=int(rng.integers(1000, 10000)), make=str(rng.choice(MAKES)), year=int(rng.integers(2015, 2023)),
                                 vin="1" + "".join(rng.choice(list("ABCDEFGHJKLMNPRSTUVWXYZ0123456789"), 16)),
                                 acq=f"{int(rng.integers(2015, 2023))}-{int(rng.integers(1, 13)):02d}-{int(rng.integers(1, 28)):02d}",
                                 acq_mi=int(rng.integers(200, 50000)), home=int(rng.integers(NC_))) for _ in range(N)]
        # drivers: 25% bench so turnover can swap people ---------------------------------------
        Nd = int(math.ceil(N * 1.25))
        self.drivers = [self._new_driver() for _ in range(Nd)]
        self.spare = collections.deque(range(N, Nd))
        self.pending_term = set()
        # trailers ------------------------------------------------------------------------------
        Nt = int(math.ceil(N * 1.5))
        self.trl_info = []
        for k in range(Nt):
            self.trl_info.append(self._new_trailer(reefer=(k % 2 == 0), city=int(rng.integers(NC_))))
        self.free = {True: collections.deque(), False: collections.deque()}
        for k in rng.permutation(Nt):
            self.free[self.trl_info[int(k)]["reefer"]].append(int(k))
        self._warm_start(t0)
        self.odo0 = self.odo.copy()

    # ---- entity factories ---------------------------------------------------------------------
    def _new_driver(self):
        rng = self.rng
        self.ctr["driver"] += 1
        n = self.ctr["driver"]
        return dict(id=f"DRV{n:05d}", first=str(rng.choice(FIRST)), last=str(rng.choice(LAST)),
                    hire=f"{int(rng.integers(2012, 2026))}-{int(rng.integers(1, 13)):02d}-{int(rng.integers(1, 28)):02d}", term=None,
                    lic=f"DL{int(rng.integers(100_000_000, 999_999_999))}", lic_state=str(rng.choice(STATES_LIC)),
                    dob=f"{int(rng.integers(1960, 2001))}-{int(rng.integers(1, 13)):02d}-{int(rng.integers(1, 28)):02d}",
                    home=int(rng.integers(NC_)), status="Active", yrs=int(rng.integers(2, 26)))

    def _new_trailer(self, reefer, city):
        rng = self.rng
        self.ctr["trailer"] += 1
        n = self.ctr["trailer"]
        return dict(id=f"TRL{n:05d}", num=int(rng.integers(1000, 10000)), reefer=bool(reefer), year=int(rng.integers(2015, 2025)),
                    vin="1" + "".join(rng.choice(list("ABCDEFGHJKLMNPRSTUVWXYZ0123456789"), 16)),
                    acq=f"{int(rng.integers(2015, 2023))}-{int(rng.integers(1, 13)):02d}-{int(rng.integers(1, 28)):02d}", city=city)

    def _pop_trailer(self, reefer):
        dq = self.free[bool(reefer)]
        if dq:
            return dq.popleft()
        self.trl_info.append(self._new_trailer(reefer, 0))
        return len(self.trl_info) - 1

    # ---- stochastic durations (seconds) --------------------------------------------------------
    def _load_dur(self):
        return float(np.clip(self.rng.gamma(2, 38), 5, 239)) * 60

    def _unload_dur(self):
        return float(np.clip(self.rng.gamma(2, 53), 5, 239)) * 60

    def _delay(self, mean_min):
        d = float(self.rng.exponential(mean_min)) * 60
        if self.rng.random() < 0.08:
            d += float(self.rng.uniform(60, 240)) * 60
        return d

    def _plan_hours(self, L, tank):
        drive = L / 60.0
        return drive + (drive // 11) * 10 + (drive // 8) * 0.5 + (L / (tank * 6.0)) * 0.4

    # ---- trips ------------------------------------------------------------------------------------
    def _make_trip(self, i, r, pickup_sched, delay, load_dur):
        rng, cfg, ref = self.rng, self.cfg, self.ref
        L = ref.rlen[r]
        reefer = bool(rng.random() < cfg.reefer_load_share)
        self.ctr["trip"] += 1
        self.ctr["load"] += 1
        trip = dict(id=f"TRIP{self.ctr['trip']:08d}", load=f"LOAD{self.ctr['load']:08d}", r=int(r), drv=int(self.drv[i]),
                    trl=self._pop_trailer(reefer), reefer=reefer, cust=int(rng.integers(len(ref.cust))),
                    weight=int(rng.integers(10_000, 45_001)), pieces=int(rng.integers(1, 29)),
                    booking=str(rng.choice(["Dedicated", "Contract", "Spot"], p=[0.496, 0.252, 0.252])),
                    acc=int(rng.choice([0, 50, 100, 200], p=[0.377, 0.208, 0.208, 0.207])),
                    pickup_sched=float(pickup_sched), delay=float(delay), load_dur=float(load_dur),
                    pickup_start=float(pickup_sched + delay), depart=None, arrive=None, unload_start=None, unload_dur=None, q=None)
        plan = self._plan_hours(L, self.tank[i]) * (1 + cfg.delivery_slack)
        trip["deliv_sched"] = float(math.ceil((pickup_sched + load_dur + plan * 3600) / 3600) * 3600)
        trip["est_h"] = plan
        if reefer:
            w = [c[1] for c in COMMODITIES]
            c = COMMODITIES[int(rng.choice(len(COMMODITIES), p=w))]
            trip.update(comm=c[0], sp=c[2], tmin=c[3], tmax=c[4])
        return trip

    def _schedule_anoms(self, i, L, trip, t_ref, progress=0.0):
        rng = self.rng
        self.idle_done[i], self.dev_done[i], self.fail_done[i] = False, False, False
        self.idle_at[i] = rng.uniform(0.1, 0.9) * L if (rng.random() < P_IDLE_ANOM and L > 100) else INF
        self.idle_dur[i] = rng.uniform(45, 150) * 60
        if rng.random() < P_DEVIATION and L > 150:
            self.dev_len[i] = rng.uniform(20, min(80, 0.4 * L))
            self.dev_at[i] = rng.uniform(0.15, 0.75) * L
            self.dev_amp[i] = rng.uniform(6, 25)
        else:
            self.dev_at[i] = INF
        self.dev_t0[i] = np.nan
        if self.idle_at[i] < progress:
            self.idle_done[i] = True
        if self.dev_at[i] + self.dev_len[i] < progress:
            self.dev_done[i] = True
        self.fail_at[i] = (t_ref + rng.uniform(0.05, 0.9) * trip["est_h"] * 3600) if (trip["reefer"] and rng.random() < P_REEFER_FAIL) else INF

    def _assign(self, i, t):
        rng, ref = self.rng, self.ref
        if i in self.pending_term and self.spare:  # driver turnover happens between trips
            old = self.drivers[int(self.drv[i])]
            old["status"], old["term"] = "Terminated", day_str(t)
            self.drv[i] = self.spare.popleft()
            self.drivers.append(self._new_driver())
            self.spare.append(len(self.drivers) - 1)
            self.pending_term.discard(i)
        cand = ref.routes_from[int(self.near[i])]
        if len(cand):
            w = ref.rlen[cand] ** 1.5
            r = int(cand[int(rng.choice(len(cand), p=w / w.sum()))])
        else:
            r = int(rng.integers(ref.R))
        ps = math.ceil((t + rng.uniform(1, 6) * 3600) / 3600) * 3600
        delay, ld = self._delay(12), self._load_dur()
        trip = self._make_trip(i, r, ps, delay, ld)
        self.trips[i] = trip
        self.route[i], self.prog[i], self.rlen[i] = r, 0.0, ref.rlen[r]
        self.mpg[i] = rng.uniform(5.8, 7.8)
        self.trl[i] = trip["trl"]
        self.trip_miles[i] = self.trip_fuel[i] = self.trip_idle[i] = 0.0
        self.assigned[i], self.state[i], self.until[i] = True, WAITING, trip["pickup_start"]
        self._schedule_anoms(i, ref.rlen[r], trip, trip["pickup_start"])

    # ---- warm start (fleet is in steady state at t0) ---------------------------------------------------
    def _warm_start(self, t0):
        rng, ref = self.rng, self.ref
        kinds = [k for k, _ in WARM_MIX]
        probs = np.array([p for _, p in WARM_MIX])
        pick = rng.choice(len(kinds), self.N, p=probs / probs.sum())
        for i in range(self.N):
            kind = kinds[int(pick[i])]
            r = int(rng.integers(ref.R))
            L = ref.rlen[r]
            self.mpg[i] = rng.uniform(5.8, 7.8)
            self.fuel[i] = self.tank[i] * rng.uniform(0.3, 0.95)
            self.eng_temp[i] = 195.0
            self.near[i] = ref.rdest[r]
            if kind in (DRIVING, RESTING, FUELING, BREAK):
                p = rng.uniform(0.03, 0.97) * L
                depart = t0 - p / 58.0 * 3600
                ld, dl = self._load_dur(), self._delay(12)
                trip = self._make_trip(i, r, depart - ld - dl, dl, ld)
                trip.update(depart=depart)
                self.trips[i] = trip
                self.route[i], self.prog[i], self.rlen[i], self.trl[i] = r, p, L, trip["trl"]
                self.trip_miles[i], self.trip_fuel[i] = p, p / self.mpg[i]
                self.trip_idle[i] = rng.uniform(1, 4) * 3600
                self.assigned[i] = True
                self.hos_drive[i] = rng.uniform(0, 8) * 3600
                self.hos_duty[i] = self.hos_drive[i] + rng.uniform(0, 1.5) * 3600
                self.hos_brk[i] = min(self.hos_drive[i], rng.uniform(0, 8) * 3600)
                self.speed[i] = 0.0
                self.state[i] = kind
                if kind == DRIVING:
                    self.speed[i] = self.cruise[i]
                elif kind == RESTING:
                    self.until[i], self.hos_drive[i] = t0 + rng.uniform(0, 10) * 3600, 11 * 3600
                elif kind == FUELING:
                    self.until[i] = t0 + rng.uniform(0, 25) * 60
                else:
                    self.until[i], self.hos_brk[i] = t0 + rng.uniform(0, 30) * 60, 8 * 3600
                self._schedule_anoms(i, L, trip, t0, progress=p)
                if trip["reefer"]:
                    self._reefer_on(i, t0, warm=True)
            elif kind == LOADING:
                ld, dl = self._load_dur(), self._delay(12)
                ps = t0 - float(rng.uniform(0, 1)) * ld - dl
                trip = self._make_trip(i, r, ps, dl, ld)
                self.trips[i] = trip
                self.near[i] = ref.rorig[r]
                self.route[i], self.prog[i], self.rlen[i], self.trl[i] = r, 0.0, L, trip["trl"]
                self.assigned[i], self.state[i], self.until[i] = True, LOADING, trip["pickup_start"] + ld
                self._schedule_anoms(i, L, trip, t0)
                if trip["reefer"]:
                    self._reefer_on(i, t0, warm=True)
            elif kind == UNLOADING:
                ud = self._unload_dur()
                arrive = t0 - float(rng.uniform(0, 1)) * ud
                ld, dl = self._load_dur(), self._delay(12)
                depart = arrive - L / 58.0 * 3600
                trip = self._make_trip(i, r, depart - ld - dl, dl, ld)
                trip.update(depart=depart, arrive=arrive, q=0.0, unload_start=arrive, unload_dur=ud)
                self.trips[i] = trip
                self.route[i], self.prog[i], self.rlen[i], self.trl[i] = r, L, L, trip["trl"]
                self.trip_miles[i], self.trip_fuel[i], self.trip_idle[i] = L, L / self.mpg[i], 3 * 3600
                self.assigned[i], self.state[i], self.until[i] = True, UNLOADING, arrive + ud
                self.dev_at[i], self.idle_at[i], self.fail_at[i] = INF, INF, INF
                if trip["reefer"]:
                    self._reefer_on(i, t0, warm=True)
            elif kind == MAINT:
                self.route[i], self.prog[i], self.rlen[i] = r, L, L
                self._maint_begin(i, t0 - float(rng.uniform(0, 20)) * 3600)
            else:  # WAITING (no load yet)
                self.route[i], self.prog[i], self.rlen[i] = r, L, L
                self.state[i], self.until[i] = WAITING, t0 + float(rng.exponential(self.cfg.wait_mean_hours)) * 3600
        self._positions()

    # ---- reefer ------------------------------------------------------------------------------------------
    def _reefer_on(self, i, t, warm=False):
        trip, rng = self.trips[i], self.rng
        self.r_active[i] = True
        self.setpoint[i], self.tmax[i] = trip["sp"], trip["tmax"]
        self.cargo[i] = trip["sp"] + (rng.uniform(-1, 1) if warm else rng.uniform(0, 2))
        self.comp[i], self.door_until[i], self.fail_until[i] = True, 0.0, 0.0
        self.breach_open[i] = False

    def _reefer_off(self, i, t):
        if self.breach_open[i]:
            self._close_breach(i, t)
        self.r_active[i] = False

    def _close_breach(self, i, t):
        trip = self.trips[i]
        cause = "refrigeration_failure" if self.fail_start[i] > 0 and self.breach_start[i] >= self.fail_start[i] - 60 else "heat_or_door"
        self.em.label(dict(anomaly_id=self._aid(), anomaly_type="COLD_CHAIN_BREACH", vehicle_id=self.veh_ids[i], trip_id=trip["id"] if trip else None,
                           start_ts=iso(self.breach_start[i]), end_ts=iso(t),
                           params=json.dumps({"peak_temp_f": round(float(self.breach_peak[i]), 1), "threshold_f": float(self.tmax[i]), "cause": cause})))
        self.breach_open[i] = False

    def _aid(self):
        self.ctr["anom"] += 1
        return f"A{self.ctr['anom']:08d}"

    def _reefer_physics(self, ra, t, dt):
        dtm = dt / 60.0
        amb, st = self.amb[ra], self.state[ra]
        door = (st == LOADING) | (st == UNLOADING) | (t < self.door_until[ra])
        leak = K_LEAK * (amb - self.cargo[ra]) * (1 + DOOR_FACTOR * door) * dtm
        cap = np.maximum(0.06, CAP0 - CAP_DERATE * np.maximum(amb - 75, 0)) * dtm
        sp, cg = self.setpoint[ra], self.cargo[ra]
        c = np.where(cg > sp + DEADBAND, True, np.where(cg < sp - DEADBAND, False, self.comp[ra]))
        # scheduled refrigeration failure
        start = (t >= self.fail_at[ra]) & ~self.fail_done[ra]
        for k in np.nonzero(start)[0]:
            i = ra[k]
            self.fail_done[i], self.fail_start[i] = True, t
            self.fail_until[i] = t + self.rng.uniform(45, 240) * 60
            self.fail_at[i] = INF
            self.em.label(dict(anomaly_id=self._aid(), anomaly_type="REEFER_UNIT_FAILURE", vehicle_id=self.veh_ids[i],
                               trip_id=self.trips[i]["id"], start_ts=iso(t), end_ts=iso(self.fail_until[i]),
                               params=json.dumps({"duration_min": round((self.fail_until[i] - t) / 60, 1)})))
        failing = t < self.fail_until[ra]
        c = c & ~failing
        self.comp[ra] = c
        self.cargo[ra] = cg + leak - c * cap
        # breach bookkeeping (noise-free truth)
        br = self.cargo[ra] > self.tmax[ra]
        for k in np.nonzero(br & ~self.breach_open[ra])[0]:
            i = ra[k]
            self.breach_open[i], self.breach_start[i], self.breach_peak[i] = True, t, self.cargo[i]
        still = br & self.breach_open[ra]
        if still.any():
            ii = ra[still]
            self.breach_peak[ii] = np.maximum(self.breach_peak[ii], self.cargo[ii])
        for k in np.nonzero(~br & self.breach_open[ra])[0]:
            self._close_breach(ra[k], t)

    # ---- positions -------------------------------------------------------------------------------------------
    def _positions(self):
        r = self.route
        L = np.floor(self.rlen).astype(np.int64)
        k = np.minimum(self.prog.astype(np.int64), L)
        f = np.clip(self.prog - k, 0, 1)
        g0a, g0o = self.ref.glat[r, k], self.ref.glon[r, k]
        g1a, g1o = self.ref.glat[r, k + 1], self.ref.glon[r, k + 1]
        lat, lon = g0a * (1 - f) + g1a * f, g0o * (1 - f) + g1o * f
        moving = ENGINE_ON[self.state] & (self.state == DRIVING)
        dla, dlo = g1a - g0a, (g1o - g0o) * np.cos(np.radians(lat))
        hd = (np.degrees(np.arctan2(dlo, dla)) + 360) % 360
        self.heading = np.where(moving & ((dla != 0) | (dlo != 0)), hd, self.heading)
        # route deviation: smooth lateral bump while inside the window
        inwin = (self.state == DRIVING) & (self.prog >= self.dev_at) & (self.prog <= self.dev_at + self.dev_len)
        if inwin.any():
            off = np.where(inwin, self.dev_amp * np.sin(np.pi * np.clip((self.prog - self.dev_at) / self.dev_len, 0, 1)), 0.0)
            b = np.radians(self.heading + 90)
            lat = lat + off * np.cos(b) / MI_PER_DEG
            lon = lon + off * np.sin(b) / (MI_PER_DEG * np.cos(np.radians(lat)))
        self.lat, self.lon = lat, lon

    # ---- one tick ----------------------------------------------------------------------------------------------
    def step(self):
        t, dt = self.t, self.dt
        te = t + dt
        st = self.state
        self.amb = np.asarray(self.wx.ambient(self.near, t), dtype=float)
        ra = np.nonzero(self.r_active)[0]
        if ra.size:
            self._reefer_physics(ra, t, dt)
        # timed completions
        for i in np.nonzero((st != DRIVING) & (self.until <= te))[0]:
            self._complete(int(i), te)
        # driving physics
        d = np.nonzero(self.state == DRIVING)[0]
        mi = np.zeros(0)
        if d.size:
            newc = (self.cong_until[d] < t) & (self.rng.random(d.size) < 0.0015 * dt / 60)
            if newc.any():
                self.cong_until[d[newc]] = t + self.rng.uniform(600, 2400, newc.sum())
                self.cong_factor[d[newc]] = self.rng.uniform(0.45, 0.7, newc.sum())
            f = np.where(self.cong_until[d] > t, self.cong_factor[d], 1.0)
            f = f * np.where((self.prog[d] < 20) | (self.rlen[d] - self.prog[d] < 20), 0.72, 1.0)
            v = np.clip(0.55 * self.speed[d] + 0.45 * self.cruise[d] * f + self.rng.normal(0, 1.2, d.size), 0, 78)
            self.speed[d] = v
            mi = v * dt / 3600.0
            self.prog[d] = np.minimum(self.prog[d] + mi, self.rlen[d])
            self.odo[d] += mi
            self.trip_miles[d] += mi
            eff = np.clip(1 - 0.007 * np.maximum(v - 60, 0), 0.7, 1.0)
            g = np.where(v > 2, v / (self.mpg[d] * eff), self.idle_gph[d])
            self.gph[d] = g
            burn = g * dt / 3600.0
            self.fuel[d] -= burn
            self.trip_fuel[d] += burn
            self.hos_drive[d] += dt
            self.hos_duty[d] += dt
            self.hos_brk[d] += dt
        # engine-on, not driving: idle burn
        ib = np.nonzero(IDLE_BURN[self.state])[0]
        if ib.size:
            self.speed[ib] = 0.0
            self.gph[ib] = self.idle_gph[ib]
            self.fuel[ib] -= self.idle_gph[ib] * dt / 3600.0
            self.hos_duty[ib] += dt
            has = np.array([self.trips[j] is not None for j in ib])
            if has.any():
                jj = ib[has]
                self.trip_fuel[jj] += self.idle_gph[jj] * dt / 3600.0
                self.trip_idle[jj] += dt
        off = np.nonzero(~ENGINE_ON[self.state])[0]
        if off.size:
            self.speed[off] = 0.0
            self.gph[off] = 0.0
        self._positions()
        if d.size:
            self.near[d] = nearest_city(self.lat[d], self.lon[d])
            self._driving_events(d, te, mi)
        # engine temperature (first-order lag to target)
        target = np.where(ENGINE_ON[self.state], 195.0 + 0.25 * self.speed, self.amb)
        alpha = np.where(ENGINE_ON[self.state], 1 - math.exp(-dt / 420.0), 1 - math.exp(-dt / 1500.0))
        self.eng_temp += (target - self.eng_temp) * alpha
        # maintenance due (Poisson)
        self.maint_due |= self.rng.random(self.N) < MAINT_PER_YEAR * dt / (365.0 * 86400)
        self.t = te
        self.tick += 1

    def _driving_events(self, d, te, mi):
        L, p = self.rlen[d], self.prog[d]
        # deviation label bookkeeping
        ent = (p >= self.dev_at[d]) & np.isnan(self.dev_t0[d]) & ~self.dev_done[d]
        self.dev_t0[d[ent]] = te
        ex = (p > self.dev_at[d] + self.dev_len[d]) & ~self.dev_done[d] & ~np.isnan(self.dev_t0[d])
        for k in np.nonzero(ex)[0]:
            i = d[k]
            self.dev_done[i] = True
            self.em.label(dict(anomaly_id=self._aid(), anomaly_type="ROUTE_DEVIATION", vehicle_id=self.veh_ids[i], trip_id=self.trips[i]["id"],
                               start_ts=iso(self.dev_t0[i]), end_ts=iso(te),
                               params=json.dumps({"max_offset_miles": round(float(self.dev_amp[i]), 1), "length_miles": round(float(self.dev_len[i]), 1)})))
        arrived = p >= L
        lowfuel = self.fuel[d] < 0.18 * self.tank[d]
        hos = (self.hos_drive[d] >= 11 * 3600) | (self.hos_duty[d] >= 14 * 3600)
        brk = self.hos_brk[d] >= 8 * 3600
        idl = (~self.idle_done[d]) & (p >= self.idle_at[d])
        inc = self.rng.random(d.size) < mi * INCIDENT_PER_MILE
        for k in np.nonzero(arrived | lowfuel | hos | brk | idl | inc)[0]:
            i = int(d[k])
            if arrived[k]:
                self._arrive(i, te)
            elif idl[k]:
                self.state[i], self.until[i], self.idle_done[i], self.idle_t0[i] = ANOM_IDLE, te + self.idle_dur[i], True, te
                self.speed[i] = 0.0
            elif inc[k]:
                self._incident_begin(i, te)
            elif lowfuel[k]:
                self._fuel_begin(i, te)
            elif hos[k]:
                self.state[i], self.until[i], self.speed[i] = RESTING, te + 10 * 3600 + float(self.rng.uniform(0, 3600)), 0.0
            elif brk[k]:
                self.state[i], self.until[i], self.speed[i] = BREAK, te + 1800, 0.0

    # ---- state handlers --------------------------------------------------------------------------------------------
    def _complete(self, i, te):
        s, trip = int(self.state[i]), self.trips[i]
        if s == WAITING:
            if self.assigned[i]:  # pickup begins
                self.state[i], self.until[i] = LOADING, trip["pickup_start"] + trip["load_dur"]
                self.hos_drive[i] = self.hos_duty[i] = self.hos_brk[i] = 0.0
                if trip["reefer"]:
                    self._reefer_on(i, te)
            elif self.maint_due[i]:
                self._maint_begin(i, te)
            else:
                self._assign(i, te)
        elif s == LOADING:
            trip["depart"] = te
            self.state[i] = DRIVING
        elif s == UNLOADING:
            self._finish_trip(i, te)
        elif s == FUELING:
            self.state[i] = DRIVING
        elif s == BREAK:
            self.hos_brk[i] = 0.0
            self.state[i] = DRIVING
        elif s == RESTING:
            self.hos_drive[i] = self.hos_duty[i] = self.hos_brk[i] = 0.0
            self.state[i] = DRIVING
        elif s == INCIDENT:
            self.state[i] = DRIVING
        elif s == ANOM_IDLE:
            self.em.label(dict(anomaly_id=self._aid(), anomaly_type="EXCESSIVE_IDLING", vehicle_id=self.veh_ids[i], trip_id=trip["id"],
                               start_ts=iso(self.idle_t0[i]), end_ts=iso(te),
                               params=json.dumps({"duration_min": round((te - self.idle_t0[i]) / 60, 1), "city": CITIES[int(self.near[i])][0]})))
            self.state[i] = DRIVING
        elif s == MAINT:
            self._maint_end(i, te)

    def _arrive(self, i, te):
        trip = self.trips[i]
        self.speed[i] = 0.0
        self.prog[i] = self.rlen[i]
        q, ud = self._delay(20), self._unload_dur()
        trip.update(arrive=te, q=q, unload_start=te + q, unload_dur=ud)
        self.state[i], self.until[i] = UNLOADING, te + q + ud

    def _finish_trip(self, i, te):
        trip, ref, rng = self.trips[i], self.ref, self.rng
        r = ref.routes[trip["r"]]
        L = ref.rlen[trip["r"]]
        cust = ref.cust[trip["cust"]]
        drv = self.drivers[trip["drv"]]
        grace = 900.0
        pick_ok = trip["delay"] <= grace
        del_ok = trip["unload_start"] <= trip["deliv_sched"] + grace
        oc, dc = CITIES[r["o"]], CITIES[r["d"]]
        ofac, dfac = ref.fac_by_city[r["o"]], ref.fac_by_city[r["d"]]
        em = self.em
        em.batch("loads", dict(load_id=trip["load"], customer_id=cust["id"], route_id=r["id"], load_date=day_str(trip["pickup_start"]),
                               load_type="Refrigerated" if trip["reefer"] else "Dry Van", weight_lbs=trip["weight"], pieces=trip["pieces"],
                               revenue=round(float(L * r["rate"] * rng.normal(1, 0.08)), 2),
                               fuel_surcharge=round(float(L * r["fsr"] * rng.normal(1, 0.08)), 2), accessorial_charges=trip["acc"],
                               load_status="Completed", booking_type=trip["booking"]))
        fuel_used = max(float(self.trip_fuel[i]), 0.1)
        em.batch("trips", dict(trip_id=trip["id"], load_id=trip["load"], driver_id=drv["id"], truck_id=self.veh_ids[i],
                               trailer_id=self.trl_info[trip["trl"]]["id"], dispatch_date=day_str(trip["pickup_start"]),
                               dispatch_ts=iso(trip["pickup_start"]), arrival_ts=iso(trip["arrive"]),
                               actual_distance_miles=int(round(float(self.trip_miles[i]))),
                               actual_duration_hours=round((trip["arrive"] - trip["pickup_start"]) / 3600, 1),
                               fuel_gallons_used=round(fuel_used, 1), average_mpg=round(float(self.trip_miles[i]) / fuel_used, 2),
                               idle_time_hours=round(float(self.trip_idle[i]) / 3600, 1), trip_status="Completed"))
        for typ, fac, city, sched, act, dur, ok in (
                ("Pickup", ofac, oc, trip["pickup_sched"], trip["pickup_start"], trip["load_dur"], pick_ok),
                ("Delivery", dfac, dc, trip["deliv_sched"], trip["unload_start"], trip["unload_dur"], del_ok)):
            self.ctr["event"] += 1
            em.batch("delivery_events", dict(event_id=f"EVT{self.ctr['event']:08d}", load_id=trip["load"], trip_id=trip["id"], event_type=typ,
                                             facility_id=fac["id"], scheduled_datetime=iso(sched), actual_datetime=iso(act),
                                             detention_minutes=int(round(dur / 60)), on_time_flag=bool(ok), location_city=city[0], location_state=city[1]))
        self.ctr["done"] += 1
        self.ctr["pick_ok"] += int(pick_ok)
        self.ctr["del_ok"] += int(del_ok)
        self.ctr["miles"] += float(self.trip_miles[i])
        self.ctr["fuel"] += float(fuel_used)
        if trip["reefer"]:
            self._reefer_off(i, te)
        info = self.trl_info[trip["trl"]]
        info["city"] = r["d"]
        self.free[info["reefer"]].append(trip["trl"])
        self.trips[i], self.trl[i], self.assigned[i] = None, -1, False
        self.near[i] = r["d"]
        self.prog[i] = self.rlen[i]
        self.dev_at[i] = self.idle_at[i] = self.fail_at[i] = INF
        self.state[i], self.until[i] = WAITING, te + float(rng.exponential(self.cfg.wait_mean_hours)) * 3600

    def _fuel_begin(self, i, te):
        rng = self.rng
        gal = max(5.0, float(self.tank[i] * rng.uniform(0.90, 1.0) - self.fuel[i]))
        self.fuel[i] += gal
        c = CITIES[int(self.near[i])]
        price = self.diesel.at(te, c[1], rng)
        self.ctr["fuel_purchase"] += 1
        trip = self.trips[i]
        self.em.batch("fuel_purchases", dict(fuel_purchase_id=f"FUEL{self.ctr['fuel_purchase']:09d}", trip_id=trip["id"] if trip else None,
                                             truck_id=self.veh_ids[i], driver_id=self.drivers[int(self.drv[i])]["id"], purchase_date=iso(te),
                                             location_city=c[0], location_state=c[1], gallons=round(gal, 1), price_per_gallon=price,
                                             total_cost=round(gal * price, 2), fuel_card_number=f"FC{int(rng.integers(100000, 999999))}"))
        self.state[i], self.until[i], self.speed[i] = FUELING, te + float(rng.uniform(15, 30)) * 60, 0.0

    def _incident_begin(self, i, te):
        rng = self.rng
        typ = INCIDENT_TYPES[int(rng.choice(len(INCIDENT_TYPES), p=[w for _, w in INCIDENT_TYPES]))][0]
        acc = typ == "Accident"
        p_vd, p_cd = {"Accident": (0.85, 0.35), "Equipment Damage": (0.90, 0.05), "Customer Complaint": (0.0, 0.20)}.get(typ, (0.0, 0.0))
        vd = float(rng.uniform(1000, 24600)) if rng.random() < p_vd else 0.0
        cd = float(rng.uniform(5000, 50000)) if rng.random() < p_cd else 0.0
        fine = float(rng.uniform(300, 6000)) if typ in ("DOT Violation", "Moving Violation") else 0.0
        c = CITIES[int(self.near[i])]
        self.ctr["incident"] += 1
        self.em.batch("safety_incidents", dict(incident_id=f"INC{self.ctr['incident']:08d}", trip_id=self.trips[i]["id"], truck_id=self.veh_ids[i],
                                               driver_id=self.drivers[int(self.drv[i])]["id"], incident_date=iso(te), incident_type=typ,
                                               location_city=c[0], location_state=c[1], at_fault_flag=bool(rng.random() < 0.318),
                                               injury_flag=bool(rng.random() < (0.45 if acc else 0.05)), vehicle_damage_cost=round(vd, 2),
                                               cargo_damage_cost=round(cd, 2), claim_amount=round(vd + cd + fine, 2),
                                               preventable_flag=bool(rng.random() < 0.376),
                                               description=f"{rng.choice(['Minor', 'Moderate', 'Severe'])} incident involving "
                                                           f"{rng.choice(['weather', 'traffic', 'equipment', 'other driver', 'road conditions'])}"))
        dur = float(rng.uniform(2, 8) if acc else rng.uniform(0.5, 2.0)) * 3600
        self.state[i], self.until[i], self.speed[i] = INCIDENT, te + dur, 0.0

    def _maint_begin(self, i, te):
        rng = self.rng
        mt = str(rng.choice(MAINT_TYPES))
        lh = float(rng.uniform(0.5, 8))
        parts = float(rng.uniform(0, 160) if mt == "Inspection" else rng.uniform(0, 3500))
        down = float(rng.uniform(2, 48))
        self.maint[i] = dict(start=te, type=mt, lh=lh, lc=lh * float(rng.normal(105, 12)), parts=parts, down=down,
                             desc=f"{rng.choice(['Scheduled', 'Routine', 'Emergency'])} {mt}")
        self.maint_due[i] = False
        self.state[i], self.until[i], self.speed[i] = MAINT, te + down * 3600, 0.0

    def _maint_end(self, i, te):
        m = self.maint[i]
        self.ctr["maint"] += 1
        c = CITIES[int(self.near[i])]
        lc = max(40.0, m["lc"])
        self.em.batch("maintenance_records", dict(maintenance_id=f"MAINT{self.ctr['maint']:08d}", truck_id=self.veh_ids[i],
                                                  maintenance_date=day_str(m["start"]), maintenance_type=m["type"],
                                                  odometer_reading=int(self.odo[i]), labor_hours=round(m["lh"], 1), labor_cost=round(lc, 2),
                                                  parts_cost=round(m["parts"], 2), total_cost=round(lc + m["parts"], 2), facility_location=c[0],
                                                  downtime_hours=round(m["down"], 1), service_description=m["desc"]))
        self.maint[i] = None
        self.state[i], self.until[i] = WAITING, te + float(self.rng.exponential(1.0)) * 3600
        self.assigned[i] = False

    # ---- messages ----------------------------------------------------------------------------------------------------
    def emit_streams(self):
        """build this tick's telemetry/reefer messages and push them to the emitter (with late/dup/malformed noise)"""
        rng, em, cfg = self.rng, self.em, self.cfg
        te, dt = self.t, self.dt   # state is as of the end of the tick
        st = self.state
        rep = ENGINE_ON[st] | (((self.tick + np.arange(self.N)) % cfg.parked_mult) == 0)
        idx = np.nonzero(rep)[0]
        n = idx.size
        if n:
            ets = (te - self.phase[idx]).astype(np.int64)
            sp = np.where(ENGINE_ON[st[idx]], np.maximum(0, self.speed[idx] + rng.normal(0, 0.4, n)), 0.0)
            moving = sp > 1
            rpm = np.where(ENGINE_ON[st[idx]], np.where(moving, 600 + 13 * sp + rng.normal(0, 35, n), 650 + rng.normal(0, 25, n)), 0).astype(int)
            lat = np.round(self.lat[idx] + rng.normal(0, 0.00006, n), 5)
            lon = np.round(self.lon[idx] + rng.normal(0, 0.00006, n), 5)
            et = np.round(self.eng_temp[idx] + rng.normal(0, 0.5, n), 1)
            g = np.round(self.gph[idx] * rng.uniform(0.95, 1.05, n), 2)
            self.seq_t[idx] += 1
            gps_null = rng.random(n) < cfg.p_gps_null
            sp_null = rng.random(n) < cfg.p_speed_null
            r_late, r_dup, r_bad = rng.random(n), rng.random(n), rng.random(n)
            lat_l, lon_l, sp_l, rpm_l, et_l, g_l = lat.tolist(), lon.tolist(), np.round(sp, 1).tolist(), rpm.tolist(), et.tolist(), g.tolist()
            fl, od, hd = np.round(self.fuel[idx], 1).tolist(), np.round(self.odo[idx], 1).tolist(), np.round(self.heading[idx]).astype(int).tolist()
            eon = ENGINE_ON[st[idx]].tolist()
            seq, ets_l, idx_l = self.seq_t[idx].tolist(), ets.tolist(), idx.tolist()
            for k in range(n):
                i = idx_l[k]
                m = {"schema_version": 1, "event_id": f"T{i + 1:05d}{ets_l[k]}", "vehicle_id": self.veh_ids[i], "device_id": self.dev_ids[i],
                     "event_ts": iso_sec(ets_l[k]), "source_sequence": seq[k],
                     "lat": None if gps_null[k] else lat_l[k], "lon": None if gps_null[k] else lon_l[k],
                     "speed_mph": None if sp_null[k] else sp_l[k], "heading_deg": hd[k], "rpm": rpm_l[k], "engine_temp_f": et_l[k],
                     "fuel_gph": g_l[k], "fuel_level_gal": fl[k], "odometer_mi": od[k], "engine_on": eon[k]}
                self._dispatch("telemetry", i, m, te, r_late[k], r_dup[k], r_bad[k])
        ra = np.nonzero(self.r_active)[0]
        if ra.size:
            m_ = ra.size
            ets = (te - self.phase[ra]).astype(np.int64).tolist()
            ct = np.round(self.cargo[ra] + rng.normal(0, 0.3, m_), 1).tolist()
            ab = np.round(self.amb[ra] + rng.normal(0, 0.5, m_), 1).tolist()
            door = ((st[ra] == LOADING) | (st[ra] == UNLOADING)).tolist()
            comp = self.comp[ra].tolist()
            rf = np.round(np.where(self.comp[ra], 0.7, 0.2) + rng.normal(0, 0.03, m_), 2).tolist()
            self.seq_r[ra] += 1
            seq = self.seq_r[ra].tolist()
            r_late, r_dup, r_bad = rng.random(m_), rng.random(m_), rng.random(m_)
            drop = (rng.random(m_) < cfg.p_speed_null).tolist()
            for k, i in enumerate(ra.tolist()):
                tid = self.trl_info[int(self.trl[i])]["id"]
                m = {"schema_version": 1, "event_id": f"R{int(self.trl[i]) + 1:05d}{ets[k]}", "vehicle_id": self.veh_ids[i], "trailer_id": tid,
                     "sensor_id": f"RF-{tid}-S1", "event_ts": iso_sec(ets[k]), "source_sequence": seq[k],
                     "cargo_temp_f": None if drop[k] else ct[k], "setpoint_f": float(self.setpoint[i]), "compressor_on": comp[k],
                     "door_open": door[k], "ambient_temp_f": ab[k], "reefer_fuel_gph": rf[k], "unit_mode": "CONTINUOUS"}
                self._dispatch("reefer", i, m, te, r_late[k], r_dup[k], r_bad[k])
        # release delayed (late) messages that are now due
        while self.delayq and self.delayq[0][0] <= te:
            rel, _, kind, i, m = heapq.heappop(self.delayq)
            em.stream(kind, i, m, rel)

    def _dispatch(self, kind, i, m, te, r_late, r_dup, r_bad):
        cfg, em, rng = self.cfg, self.em, self.rng
        if r_bad < cfg.p_malformed:
            b = jdumps(m)
            em.stream_raw(kind, i, (b[:-12] if r_bad < cfg.p_malformed / 2 else b.replace(b'"event_ts"', b'"event_tz"', 1)), te + 1.0, m["vehicle_id"])
            return
        if r_late < cfg.p_late:
            self.ctr["late"] += 1
            heapq.heappush(self.delayq, (te + float(rng.uniform(120, 900)), self.ctr["late"], kind, i, m))
        else:
            em.stream(kind, i, m, te + float(rng.uniform(1, 3)))
        if r_dup < cfg.p_dup:  # duplicate delivery of the same event (same event_id)
            m2 = dict(m)
            em.stream(kind, i, m2, te + float(rng.uniform(4, 12)))

    # ---- snapshots / master data (daily) -------------------------------------------------------------------------------
    def snapshots(self, t):
        d, em, ref = day_str(t), self.em, self.ref
        for i in range(self.N):
            ti = self.trucks_info[i]
            em.batch("trucks", dict(truck_id=self.veh_ids[i], unit_number=ti["unit"], make=ti["make"], model_year=ti["year"], vin=ti["vin"],
                                    acquisition_date=ti["acq"], acquisition_mileage=ti["acq_mi"], fuel_type="Diesel",
                                    tank_capacity_gallons=int(self.tank[i]), status="Maintenance" if self.state[i] == MAINT else "Active",
                                    home_terminal=CITIES[ti["home"]][0], snapshot_date=d))
        for k, tr in enumerate(self.trl_info):
            em.batch("trailers", dict(trailer_id=tr["id"], trailer_number=tr["num"], trailer_type="Refrigerated" if tr["reefer"] else "Dry Van",
                                      length_feet=53, model_year=tr["year"], vin=tr["vin"], acquisition_date=tr["acq"], status="Active",
                                      current_location=CITIES[tr["city"]][0], snapshot_date=d))
        for dr in self.drivers:
            em.batch("drivers", dict(driver_id=dr["id"], first_name=dr["first"], last_name=dr["last"], hire_date=dr["hire"],
                                     termination_date=dr["term"], license_number=dr["lic"], license_state=dr["lic_state"], date_of_birth=dr["dob"],
                                     home_terminal=CITIES[dr["home"]][0], employment_status=dr["status"], cdl_class="A",
                                     years_experience=dr["yrs"], snapshot_date=d))
        for c in ref.cust:
            em.batch("customers", dict(customer_id=c["id"], customer_name=c["name"], customer_type=c["type"], credit_terms_days=c["credit"],
                                       primary_freight_type=c["freight"], account_status=c["status"], contract_start_date=c["start"],
                                       annual_revenue_potential=c["potential"]))
        for f in ref.fac:
            cc = CITIES[f["city"]]
            em.batch("facilities", dict(facility_id=f["id"], facility_name=f["name"], facility_type=f["type"], city=cc[0], state=cc[1],
                                        latitude=f["lat"], longitude=f["lon"], dock_doors=f["docks"], operating_hours=f["hours"]))
        for r in ref.routes:
            o, dd = CITIES[r["o"]], CITIES[r["d"]]
            em.batch("routes", dict(route_id=r["id"], origin_city=o[0], origin_state=o[1], destination_city=dd[0], destination_state=dd[1],
                                    typical_distance_miles=int(round(r["len"])), base_rate_per_mile=r["rate"], fuel_surcharge_rate=r["fsr"],
                                    typical_transit_days=r["transit_days"]))
        em.batch("diesel_prices", dict(effective_date=d, fuel_type="Diesel", price_per_gallon=round(self.diesel.national(t), 3),
                                       source=self.diesel.source))
        # driver turnover (15% per year) applied at the next assignment of that truck
        hit = np.nonzero(self.rng.random(self.N) < 0.15 / 365.0)[0]
        self.pending_term.update(int(x) for x in hit)

    # ---- checkpoint ------------------------------------------------------------------------------------------------------
    ARR = ["state", "until", "route", "prog", "rlen", "assigned", "speed", "cruise", "aggr", "lat", "lon", "heading", "odo", "fuel", "tank", "mpg",
           "idle_gph", "eng_temp", "gph", "hos_drive", "hos_duty", "hos_brk", "trip_miles", "trip_fuel", "trip_idle", "near", "amb", "r_active",
           "cargo", "setpoint", "tmax", "comp", "door_until", "fail_at", "fail_until", "fail_start", "fail_done", "breach_open", "breach_start",
           "breach_peak", "idle_at", "idle_dur", "idle_done", "idle_t0", "dev_at", "dev_len", "dev_amp", "dev_t0", "dev_done", "cong_until",
           "cong_factor", "maint_due", "drv", "trl", "phase", "seq_t", "seq_r"]

    def state_dict(self):
        return dict(arrays={k: getattr(self, k) for k in self.ARR}, trips=self.trips, maint=self.maint, incident=self.incident, ctr=dict(self.ctr),
                    delayq=list(self.delayq), t=self.t, tick=self.tick, drivers=self.drivers, spare=list(self.spare), pending=list(self.pending_term),
                    trl_info=self.trl_info, free={k: list(v) for k, v in self.free.items()}, trucks_info=self.trucks_info)

    def load_state(self, d):
        for k, v in d["arrays"].items():
            setattr(self, k, v)
        self.trips, self.maint, self.incident = d["trips"], d["maint"], d["incident"]
        self.ctr = collections.Counter(d["ctr"])
        self.delayq = d["delayq"]
        heapq.heapify(self.delayq)
        self.t, self.tick = d["t"], d["tick"]
        self.drivers, self.spare, self.pending_term = d["drivers"], collections.deque(d["spare"]), set(d["pending"])
        self.trl_info = d["trl_info"]
        self.free = {k: collections.deque(v) for k, v in d["free"].items()}
        self.trucks_info = d["trucks_info"]

    def summary(self):
        c = np.bincount(self.state, minlength=10)
        names = ["waiting", "loading", "driving", "fueling", "break", "resting", "unloading", "maint", "incident", "anom_idle"]
        return {n: int(v) for n, v in zip(names, c)}


# ----------------------------------------------------------------------------------------
# runner
# ----------------------------------------------------------------------------------------
def setup_logging(log_dir: str):
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    fh = logging.handlers.RotatingFileHandler(Path(log_dir) / "fleet.log", maxBytes=20_000_000, backupCount=5)
    fh.setFormatter(fmt)
    root.addHandler(sh)
    root.addHandler(fh)


def rss_mb():
    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 0)
    except Exception:
        return None


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


class Pacer:
    """processes a tick only when its end time has elapsed (x speedup); catches up without sleeping when behind"""

    def __init__(self, cfg: Cfg, sim_now: float, dt: int):
        self.speed, self.dt = max(cfg.speedup, 1e-6), dt
        self.wall0, self.sim0 = time.time(), sim_now
        self.catch = (self.wall0 - (sim_now + dt)) > 2 * dt

    def due(self, tick_end: float) -> bool:
        now = time.time()
        if self.catch:
            if tick_end <= now - self.dt:
                return True
            self.catch, self.wall0, self.sim0 = False, now, tick_end - self.dt
            log.info("caught up with real time - switching to live pacing")
        return tick_end <= self.sim0 + (now - self.wall0) * self.speed


class Runner:
    def __init__(self, cfg: Cfg, fresh: bool = False):
        self.cfg = cfg
        self.stop = False
        self.run_id = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
        sd = Path(cfg.state_dir)
        sd.mkdir(parents=True, exist_ok=True)
        self.s3 = S3Writer(cfg, sd / "s3_outbox")
        self.kafka = KafkaOut(cfg, sd / "kafka_spool", self.run_id)
        self.ref = Ref(cfg, np.random.default_rng(cfg.seed), sd / "route_cache")
        self.rng = np.random.default_rng(cfg.seed + 1)
        self.direct_mask = np.random.default_rng(cfg.seed + 99).random(cfg.fleet_size) < cfg.direct_s3_pct / 100.0
        self.em = Emitter(cfg, self.kafka, self.s3, self.run_id, self.direct_mask)
        self.wx = Weather(cfg, self.s3, np.random.default_rng(cfg.seed + 5))
        self.diesel = DieselPrice(cfg, self.s3)
        dt = cfg.tick_seconds
        now = time.time()
        t0 = math.floor(now / dt) * dt - cfg.backfill_days * 86400
        self.sim_start = t0
        self.ckpt_path = sd / "checkpoint.pkl.gz"
        self.fleet = Fleet(cfg, self.ref, self.wx, self.diesel, self.em, self.rng, t0)
        self.resumed = False
        if not fresh:
            self._try_resume(now)
        self.pacer = Pacer(cfg, self.fleet.t, dt)
        self.last_day = None
        self.t_log = self.t_ckpt = self.t_drain = time.time()
        self.prev = collections.Counter()
        self.errors = 0

    # -- checkpoint ----------------------------------------------------------------------------
    def save_checkpoint(self):
        d = dict(version=VERSION, sig=self.ref.sig, fleet_size=self.cfg.fleet_size, seed=self.cfg.seed, tick=self.cfg.tick_seconds,
                 fleet=self.fleet.state_dict(), rng=self.rng.bit_generator.state, em_rng=self.em.g.bit_generator.state,
                 saved_wall=time.time(), sim_start=self.sim_start, last_day=self.last_day)
        atomic_write(self.ckpt_path, gzip.compress(pickle.dumps(d, protocol=4), compresslevel=3))

    def _try_resume(self, now):
        if not self.ckpt_path.exists():
            return
        try:
            d = pickle.loads(gzip.decompress(self.ckpt_path.read_bytes()))
            if (d["sig"], d["fleet_size"], d["seed"], d["tick"]) != (self.ref.sig, self.cfg.fleet_size, self.cfg.seed, self.cfg.tick_seconds):
                log.warning("checkpoint does not match this configuration (route geometry / fleet size / seed / tick) -> starting fresh")
                return
            self.fleet.load_state(d["fleet"])
            self.rng.bit_generator.state = d["rng"]
            self.em.g.bit_generator.state = d["em_rng"]
            self.sim_start, self.last_day = d["sim_start"], d["last_day"]
            self.resumed = True
            gap = now - self.fleet.t
            log.info("RESUMED from checkpoint: sim time %s (behind real time by %.1f min)", iso(self.fleet.t), gap / 60)
            if gap > self.cfg.max_gap_hours * 3600:
                new_t = math.floor(now / self.cfg.tick_seconds) * self.cfg.tick_seconds
                log.warning("gap of %.1f h exceeds MAX_GAP_HOURS=%.1f -> jumping sim clock to %s (data gap, like a real outage)",
                            gap / 3600, self.cfg.max_gap_hours, iso(new_t))
                self.fleet.t = float(new_t)
        except Exception as e:
            log.error("could not read checkpoint (%s) -> starting fresh", e)

    # -- housekeeping ----------------------------------------------------------------------------
    def metrics(self, force=False):
        now = time.time()
        if not force and now - self.t_log < 60:
            return
        el = max(now - self.t_log, 1e-9)
        c, f = self.em.counts, self.fleet
        cur = collections.Counter(c)
        cur.update(sent=self.kafka.sent)
        rate = lambda k: round((cur[k] - self.prev[k]) / el, 1)
        done = max(f.ctr["done"], 1)
        line = dict(sim=iso(f.t), lag_min=round((now - f.t) / 60, 1), tel_kafka_s=rate("telemetry_kafka"), tel_s3_s=rate("telemetry_s3direct"),
                    reefer_kafka_s=rate("reefer_kafka"), reefer_s3_s=rate("reefer_s3direct"), trips_done=f.ctr["done"],
                    on_time_pickup=round(f.ctr["pick_ok"] / done, 3), on_time_delivery=round(f.ctr["del_ok"] / done, 3),
                    fleet_mpg=round(f.ctr["miles"] / max(f.ctr["fuel"], 1e-9), 2),
                    miles_per_truck_day=round(float((f.odo - f.odo0).sum()) / f.N / max((f.t - self.sim_start) / 86400, 1e-9), 1), states=f.summary(),
                    s3_files=self.s3.files, s3_mb=round(self.s3.bytes / 1e6, 1), s3_failed=self.s3.failed, s3_outbox=self.s3.backlog(),
                    kafka_sent=self.kafka.sent, kafka_failed=self.kafka.failed, kafka_spool_files=self.kafka.spool_backlog(),
                    weather=self.wx.source, diesel=self.diesel.source, pending_late=len(f.delayq), rss_mb=rss_mb())
        log.info("STATUS %s", json.dumps(line))
        atomic_write(Path(self.cfg.state_dir) / "heartbeat.json", json.dumps(dict(wall=now, sim=f.t, lag_min=line["lag_min"])).encode())
        self.prev, self.t_log = cur, now

    def housekeeping(self):
        now = time.time()
        self.kafka.poll()
        if now - self.t_drain > 30:
            self.s3.drain()
            self.kafka.drain_spool()
            self.t_drain = now
        if now - self.t_ckpt > self.cfg.ckpt_seconds:
            self.save_checkpoint()
            self.t_ckpt = now
        self.metrics()

    # -- main loop ----------------------------------------------------------------------------------
    def run(self):
        cfg, fl, em = self.cfg, self.fleet, self.em
        dt = cfg.tick_seconds

        def _sig(*_):
            self.stop = True
            log.info("stop requested - finishing the current tick, flushing and checkpointing ...")
        signal.signal(signal.SIGINT, _sig)
        try:
            signal.signal(signal.SIGTERM, _sig)
        except Exception:
            pass
        log.info("fleet generator %s | run %s | %d trucks | tick %ds | S3=%s | Kafka=%s | direct-to-S3 %.0f%% of trucks (%d)",
                 VERSION, self.run_id, cfg.fleet_size, dt, cfg.s3_mode, cfg.kafka_mode, cfg.direct_s3_pct, int(self.direct_mask.sum()))
        log.info("network: %d routes on %d lanes, mean %.0f miles | customers %d | facilities %d", self.ref.R, self.ref.R // 2,
                 float(self.ref.rlen.mean()), len(self.ref.cust), len(self.ref.fac))
        while not self.stop:
            te = fl.t + dt
            if cfg.until_sim_hours and te - self.sim_start > cfg.until_sim_hours * 3600:
                log.info("reached --until-sim-hours, stopping")
                break
            if not self.pacer.due(te):
                self.housekeeping()
                time.sleep(0.25)
                continue
            try:
                em.wall_now = time.time()
                self.wx.refresh(fl.t, cfg.backfill_days)
                self.diesel.refresh(fl.t)
                if day_str(te) != self.last_day:
                    self.last_day = day_str(te)
                    fl.snapshots(te)
                fl.step()
                fl.emit_streams()
                em.flush_batches(fl.t)
                em.flush_direct(fl.t)
                self.errors = 0
            except Exception:
                self.errors += 1
                log.error("tick failed (%d in a row):\n%s", self.errors, traceback.format_exc())
                if self.errors >= 20:
                    log.error("too many consecutive errors -> exiting (a supervisor/Docker will restart and resume)")
                    break
                time.sleep(1)
            self.housekeeping()
        self.shutdown()

    def shutdown(self):
        log.info("shutting down ...")
        try:
            self.em.flush_all(self.fleet.t)
            self.s3.drain(10_000)
            self.kafka.close()
            self.save_checkpoint()
            self.metrics(force=True)
        finally:
            log.info("bye. sim time reached: %s", iso(self.fleet.t))


# ----------------------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------------------
def cmd_fetch_routes(cfg: Cfg):
    sd = Path(cfg.state_dir) / "route_cache"
    sd.mkdir(parents=True, exist_ok=True)
    ref = Ref(cfg, np.random.default_rng(cfg.seed), sd)
    lanes = sorted({r["lane"] for r in ref.routes})
    log.info("fetching real road geometry for %d lanes from the OSRM public demo server (light use only; ~1 request/s)", len(lanes))
    for n, (a, b) in enumerate(lanes, 1):
        f = sd / f"{a}_{b}.json"
        if f.exists():
            continue
        url = (f"http://router.project-osrm.org/route/v1/driving/{CITIES[a][3]},{CITIES[a][2]};{CITIES[b][3]},{CITIES[b][2]}"
               "?overview=full&geometries=geojson")
        try:
            data = json.loads(_http_get(url, 60))
            co = data["routes"][0]["geometry"]["coordinates"]
            f.write_text(json.dumps({"coords": co, "distance_mi": data["routes"][0]["distance"] / 1609.344}))
            log.info("[%d/%d] %s -> %s : %.0f road miles, %d points", n, len(lanes), CITIES[a][0], CITIES[b][0],
                     data["routes"][0]["distance"] / 1609.344, len(co))
        except Exception as e:
            log.warning("[%d/%d] %s -> %s failed: %s (great-circle geometry will be used for this lane)", n, len(lanes), CITIES[a][0], CITIES[b][0], e)
        time.sleep(1.2)
    log.info("done. Restart the generator with --fresh so the new geometry is used (the old checkpoint will be ignored anyway).")


def build_cfg(a) -> Cfg:
    load_dotenv(a.env)
    cfg = Cfg.from_env()
    for k_arg, k_cfg in (("fleet", "fleet_size"), ("tick", "tick_seconds"), ("seed", "seed"), ("s3_mode", "s3_mode"), ("bucket", "s3_bucket"),
                         ("kafka_mode", "kafka_mode"), ("bootstrap", "kafka_bootstrap"), ("backfill_days", "backfill_days"),
                         ("until_sim_hours", "until_sim_hours"), ("speedup", "speedup"), ("direct_pct", "direct_s3_pct"),
                         ("out_dir", "out_dir"), ("state_dir", "state_dir"), ("log_dir", "log_dir")):
        v = getattr(a, k_arg, None)
        if v is not None:
            setattr(cfg, k_cfg, v)
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description="Continuous US trucking fleet simulator -> Kafka + S3 (raw data)")
    ap.add_argument("command", choices=["run", "init-topics", "fetch-routes"])
    ap.add_argument("--env", default=".env")
    ap.add_argument("--fleet", type=int)
    ap.add_argument("--tick", type=int)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--s3-mode", choices=["s3", "local"])
    ap.add_argument("--bucket")
    ap.add_argument("--kafka-mode", choices=["kafka", "file", "null"])
    ap.add_argument("--bootstrap")
    ap.add_argument("--backfill-days", type=float)
    ap.add_argument("--until-sim-hours", type=float)
    ap.add_argument("--speedup", type=float)
    ap.add_argument("--direct-pct", type=float)
    ap.add_argument("--out-dir")
    ap.add_argument("--state-dir")
    ap.add_argument("--log-dir")
    ap.add_argument("--fresh", action="store_true", help="ignore any checkpoint")
    a = ap.parse_args(argv)
    cfg = build_cfg(a)
    setup_logging(cfg.log_dir)
    if a.command == "fetch-routes":
        return cmd_fetch_routes(cfg)
    if a.command == "init-topics":
        KafkaOut(cfg, Path(cfg.state_dir) / "kafka_spool", "init").close()
        return
    Runner(cfg, fresh=a.fresh).run()


if __name__ == "__main__":
    main()
