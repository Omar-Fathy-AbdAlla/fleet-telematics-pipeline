// KPI catalog: ids, names, units, meanings, formulas and business actions copied from Notion_Data_Catalog.md (sections 1-4).
// The backend sends only { kpi_id, value, previous }; everything a viewer reads comes from here.
// better: 'up' = higher is good, 'down' = lower is good, null = neutral.
// question: key in QUESTIONS (why we track the KPI). action: catalog "Business action"; when missing, the group's decisions apply.

export const KPIS = {
  // A. Delivery
  1: {
    name: 'On-Time Delivery Rate', unit: '%', better: 'up', meaning: 'Share of deliveries that started within the 15-min grace period.',
    question: 'Q1', formula: 'Deliveries with on_time_flag = true / eligible deliveries × 100', action: 'Investigate low-performing lanes and customers.',
  },
  2: {
    name: 'On-Time Pickup Rate', unit: '%', better: 'up', meaning: 'Share of pickups that started within the 15-min grace period.',
    question: 'Q1', formula: 'Pickups with on_time_flag = true / eligible pickups × 100', action: 'Find loading and dispatch delays that start the trip late.',
  },
  3: {
    name: 'Average Delivery Delay', unit: 'min', better: 'down', meaning: 'Average positive delay of late deliveries (early ones excluded).',
    question: 'Q1', formula: 'Average of delay_minutes over late deliveries only (delay_minutes > 0)', action: 'Prioritize recurring delays.',
  },
  5: {
    name: 'Severe Delay Rate', unit: '%', better: 'down', meaning: 'Share of deliveries later than the severe threshold (assumption: 120 min).',
    question: 'Q1', formula: 'Deliveries delayed more than 120 min / eligible deliveries × 100',
  },
  6: {
    name: 'Destination Queue Time', unit: 'min', better: 'down', meaning: 'Wait at destination before unloading starts.',
    question: 'Q2', formula: 'Delivery actual_datetime − trips.arrival_ts', action: 'Identify facilities and cities with long waiting times (a major source of lost driver hours).',
  },
  7: {
    name: 'Dock Time', unit: 'min', better: 'down', meaning: 'Average loading/unloading time (detention_minutes).',
    question: 'Q2', formula: 'Average of delivery_events.detention_minutes (Pickup and Delivery)', action: 'Review slow facilities and negotiate detention fees.',
  },
  8: {
    name: 'Trip Duration Variance', unit: '%', better: 'down', meaning: 'Actual vs planned trip hours. Compare lanes, not absolute value.',
    question: 'Q4', formula: 'Planned = scheduled delivery − scheduled pickup; average per trip of (actual_duration_hours − planned) / planned × 100', action: 'Review inaccurate time estimates and lanes with recurring overruns.',
  },

  // B. Cold chain
  10: {
    name: 'Cold Chain Compliance (readings)', unit: '%', better: 'up', meaning: 'Share of valid reefer readings inside the allowed range.',
    question: 'Q5', formula: 'Valid readings inside the allowed range / all valid readings × 100 (null cargo_temp_f excluded)',
  },
  11: {
    name: 'Shipment Cold Chain Compliance', unit: '%', better: 'up', meaning: 'Share of refrigerated loads with no confirmed excursion.',
    question: 'Q5', formula: 'Refrigerated loads with no confirmed excursion / all refrigerated loads × 100',
  },
  12: {
    name: 'Temperature Excursions', unit: 'count', better: 'down', meaning: 'Distinct events where cargo temperature left the allowed range.',
    question: 'Q5', formula: 'Count of distinct out-of-range events (at least 2 consecutive readings outside the range)',
  },
  13: {
    name: 'Avg Excursion Duration', unit: 'min', better: 'down', meaning: 'Average minutes an excursion lasted.',
    question: 'Q5', formula: 'Average of (excursion end − excursion start)',
  },
  14: {
    name: 'Peak Excursion Severity', unit: '°F', better: 'down', meaning: 'Average peak degrees outside the allowed range.',
    question: 'Q5', formula: 'Average of the peak per excursion: temp − max allowed (above range) or min allowed − temp (below range)',
  },
  15: {
    name: 'Refrigeration Failure Rate', unit: '%', better: 'down', meaning: 'Share of reefer trips where the compressor stopped too long.',
    question: 'Q6', formula: 'Reefer trips with compressor_on = false too long while cargo_temp_f > setpoint + deadband / all reefer trips × 100',
    action: 'Identify trailers needing inspection.',
  },
  16: {
    name: 'Door-Open Exposure', unit: 'min/trip', better: 'down', meaning: 'Minutes with door open per refrigerated trip.',
    question: 'Q6', formula: 'Readings with door_open = true × reading interval / refrigerated trips', action: 'Reduce door-open time during loading and unloading.',
  },
  17: {
    name: 'Excursion Rate', unit: '%', better: 'down', meaning: 'Share of reefer trips with an excursion, by ambient temperature band.',
    question: 'Q6', formula: 'Reefer trips with an excursion / all reefer trips × 100, per ambient_temp_f band (<50, 50-70, 70-90, >90 °F)',
    action: 'Prepare for high-risk heat periods.',
  },

  // C. Fuel & cost
  19: {
    name: 'Total Fuel Spend', unit: 'USD', better: null, meaning: 'Sum of fuel card purchases (bought, not burned).',
    question: 'Q8', formula: 'Sum of fuel_purchases.total_cost',
  },
  20: {
    name: 'Fuel Cost per km', unit: 'USD/km', better: 'down', meaning: 'Fuel used by trips × average price paid per liter, divided by their km.',
    question: 'Q8', formula: 'Σ trips.fuel_liters_used × (Σ fuel_purchases.total_cost / Σ fuel_purchases.liters) / Σ trips.actual_distance_km',
  },
  21: {
    name: 'Fuel Efficiency', unit: 'L/100km', better: 'down', meaning: 'Liters per 100 km. Expected range 30-41 (= 5.8-7.8 mpg).',
    question: 'Q9', formula: 'Average of trips.average_l_per_100km', action: 'Find trucks and routes that burn more fuel than similar ones.',
  },
  22: {
    name: 'Fuel Price Variance', unit: '%', better: 'down', meaning: 'Price paid per liter vs the national diesel price of the same day (state offsets included).',
    question: 'Q10', formula: 'Average of (fuel_purchases.price_per_liter − reference) / reference × 100, reference = diesel_prices.price_per_gallon / 3.78541',
  },
  23: {
    name: 'Idle Fuel', unit: 'L', better: 'down', meaning: 'Liters burned with engine on and truck not moving.',
    question: 'Q9', formula: 'Sum of telemetry.fuel_gph × interval × 3.78541 where engine_on = true and speed_mph ≈ 0',
  },
  24: {
    name: 'Idle Time Share', unit: '%', better: 'down', meaning: 'Idle hours as a share of trip hours.',
    question: 'Q9', formula: 'trips.idle_time_hours / trips.actual_duration_hours × 100',
  },
  26: {
    name: 'Revenue per km', unit: 'USD/km', better: 'up', meaning: 'Load revenue + surcharge + accessorials per km.',
    question: 'Q11', formula: 'Σ (trips.revenue_usd + fuel_surcharge_usd + accessorial_charges_usd) / Σ trips.actual_distance_km',
  },
  27: {
    name: 'Fuel Cost % of Revenue', unit: '%', better: 'down', meaning: 'Trip fuel cost as a share of load revenue.',
    question: 'Q11', formula: 'Trip fuel cost (liters used × average price per liter) / total load revenue × 100',
  },
  28: {
    name: 'Margin Proxy per Trip', unit: 'USD', better: 'up', meaning: 'Revenue - fuel - maintenance. A proxy, not profit.',
    question: 'Q11', formula: 'Average per trip of: total load revenue − fuel cost (liters used × average price per liter) − truck maintenance cost allocated by km',
  },

  // D. Utilization & safety
  29: {
    name: 'Truck Utilization', unit: '%', better: 'up', meaning: 'Productive time share. Low by design (60 h between loads): compare trucks.',
    question: 'Q12', formula: 'Time driving, loading and unloading / total available time × 100',
  },
  30: {
    name: 'Km per Truck per Day', unit: 'km', better: 'up', meaning: 'Trip km / (fleet trucks x days).',
    question: 'Q12', formula: 'Sum of trips.actual_distance_km / truck-days (rows of fct_truck_daily in the period)',
  },
  33: {
    name: 'Speeding Events', unit: 'per 100 km', better: 'down', meaning: 'Speed above 70 mph = 113 km/h (assumption, no road limits in data).',
    question: 'Q13', formula: 'Speeding events (speed_mph > 70 for N consecutive readings) / km traveled × 100',
  },
  34: {
    name: 'Excessive Idling Events', unit: 'count', better: 'down', meaning: 'Engine on, speed ~0 for over 30 min (assumption).',
    question: 'Q13', formula: 'Count of periods with engine_on = true and speed ≈ 0 for more than 30 min (outside loading/unloading)',
    action: 'Coaching and idle-reduction policy.',
  },
  36: {
    name: 'Incident Rate', unit: 'per 1M km', better: 'down', meaning: 'Safety incidents per million km. Expected ~0.9 (= 1.4 per 1M mi).',
    question: 'Q14', formula: 'Count of safety_incidents / Σ trips.actual_distance_km × 1,000,000',
  },
  38: {
    name: 'Claim Cost', unit: 'USD', better: 'down', meaning: 'Sum of safety_incidents.claim_amount.',
    question: 'Q14', formula: 'Sum of safety_incidents.claim_amount',
  },

  // E. Maintenance
  41: {
    name: 'Total Maintenance Cost', unit: 'USD', better: 'down', meaning: 'Labor + parts cost of all maintenance orders.',
    question: 'Q15', formula: 'Sum of maintenance_records.total_cost (labor_cost + parts_cost)',
  },
  42: {
    name: 'Maintenance Downtime', unit: 'h', better: 'down', meaning: 'Total hours trucks were out of service.',
    question: 'Q15', formula: 'Sum of maintenance_records.downtime_hours',
  },
  43: {
    name: 'Orders per Truck', unit: 'orders', better: 'down', meaning: 'Maintenance orders per truck in the 30-day period (~0.66 = ~8/year expected).',
    question: 'Q15', formula: 'Count of maintenance orders / fleet trucks (distinct trucks in fct_truck_daily) in the period',
  },
  44: {
    name: 'Maintenance Cost per km', unit: 'USD/km', better: 'down', meaning: 'Maintenance cost / trip km in the same period.',
    question: 'Q8', formula: 'Σ maintenance total_cost in the period / Σ trips.actual_distance_km in the same period',
  },
  46: {
    name: 'Truck Availability', unit: '%', better: 'up', meaning: 'Share of fleet truck-days not in maintenance.',
    question: 'Q15', formula: 'Truck-days with is_in_maintenance = false / all truck-days × 100 (fct_truck_daily)',
  },

  // Platform
  54: {
    name: 'Ingestion Throughput', unit: 'events/s', better: 'up', meaning: 'Kafka messages (telemetry + reefer) received per second, last 60 min of Kafka time.',
    question: 'Outcome 7', formula: 'Stream events ingested / seconds in the window',
  },
  57: {
    name: 'Duplicate Rate', unit: '%', better: 'down', meaning: 'Kafka rows with the same vehicle_id + event_ts as a row already kept (dropped).',
    question: 'Outcome 7', formula: 'Duplicate rows / all received rows × 100',
  },
  58: {
    name: 'Rejection Rate', unit: '%', better: 'down', meaning: 'Kafka messages that are not JSON or have no valid vehicle_id / event_ts (skipped).',
    question: 'Outcome 7', formula: 'Quarantined rows / all received rows × 100',
  },
  60: {
    name: 'Data Freshness', unit: 'min', better: 'down', meaning: 'Minutes since the newest Kafka message (live stream).',
    question: 'Outcome 7', formula: 'Now − Kafka time of the newest message received',
  },
  65: {
    name: 'Warehouse Data Freshness', unit: 'min', better: 'down', meaning: 'Minutes since the last Airbyte load into Snowflake (RAW_DATA).',
    question: 'Outcome 7', formula: 'Now − newest _AIRBYTE_EXTRACTED_AT over the 13 RAW_DATA tables',
  },
}

