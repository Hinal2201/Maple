"""Alert processing for Maple Freight (Python port of dashboard/engine.js)."""
from __future__ import annotations

import re
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AS_OF = pd.Timestamp("2026-09-21T22:00:00Z")
TZ = ZoneInfo("America/Toronto")
SEVERITY = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
SEVERITY_NAME = {v: k for k, v in SEVERITY.items()}
TELEMATICS = {"device_unplugged", "camera_offline"}
KEY_COLS = ["vehicle_id", "driver_id", "alert_type", "event_time_utc",
            "value", "unit", "posted_limit_kmh", "dtc_code"]


# ---------- Load ----------
def load_data(data_dir: Path = DATA_DIR) -> dict[str, pd.DataFrame]:
    read = lambda name: pd.read_csv(data_dir / name, dtype=str, keep_default_na=False)
    alerts, vehicles = read("alerts.csv"), read("vehicles.csv")
    references, orders = read("dtc_reference.csv"), read("work_orders.csv")

    alerts["event_time"] = pd.to_datetime(alerts["event_time_utc"], utc=True)
    alerts["received_time"] = pd.to_datetime(alerts["received_time_utc"], utc=True)
    vehicles["km_driven_14d"] = vehicles["km_driven_14d"].astype(int)
    for col in ("opened_local", "closed_local"):
        orders[col.replace("_local", "")] = (
            pd.to_datetime(orders[col].replace("", None)).dt.tz_localize(TZ))
    return {"alerts": alerts, "vehicles": vehicles, "references": references, "orders": orders}


def local(ts: pd.Timestamp) -> str:
    return ts.tz_convert(TZ).strftime("%b %d %H:%M") if pd.notna(ts) else ""


# ---------- Clean ----------
def deduplicate(alerts: pd.DataFrame) -> pd.DataFrame:
    """The vendor says each alert is unique, but identical events are re-delivered with new IDs."""
    a = alerts.assign(sev_rank=alerts["vendor_severity"].map(SEVERITY))
    events = (a.groupby(KEY_COLS, sort=False)
                .agg(alert_id=("alert_id", "first"),
                     source_ids=("alert_id", list),
                     sev_rank=("sev_rank", "max"),
                     event_time=("event_time", "first"),
                     received_time=("received_time", "min"))
                .reset_index())
    events["vendor_severity"] = events["sev_rank"].map(SEVERITY_NAME)
    events["copies"] = events["source_ids"].str.len()
    return events.drop(columns="sev_rank")


# ---------- Classify ----------
def matching_repair(ev, orders: pd.DataFrame, as_of=AS_OF):
    closed = orders[(orders.vehicle_id == ev.vehicle_id) & (orders.status == "Closed")
                    & orders.closed.notna() & (orders.closed >= ev.event_time)
                    & (orders.closed <= as_of)]
    for o in closed.itertuples():
        if ev.dtc_code:
            if ev.dtc_code in f"{o.work_done} {o.technician_note}":
                return o
        elif ev.alert_type in TELEMATICS and re.search(r"harness|connector", o.work_done, re.I):
            return o
    return None


