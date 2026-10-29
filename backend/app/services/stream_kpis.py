"""Stream KPIs and charts (catalog numbers, see dashboard/src/kpis/definitions.js) calculated from the Kafka rows kept
in StreamHistory, as plain functions (no Kafka, no asyncio, so they can be tested with dicts).
Window = the last `window` of event_ts, ending at the newest row kept; previous = the `window` before it.
Kafka has no trip_id / load_id: one trailer (reefer) or one truck (telemetry) inside the window counts as one trip."""
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

INTERVAL_CAP = timedelta(minutes=15)  # a row counts until the next row of its truck/trailer, at most this long
EXCESSIVE_IDLING_AFTER = timedelta(minutes=30)  # is_idling for this long (catalog KPI 34, assumption)
LITERS_PER_GALLON = 3.78541
KM_PER_MILE = 1.609344
AMBIENT_BANDS = ((50, "< 50 °F"), (70, "50-70 °F"), (90, "70-90 °F"), (float("inf"), "> 90 °F"))  # KPI 17 bands
TOP_TRAILERS = 10  # rows of excursions_by_trailer
TOP_EXCURSIONS = 8  # rows of high_risk_trips
STREAM_KPI_IDS = (10, 11, 12, 13, 14, 15, 16, 23, 29, 33, 34)
# Rows kept before the previous window, so an idle run reaching 30 min inside it has a known start (see _runs)
MARGIN = EXCESSIVE_IDLING_AFTER
CAIRO = ZoneInfo("Africa/Cairo")  # event_ts is UTC; the period text is shown in Cairo time

Track = list[tuple[datetime, dict, float]]  # one truck's or trailer's rows, oldest first: (event_ts, row, minutes)


def kept(window: timedelta) -> timedelta:
    """How much event_ts to keep (and read back from Kafka on start): the window, the previous one and MARGIN."""
    return 2 * window + MARGIN


def calculate(telemetry_rows: list[dict], reefer_rows: list[dict], window: timedelta) -> dict | None:
    """StreamKpis (schemas/stream.py): STREAM_KPI_IDS for the window vs the previous window, and the stream charts of
    the window. None when no row is kept."""
    telemetry = _tracks(telemetry_rows, "vehicle_id")
    reefer = _tracks(reefer_rows, "trailer_id")
    end = max((item[0] for track in [*telemetry.values(), *reefer.values()] for item in track), default=None)
    if end is None:
        return None
    excursions = [excursion for track in reefer.values() for excursion in _excursions(track)]
    speeding = [run[0][0] for track in telemetry.values() for run in _runs(track, "is_speeding")]
    # counted when idling reaches EXCESSIVE_IDLING_AFTER (same moment the EXCESSIVE_IDLING alert starts)
    idling = [next(time for time, _, _ in run if time - run[0][0] >= EXCESSIVE_IDLING_AFTER)
              for track in telemetry.values() for run in _runs(track, "is_idling")
              if run[-1][0] - run[0][0] >= EXCESSIVE_IDLING_AFTER]
    current = _window_kpis(end - window, end, telemetry, reefer, excursions, speeding, idling)
    previous = _window_kpis(end - 2 * window, end - window, telemetry, reefer, excursions, speeding, idling)
    minutes = round(window.total_seconds() / 60)
    return {
        "period": f"{minutes} min to {end.astimezone(CAIRO):%H:%M} vs previous {minutes} min",
        "kpis": [{"kpi_id": kpi_id, "value": current[kpi_id], "previous": previous[kpi_id]} for kpi_id in STREAM_KPI_IDS],
        "series": _series(end - window, end, telemetry, reefer, excursions),
    }


def _tracks(rows: list[dict], key: str) -> dict[str, Track]:
    """Rows grouped by `key` (vehicle_id or trailer_id), oldest first, with the minutes each row counts for: until the
    next row (at most INTERVAL_CAP). The last row counts as long as the gap before it; a lone row counts 0."""
    groups: dict[str, list[tuple[datetime, dict]]] = defaultdict(list)
    for row in rows:
        groups[row[key]].append((datetime.fromisoformat(row["event_ts"]), row))
    tracks = {}
    for name, items in groups.items():
        items.sort(key=lambda item: item[0])
        gaps = [min(after[0] - before[0], INTERVAL_CAP).total_seconds() / 60 for before, after in zip(items, items[1:])]
        gaps.append(gaps[-1] if gaps else 0.0)
        tracks[name] = [(time, row, minutes) for (time, row), minutes in zip(items, gaps)]
    return tracks


