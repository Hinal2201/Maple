"""Run: streamlit run app.py"""
from pathlib import Path

import pandas as pd
import streamlit as st

from processing import build_snapshots, load_data, select_queue

st.set_page_config(page_title="Maple Freight - Fleet Alerts", layout="wide")
LOG = Path(__file__).with_name("action_log.csv")
PRIORITY_COLOR = {"Critical": "#d62728", "High": "#ff7f0e", "Review": "#1f77b4",
                  "Planned": "#7f7f7f", "Monitor": "#bcbd22"}


@st.cache_data
def get_models():
    return build_snapshots(load_data())


def load_log() -> pd.DataFrame:
    if LOG.exists():
        return pd.read_csv(LOG, dtype=str, keep_default_na=False)
    return pd.DataFrame(columns=["action_id", "status", "assignee", "notes"])


models = get_models()

with st.sidebar:
    st.header("Snapshot")
    snapshot = st.selectbox(
        "Data available at",
        ["updated", "original"],
        format_func=lambda value: (
            "18:48 ET - Hamilton backfill included" if value == "updated"
            else "18:00 ET - Original export only"
        ),
    )
    m = models[snapshot]
    actions, evaluated, k = m["actions"], m["evaluated"], m["kpis"]
    st.caption(
        "Late-received events are included only after their receipt time."
        if snapshot == "updated" else
        "Historical baseline; later-received Hamilton events are excluded."
    )

# ---------- Header & KPIs ----------
st.title("Maple Freight - Fleet Alert Dashboard")
st.caption(f"Data as of {m['as_of'].tz_convert('America/Toronto'):%b %d %Y %H:%M} ET")
c = st.columns(6)
c[0].metric("Raw alerts", k["raw"])
c[1].metric("Duplicates removed", k["duplicates"])
c[2].metric("Vendor HIGH", k["vendor_high"])
c[3].metric("Open actions", k["open_actions"])
c[4].metric("Critical vehicles", k["critical_vehicles"], delta=f"{k['critical']} fault actions")
c[5].metric("Excluded / resolved", k["excluded"])

# Holds are fleet-wide and intentionally unaffected by the work-queue filters.
critical = m["actions"][m["actions"].priority == "Critical"]
if not critical.empty:
    st.error(
        "DISPATCH HOLD: " + ", ".join(sorted(critical.vehicle_id.unique()))
        + " — inspect every Critical fault and explicitly clear it before dispatch. "
        + "Vendor-HIGH filters do not remove these holds."
    )
    for vehicle_id, faults in critical.groupby("vehicle_id", sort=False):
        with st.container(border=True):
            st.markdown(f"**Hold {vehicle_id} ({faults.depot.iloc[0]})**")
            for fault in faults.itertuples():
                reading = f" ({fault.value} {fault.unit})" if fault.value else ""
                received = fault.received_time.tz_convert("America/Toronto")
                st.markdown(
                    f"- **{fault.dtc_code}**{reading} — vendor {fault.vendor_severity}. "
                    f"{fault.reason} Event {fault.event_local} ET; received "
                    f"{received:%H:%M:%S} ET. Source: {', '.join(fault.source_files)} "
                    f"({fault.evidence_ids})."
                )
            st.caption(
                "Maintenance lead: verify vehicle status and inspect each fault. "
                "A repair to a different DTC does not release the vehicle."
            )

# ---------- Filters ----------
with st.sidebar:
    st.header("Filters")
    depot = st.selectbox("Depot", [""] + sorted(actions.depot.dropna().unique()), format_func=lambda x: x or "All")
    owner = st.selectbox("Owner", ["", "Maintenance lead", "Operations manager"], format_func=lambda x: x or "All")
    search = st.text_input("Search (vehicle, driver, DTC...)")
    vendor_only = st.checkbox("Only vendor-HIGH")

# ---------- Top 3 and top 10 ----------
st.subheader("Tonight's top 3")
st.caption("Fleet-wide highest-scoring distinct actions. These recommendations are independent of the filters below.")
top3 = select_queue(actions, top=3)
for rank, a in enumerate(top3.itertuples(), 1):
    color = PRIORITY_COLOR.get(a.priority, "#999")
    with st.container(border=True):
        left, right = st.columns([3, 1])
        left.markdown(
            f"**#{rank} · <span style='color:{color}'>{a.priority}</span> · "
            f"{a.vehicle_id} ({a.depot}) · {a.dtc_code} · {a.title}**",
            unsafe_allow_html=True,
        )
        left.write(f"{a.reason}  \n➡️ **{a.action}**")
        received = a.received_time.tz_convert("America/Toronto")
        right.write(f"**Owner:** {a.owner}  \n**Due:** {a.due}  \n**Vendor:** {a.vendor_severity}")
        with st.expander("Evidence and related work"):
            st.write(f"Event: {a.event_local} ET · received: {received:%H:%M:%S} ET")
            st.write(f"Source: {', '.join(a.source_files)} · alert IDs: {a.evidence_ids}")
            related = m["orders"][m["orders"].vehicle_id == a.vehicle_id]
            if related.empty:
                st.write("No work orders supplied for this vehicle.")
            else:
                st.dataframe(related[["wo_id", "status", "work_done", "technician_note"]], hide_index=True)

st.subheader("Top 10 priority actions")
top10 = select_queue(actions, depot, owner, search, vendor_only, top=10)
if vendor_only:
    st.warning("Vendor-HIGH filtering can hide Critical MEDIUM faults. The dispatch holds and fleet-wide top three above remain in effect.")