// Why we track each KPI: the catalog's business questions (section 2) and, for platform KPIs, its primary outcome (section 1).
export const QUESTIONS = {
  Q1: 'Are we picking up and delivering on time?',
  Q2: 'Why are deliveries late?',
  Q4: 'Are routes performing as planned?',
  Q5: 'Are refrigerated loads kept within the safe temperature range?',
  Q6: 'Which trucks, trailers, routes, and conditions carry the highest cold-chain risk?',
  Q8: 'What does it cost to run the fleet?',
  Q9: 'Which trucks and routes are the least fuel-efficient?',
  Q10: 'Are fuel purchases consistent with expected prices and usage?',
  Q11: 'Are we profitable per mile?',
  Q12: 'Are we using the fleet efficiently?',
  Q13: 'Which driving behaviors create risk?',
  Q14: 'How frequent and costly are safety incidents?',
  Q15: 'Are trucks going out of service too often?',
  'Outcome 7': 'Provide reliable, timely, and traceable data for decisions.',
}

// KPI sections as numbered in the catalog (ids from..to). decisions: catalog "Business decisions enabled", used when a KPI has no own action.
export const KPI_GROUPS = [
  { title: 'A. Delivery Performance', from: 1, to: 9, decisions: 'Better dispatch planning, more realistic delivery promises, customer service priorities, and lane review.' },
  { title: 'B. Cold Chain', from: 10, to: 18, decisions: 'Equipment inspection, dock/door procedures, priority handling of high-risk loads, claims prevention.' },
  { title: 'C. Fuel & Cost', from: 19, to: 28, decisions: 'Route and driving-behavior optimization, fuel-stop policy, truck allocation, pricing review.' },
  { title: 'D. Fleet Utilization & Driver Safety', from: 29, to: 40, decisions: 'Driver coaching, truck assignment, safety program priorities.' },
  { title: 'E. Maintenance & Reliability', from: 41, to: 47, decisions: 'Preventive maintenance planning and availability management.' },
  { title: 'Data Platform & Pipeline', from: 54, to: 65, decisions: 'Check the data behind the business KPIs is trustworthy and timely before acting on it.' },
]