def classify(ev, orders, references, as_of=AS_OF) -> dict:
    repair = matching_repair(ev, orders, as_of)
    if repair is not None:
        return dict(score=0, priority="Closed",
                    reason=f"Addressed by {repair.wo_id}; no later matching event.")

    t = ev.alert_type
    if t == "engine_fault":
        ref = references[references.dtc_code == ev.dtc_code]
        urgency = ref.reference_urgency.iloc[0] if len(ref) else "Unknown - inspect before dispatch"
        meaning = ref.meaning.iloc[0] if len(ref) else f"Unknown engine fault {ev.dtc_code}"
        score = next((s for k, s in [("Critical", 100), ("High", 85), ("Medium", 35), ("Low", 15)]
                      if urgency.startswith(k)), 80)
        deadline = ev.event_time + pd.Timedelta(hours=24)
        overdue = as_of > deadline
        if score == 100:
            prio, action, due = "Critical", "Hold dispatch; contact driver and inspect immediately.", "Before dispatch"
        elif score >= 80:
            prio = "High"
            action = ("Inspection window elapsed - confirm vehicle status and inspect now." if overdue
                      else "Inspect within 24 h of the fault.")
            due = "Overdue - verify now" if overdue else f"By {local(deadline)} ET"
        else:
            prio, action, due = "Planned", "Schedule at next service.", "Next service"
        return dict(score=score, priority=prio, title=meaning, owner="Maintenance lead",
                    reason=f"{ev.dtc_code}: {urgency}. Vendor label is not the dispatch decision.",
                    action=action, due=due)

    if t == "maintenance_due":
        km = float(ev.value or 0)
        if km <= 0:
            return dict(score=0, priority="Not due", reason="Zero/negative km overdue.")
        return dict(score=78 if km >= 1000 else 55, priority="High", title="Service overdue",
                    reason=f"{km:,.0f} km overdue at latest reading.", owner="Maintenance lead",
                    action="Confirm service history and bring the booking forward.",
                    due="Before 06:00 dispatch")

    if t == "speeding":
        known = ev.posted_limit_kmh not in ("", "0")
        if known:
            excess = float(ev.value) - float(ev.posted_limit_kmh)
            score = 76 if excess >= 30 else 70 if excess >= 20 else 45 if excess >= 10 else 20
            return dict(score=score, priority="High" if excess >= 20 else "Review",
                        title="Repeated speeding exposure", owner="Operations manager",
                        reason=f"{ev.value} km/h in a {ev.posted_limit_kmh} km/h zone (+{excess:.0f}).",
                        action="Review route/evidence with the driver; targeted coaching.",
                        due="Before next shift")
        return dict(score=42, priority="Review", title="Speeding needs limit verification",
                    owner="Operations manager",
                    reason=f"{ev.value} km/h recorded but no posted limit; vendor HIGH unverified.",
                    action="Verify road limit before any driver-performance conversation.",
                    due="Before next shift")

    if t in TELEMATICS:
        if ev.event_time.tz_convert(TZ).hour == 23:
            return dict(score=0, priority="Expected window",
                        reason="23:00-00:00 ET nightly update window (provisional).")
        parked = orders[(orders.vehicle_id == ev.vehicle_id) & (orders.status == "Open")
                        & (orders.opened <= as_of)
                        & orders.technician_note.str.contains("not dispatched", case=False)]
        if len(parked):
            return dict(score=0, priority="Known shop work",
                        reason=f"Vehicle not dispatched per {parked.wo_id.iloc[0]}.")
        return dict(score=30, priority="Review", title="Telematics coverage gap",
                    owner="Maintenance lead", reason="Outside the nightly update window.",
                    action="Check power, harness and camera before next dispatch.",
                    due="Before next dispatch")

    if t.startswith("harsh_"):
        return dict(score=40 if float(ev.value) >= 0.6 else 10, priority="Review",
                    title="Harsh-event pattern", owner="Operations manager",
                    reason=f"{ev.value} g; compare within the same firmware only.",
                    action="Review event context with the driver.", due="Next safety review")

    return dict(score=5, priority="Monitor", title="Idling pattern", owner="Operations manager",
                reason="Lower urgency than safety/mechanical.",
                action="Review idle time at the next efficiency review.", due="Weekly review")