def _runs(track: Track, flag: str) -> list[Track]:
    """Runs of consecutive rows where `flag` is true. Reefer rows with null cargo_temp_f are skipped (catalog A.6).
    A run that begins with the first kept row is skipped: it began before the kept rows, so its start is unknown."""
    runs, run = [], []
    started = False  # False until the first row without the flag: rows before it belong to the skipped run
    for item in track:
        row = item[1]
        if "cargo_temp_f" in row and row["cargo_temp_f"] is None:
            continue
        if not row[flag]:
            started = True
            if run:
                runs.append(run)
                run = []
        elif started:
            run.append(item)
    return runs + [run] if run else runs


def _severity(row: dict) -> float:
    """°F outside the allowed range: above max (temp - max) or below min (min - temp)."""
    return max(row["cargo_temp_f"] - row["allowed_temp_max_f"], row["allowed_temp_min_f"] - row["cargo_temp_f"])


def _excursions(track: Track) -> list[dict]:
    """Excursions of one trailer: at least 2 consecutive is_temp_breach rows (catalog KPI 12)."""
    result = []
    for run in _runs(track, "is_temp_breach"):
        if len(run) < 2:
            continue
        peak = max((item[1] for item in run), key=_severity)
        result.append({
            "start": run[0][0],
            "trip_id": None,  # not in Kafka
            "vehicle_id": peak["vehicle_id"],
            "trailer_id": peak["trailer_id"],
            "commodity": peak["commodity_type"],
            "peak_temp_f": peak["cargo_temp_f"],
            "severity_f": round(_severity(peak), 1),
            "duration_min": round((run[-1][0] - run[0][0]).total_seconds() / 60, 1),
        })
    return result


def pct(part: float, whole: float, digits: int = 1) -> float | None:
    """part / whole in %, None when whole is 0."""
    return round(part / whole * 100, digits) if whole else None


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _window_kpis(start: datetime, end: datetime, telemetry: dict[str, Track], reefer: dict[str, Track],
                 excursions: list[dict], speeding: list[datetime], idling: list[datetime]) -> dict[int, float | None]:
    """Every STREAM_KPI_IDS value for rows with start < event_ts <= end. None when the window has no row to count."""
    def inside(time: datetime) -> bool:
        return start < time <= end

    truck_rows = [(row, minutes) for track in telemetry.values() for time, row, minutes in track if inside(time)]
    trailer_rows = [(row, minutes) for track in reefer.values() for time, row, minutes in track if inside(time)]
    valid = [row for row, _ in trailer_rows if row["cargo_temp_f"] is not None]  # null = sensor dropped (A.6)
    trailers = {row["trailer_id"] for row, _ in trailer_rows}
    window_excursions = [excursion for excursion in excursions if inside(excursion["start"])]
    failed = {row["trailer_id"] for row, _ in trailer_rows if row["is_reefer_unit_failure"]}
    km = sum(_km([row for time, row, _ in track if inside(time)]) for track in telemetry.values())
    return {
        10: pct(sum(not row["is_temp_breach"] for row in valid), len(valid)),
        11: pct(len(trailers - {excursion["trailer_id"] for excursion in window_excursions}), len(trailers)),
        12: len(window_excursions) if trailers else None,
        13: _average([excursion["duration_min"] for excursion in window_excursions]),
        14: _average([excursion["severity_f"] for excursion in window_excursions]),
        15: pct(len(failed), len(trailers)),
        16: round(sum(minutes for row, minutes in trailer_rows if row["door_open"]) / len(trailers), 1) if trailers else None,
        23: round(sum(row["fuel_gph"] * minutes / 60 for row, minutes in truck_rows
                       if row["is_idling"] and row["fuel_gph"] is not None) * LITERS_PER_GALLON, 1) if truck_rows else None,
        29: pct(sum(minutes for row, minutes in truck_rows if row["motion_status"] == "DRIVING"),
                 sum(minutes for _, minutes in truck_rows)),
        33: round(sum(map(inside, speeding)) / km * 100, 2) if km else None,
        34: sum(map(inside, idling)) if truck_rows else None,
    }