// Alert types with map colors. The first four are the anomaly_type values of gen_anomaly_labels;
// SPEEDING, ENGINE_OVERHEATING and LOW_FUEL are live alerts made by the backend from the stream flags.
// ROUTE_DEVIATION has no flag in the stream yet: the backend never sends it (kept for a future flag).
export const ANOMALY_TYPES = {
  EXCESSIVE_IDLING: { label: 'Excessive idling', color: '#f59e0b' },
  ROUTE_DEVIATION: { label: 'Route deviation', color: '#a855f7' },
  REEFER_UNIT_FAILURE: { label: 'Reefer unit failure', color: '#06b6d4' },
  COLD_CHAIN_BREACH: { label: 'Cold chain breach', color: '#ef4444' },
  SPEEDING: { label: 'Speeding', color: '#ec4899' },
  ENGINE_OVERHEATING: { label: 'Engine overheating', color: '#f97316' },
  LOW_FUEL: { label: 'Low fuel', color: '#3b82f6' },
}

export function formatValue(value, unit) {
  if (value == null) return '-'
  const digits = unit === 'USD/km' ? 3 : Math.abs(value) >= 100 ? 0 : 1
  return value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export const kpiLabel = (kpiId) => `${KPIS[kpiId].name} (${KPIS[kpiId].unit})`

// Series columns named kpi_<id> get their name + unit from KPIS; any other key is returned as is.
export function columnLabel(key) {
  const match = /^kpi_(\d+)$/.exec(key)
  return match ? kpiLabel(Number(match[1])) : key
}