# ---------- Build model ----------
def build_model(data: dict, as_of=AS_OF) -> dict:
    alerts, vehicles = data["alerts"], data["vehicles"]
    orders, references = data["orders"], data["references"]

    available = alerts[(alerts.received_time <= as_of) & (alerts.event_time <= as_of)]
    unique = deduplicate(available)

    # Only the latest maintenance reading per vehicle counts
    maint = unique[unique.alert_type == "maintenance_due"]
    latest_maint = set(maint.sort_values("event_time").groupby("vehicle_id").tail(1).index)

    rows = []
    for idx, ev in unique.iterrows():
        if ev.alert_type == "maintenance_due" and idx not in latest_maint:
            d = dict(score=0, priority="Superseded", reason="A later maintenance reading exists.")
        else:
            d = classify(ev, orders, references, as_of)
        rows.append(d)
    evaluated = pd.concat([unique.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    evaluated = evaluated.merge(vehicles, on="vehicle_id", how="left")
    evaluated["event_local"] = evaluated.event_time.map(local)
    evaluated["delay_h"] = (evaluated.received_time - evaluated.event_time).dt.total_seconds() / 3600

    # Group open items into actions
    act = evaluated[evaluated.score > 0].copy()
    act["speed_kind"] = act.apply(
        lambda r: ("known" if r.posted_limit_kmh else "unknown") if r.alert_type == "speeding" else "",
        axis=1)
    act["action_id"] = act[["vehicle_id", "alert_type", "dtc_code", "speed_kind"]].agg("|".join, axis=1)

    actions = []
    for aid, g in act.groupby("action_id"):
        strongest = g.sort_values(["score", "event_time"], ascending=False).iloc[0]
        n = len(g)
        bonus = min(3, n // 3) if strongest.score < 80 else 0
        actions.append({**strongest.to_dict(), "action_id": aid, "events": n,
                        "score": strongest.score + bonus,
                        "latest_time": g.event_time.max(),
                        "vendor_high": int((g.vendor_severity == "HIGH").sum()),
                        "evidence_ids": ", ".join(sum(g.source_ids, []))})
    actions = (pd.DataFrame(actions)
                 .sort_values(["score", "latest_time", "action_id"], ascending=[False, False, True])
                 .reset_index(drop=True))
    actions["latest_local"] = actions.latest_time.map(local)
    actions["age_h"] = ((as_of - actions.latest_time).dt.total_seconds() / 3600).round(1)

    # Harsh events per 1,000 km (fair comparison)
    harsh = unique[unique.alert_type.str.startswith("harsh_")].merge(
        vehicles[["vehicle_id", "device_firmware", "assigned_driver"]], on="vehicle_id")
    drivers = (vehicles.groupby("assigned_driver")
               .agg(km=("km_driven_14d", "sum"),
                    firmware=("device_firmware", lambda s: ", ".join(sorted(set(s)))))
               .join(unique[unique.alert_type.str.startswith("harsh_")]
                     .groupby("driver_id").size().rename("harsh_events"))
               .fillna({"harsh_events": 0}))
    drivers["per_1000km"] = (drivers.harsh_events * 1000 / drivers.km).round(2)
    firmware = (vehicles.groupby("device_firmware")
                .agg(vehicles=("vehicle_id", "count"), km=("km_driven_14d", "sum"))
                .join(harsh.groupby("device_firmware").size().rename("harsh_events")))
    firmware["per_1000km"] = (firmware.harsh_events * 1000 / firmware.km).round(2)

    delays = (evaluated.groupby("depot")
              .agg(events=("alert_id", "count"),
                   delayed_over_1h=("delay_h", lambda s: int((s > 1).sum())),
                   max_delay_h=("delay_h", "max")).round(1))

    return dict(
        as_of=as_of, evaluated=evaluated, actions=actions,
        drivers=drivers.sort_values("per_1000km", ascending=False).reset_index(),
        firmware=firmware.reset_index(), delays=delays.reset_index(), orders=orders,
        kpis=dict(raw=len(available), unique=len(unique), duplicates=len(available) - len(unique),
                  vendor_high=int((available.vendor_severity == "HIGH").sum()),
                  critical=int((actions.priority == "Critical").sum()),
                  open_actions=len(actions),
                  excluded=int((evaluated.score == 0).sum()),
                  missing_limits=int(((unique.alert_type == "speeding")
                                      & (unique.posted_limit_kmh == "")).sum())))


def select_queue(actions: pd.DataFrame, depot="", owner="", search="", vendor_only=False, top=10):
    q = actions
    if depot: q = q[q.depot == depot]
    if owner: q = q[q.owner == owner]
    if vendor_only: q = q[q.vendor_high > 0]
    if search:
        hay = q[["vehicle_id", "driver_id", "title", "dtc_code", "depot"]].fillna("").agg(" ".join, axis=1)
        q = q[hay.str.lower().str.contains(search.lower(), regex=False)]
    # One card per vehicle + owner (keep the strongest)
    q = q.drop_duplicates(["vehicle_id", "owner"], keep="first")
    return q.head(top) if top else q


if __name__ == "__main__":
    m = build_model(load_data())
    print(m["kpis"])
    print(select_queue(m["actions"])[["vehicle_id", "priority", "score", "title", "due"]])