def _km(rows: list[dict]) -> float:
    """km one truck drove in its rows: odometer_mi max - min (null odometer skipped)."""
    odometers = [row["odometer_mi"] for row in rows if row["odometer_mi"] is not None]
    return (max(odometers) - min(odometers)) * KM_PER_MILE if odometers else 0.0


def _series(start: datetime, end: datetime, telemetry: dict[str, Track], reefer: dict[str, Track],
            excursions: list[dict]) -> dict:
    """Stream charts of the window, same names and shapes as the dashboard pages read them."""
    def inside(time: datetime) -> bool:
        return start < time <= end

    window_excursions = sorted((excursion for excursion in excursions if inside(excursion["start"])),
                               key=lambda excursion: excursion["duration_min"], reverse=True)
    per_trailer = defaultdict(int)
    for excursion in window_excursions:
        per_trailer[excursion["trailer_id"]] += 1
    state_minutes = defaultdict(float)
    for track in telemetry.values():
        for time, row, minutes in track:
            if inside(time) and row["motion_status"]:
                state_minutes[row["motion_status"]] += minutes
    total_minutes = sum(state_minutes.values())
    return {
        "trip_temperature": _trip_temperature(window_excursions[0], reefer, inside) if window_excursions else None,
        "excursions_by_trailer": [{"trailer_id": trailer_id, "excursions": count} for trailer_id, count in
                                  sorted(per_trailer.items(), key=lambda item: item[1], reverse=True)[:TOP_TRAILERS]],
        "excursion_rate_by_ambient": _excursion_rate_by_ambient(reefer, window_excursions, inside),
        "high_risk_trips": [{key: excursion[key] for key in ("trip_id", "vehicle_id", "trailer_id", "commodity",
                                                             "peak_temp_f", "duration_min")}
                            for excursion in window_excursions[:TOP_EXCURSIONS]],
        "time_in_state": [{"state": state, "share_pct": pct(minutes, total_minutes)} for state, minutes in
                          sorted(state_minutes.items(), key=lambda item: item[1], reverse=True)],
    }


def _trip_temperature(excursion: dict, reefer: dict[str, Track], inside) -> dict:
    """Readings of the trailer with the longest excursion in the window (Kafka has no trip_id)."""
    rows = [row for time, row, _ in reefer[excursion["trailer_id"]] if inside(time)]
    first = rows[0]
    return {
        "trip_id": None,
        "vehicle_id": excursion["vehicle_id"],
        "trailer_id": excursion["trailer_id"],
        "commodity": excursion["commodity"],
        "setpoint_f": first["setpoint_f"],
        "min_temp_f": first["allowed_temp_min_f"],
        "max_temp_f": first["allowed_temp_max_f"],
        "readings": [{key: row[key] for key in ("event_ts", "cargo_temp_f", "setpoint_f")} for row in rows],
    }


def _excursion_rate_by_ambient(reefer: dict[str, Track], excursions: list[dict], inside) -> list[dict]:
    """KPI 17 per ambient band: trailers with an excursion / trailers × 100. A trailer's band = its average
    ambient_temp_f in the window."""
    with_excursion = {excursion["trailer_id"] for excursion in excursions}
    trailers_per_band = defaultdict(list)
    for trailer_id, track in reefer.items():
        ambient = [row["ambient_temp_f"] for time, row, _ in track if inside(time) and row["ambient_temp_f"] is not None]
        if ambient:
            average = sum(ambient) / len(ambient)
            band = next(label for limit, label in AMBIENT_BANDS if average < limit)
            trailers_per_band[band].append(trailer_id)
    return [{"ambient_band": label,
             "kpi_17": pct(sum(trailer_id in with_excursion for trailer_id in trailers_per_band[label]),
                            len(trailers_per_band[label]))}
            for _, label in AMBIENT_BANDS]