for rank, a in enumerate(top10.itertuples(), 1):
    color = PRIORITY_COLOR.get(a.priority, "#999")
    with st.container(border=True):
        l, r = st.columns([3, 1])
        l.markdown(f"**#{rank} · <span style='color:{color}'>{a.priority}</span> · "
                   f"{a.vehicle_id} ({a.depot}) · {a.title}**", unsafe_allow_html=True)
        l.write(f"{a.reason}  \n➡️ **{a.action}**")
        r.write(f"**Owner:** {a.owner}  \n**Due:** {a.due}  \n**Score:** {a.score}  \n"
                f"**Events:** {a.events} · last {a.latest_local}")
        with st.expander("Evidence"):
            st.write(f"Driver {a.driver_id} · firmware {a.device_firmware} · alert IDs: {a.evidence_ids}")

# ---------- Full dashboard ----------
tab_q, tab_all, tab_drv, tab_dq, tab_wo, tab_backfill = st.tabs(
    ["Action queue", "All alerts", "Drivers & firmware", "Data quality", "Work orders", "Hamilton backfill"])

with tab_q:
    st.caption("Update status / assignee / notes, then Save. Stored in action_log.csv.")
    queue = select_queue(actions, depot, owner, search, vendor_only, top=None)
    view = queue[["action_id", "priority", "score", "vehicle_id", "depot", "driver_id",
                  "title", "action", "owner", "due", "events", "latest_local", "age_h"]]
    view = view.merge(load_log(), on="action_id", how="left").fillna({"status": "New", "assignee": "", "notes": ""})
    edited = st.data_editor(
        view, hide_index=True, use_container_width=True,
        disabled=[c for c in view.columns if c not in ("status", "assignee", "notes")],
        column_config={"status": st.column_config.SelectboxColumn(
            "status", options=["New", "In progress", "Waiting on shop", "Done"])})
    if st.button("💾 Save updates"):
        log = load_log().set_index("action_id")
        upd = edited.set_index("action_id")[["status", "assignee", "notes"]]
        log = pd.concat([log[~log.index.isin(upd.index)], upd]).reset_index()
        log.to_csv(LOG, index=False)
        st.success("Saved.")
    st.download_button("Download queue CSV", edited.to_csv(index=False), "action_queue.csv")

with tab_all:
    f1, f2, f3 = st.columns(3)
    types = f1.multiselect("Alert type", sorted(evaluated.alert_type.unique()))
    prios = f2.multiselect("Priority", sorted(evaluated.priority.unique()))
    vehicles = f3.multiselect("Vehicle", sorted(evaluated.vehicle_id.unique()))
    df = evaluated
    if types: df = df[df.alert_type.isin(types)]
    if prios: df = df[df.priority.isin(prios)]
    if vehicles: df = df[df.vehicle_id.isin(vehicles)]
    if depot: df = df[df.depot == depot]
    st.dataframe(df[["alert_id", "source_files", "event_local", "received_time", "vehicle_id", "driver_id", "depot", "alert_type",
                     "value", "unit", "posted_limit_kmh", "dtc_code", "vendor_severity",
                     "priority", "score", "reason", "copies", "delay_h"]]
                 .sort_values("score", ascending=False),
                 hide_index=True, use_container_width=True)
    a, b = st.columns(2)
    a.bar_chart(df.alert_type.value_counts())
    b.bar_chart(df.priority.value_counts())

with tab_drv:
    st.caption("Harsh events per 1,000 km. Firmware 4.2.1 is more sensitive - compare within firmware.")
    a, b = st.columns([2, 1])
    a.dataframe(m["drivers"], hide_index=True, use_container_width=True)
    b.dataframe(m["firmware"], hide_index=True, use_container_width=True)
    b.bar_chart(m["firmware"].set_index("device_firmware")["per_1000km"])

with tab_dq:
    st.write(f"- **{k['duplicates']}** duplicate deliveries removed (vendor claims exactly-once).")
    st.write(f"- **{k['missing_limits']}** speeding events have no posted limit.")
    st.write("**Delivery delay by depot**")
    st.dataframe(m["delays"], hide_index=True, use_container_width=True)
    excluded = evaluated[evaluated.score == 0]
    st.write("**Excluded / resolved alerts**")
    st.dataframe(excluded[["alert_id", "vehicle_id", "alert_type", "event_local", "priority", "reason"]],
                 hide_index=True, use_container_width=True)

with tab_wo:
    st.dataframe(m["orders"].drop(columns=["opened", "closed"]), hide_index=True, use_container_width=True)

with tab_backfill:
    if snapshot == "original":
        st.info("This historical view predates the 18:47 ET gateway reconnection. Switch to the updated snapshot to assess the delivered batch.")
    else:
        batch = evaluated[evaluated.source_files.map(lambda files: "hamilton_backfill.csv" in files)].copy()
        st.warning(
            "Hamilton gateway unreliability is confirmed by the new-information brief. "
            "The receipt time marks when Maple Freight learned about these earlier events, not when they happened."
        )
        batch["received_local"] = batch.received_time.map(lambda value: value.tz_convert("America/Toronto").strftime("%b %d %H:%M:%S ET"))
        st.dataframe(batch[["alert_id", "vehicle_id", "driver_id", "event_local", "received_local",
                            "alert_type", "value", "unit", "posted_limit_kmh", "dtc_code",
                            "vendor_severity", "priority", "score", "reason"]]
                     .sort_values(["score", "event_time"], ascending=[False, False]),
                     hide_index=True, use_container_width=True)
        st.caption(f"{len(batch)} delivered rows · {int((batch.delay_h > 1).sum())} arrived over an hour after the event · {int((batch.priority == 'Critical').sum())} Critical fault rows")