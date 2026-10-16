# Maple Freight: Fleet Alert Triage

Streamlit decision-support dashboard for the operations manager and maintenance lead. The default view includes the late Hamilton batch; the original 18:00 snapshot remains available for comparison.

## How to run it

Requires Python 3.9 or newer. From the repository root:

```powershell
python -m pip install -r python_dashboard/requirements.txt
streamlit run python_dashboard/app.py
```

Open the local URL printed by Streamlit, normally http://localhost:8501. To run the updated model in a terminal:

```powershell
cd python_dashboard
python processing.py
```

Run regression tests from the repository root:

```powershell
python -m unittest discover -s python_dashboard -v
```

No API keys, external services or hosting are required. The backfill working copy is included at [data/hamilton_backfill.csv](data/hamilton_backfill.csv); the separately delivered source file remains unchanged.

## Tonight's top 3 for Maple Freight

Updated snapshot: **September 21, 2026, 18:48 Eastern**. These are three distinct DTC actions; all are Critical, and they involve **two vehicles**. Do not delay one hold because it is ranked below another.

1. **Item:** V-108, P0524 low oil pressure (A-707191; 88 kPa). **Why it matters:** The reference says stop the vehicle immediately. **Evidence:** Vendor marked MEDIUM. Event at **15:41 ET**, received at **18:47:15 ET**, over three hours later. Work order WO-5512 addressed P0171 in 2026-09-09, not P0524. **Next action (who, by when):** Maintenance lead and operations contact the driver now, establish current location and condition, and hold dispatch until qualified inspection and explicit release.
2. **Item:** V-137, P0524 low oil pressure (A-784686; 96 kPa). **Why it matters:** The reference says stop immediately. **Evidence:** Vendor marked MEDIUM. Event at **14:32 ET**. WO-5540 cleared P0217, a different code, at **07:40 ET**, before this P0524 event. The Hamilton backfill does **not** repeat this V-137 alert. **Next action (who, by when):** Maintenance lead confirms vehicle status and inspects before dispatch; do not use the sensor repair to clear P0524.
3. **Item:** V-108, P0217 engine coolant over-temperature (A-120811; 107 C). **Why it matters:** The reference says stop the vehicle because of engine-damage risk. **Evidence:** Vendor marked MEDIUM. Event at **12:05 ET**, received at **18:47:00 ET**, over six hours later. The same vehicle also has P0524 above; the two codes need separate inspection. **Next action (who, by when):** Maintenance lead inspects the cooling system before dispatch and documents explicit clearance for this DTC as well as P0524.

**Still urgent, now fourth:** V-158 has vendor-HIGH P0300 (A-468820, September 21 at 17:09:01 ET). WO-5543 is Open and booked for September 22 first thing. Confirm the appointment and replacement vehicle before the 06:00 dispatch. Its reference inspection deadline is September 22 at 17:09 ET. V-151 also remains unresolved: HIGH P0300, 2,350 km overdue, and service only Scheduled for October 5. It is not cleared by dropping below the top three.

## What changed after the new information

The new-information brief confirms Hamilton's cellular gateway was unreliable and reconnected at **18:47 ET**, delivering ten held alerts. The last arrived at **18:47:27 ET**. The dashboard now defaults to an **18:48 ET** snapshot and preserves **18:00 ET** as a selectable historical baseline. Both event and receipt timestamps are shown so a late alert is not misrepresented as a new driving event.

| Measure | Original 18:00 ET | Updated 18:48 ET |
| --- | ---: | ---: |
| Available source rows | 2,370 | 2,380 |
| Distinct event signatures | 2,236 | 2,246 |
| Duplicate-signature rows | 134 | 134 |
| Vendor-HIGH rows | 326 | 326 |
| Vendor-HIGH engine-fault rows | 41 | 41 |
| Critical fault actions | 1 | 3 |
| Vehicles with Critical holds | 1 | 2 |
| Hamilton events delayed over one hour | 114 / 587 | 124 / 597 |
| Speeding rows missing posted limit | 83 | 84 |

All ten backfill rows are vendor LOW or MEDIUM. Consequently, filtering to vendor-HIGH misses both new Critical faults on V-108. The page keeps dispatch holds and the fleet-wide top three visible independently of those filters. V-126 also has a new 104 km/h event in a 60 zone (+44 km/h), which merits an operations review. V-131's 131 km/h event has no posted limit, so its violation remains unverified.

**Disposition of the ten delivered rows:**

| Alert | Vehicle | Event ET | Vendor | Assessment |
| --- | --- | --- | --- | --- |
| A-120811 | V-108 | 12:05:00 | MEDIUM | Critical P0217; dispatch hold |
| A-483047 | V-135 | 12:15:26 | MEDIUM | Harsh braking 0.43 g; review context |
| A-857240 | V-108 | 13:09:06 | LOW | Idling 57 min; lower-priority efficiency review |
| A-341855 | V-135 | 14:15:51 | LOW | 87 in an 80 zone (+7 km/h); review |
| A-403125 | V-131 | 14:53:15 | LOW | 131 km/h; limit absent, verify before judgment |
| A-707191 | V-108 | 15:41:00 | MEDIUM | Critical P0524; dispatch hold |
| A-499391 | V-126 | 16:22:00 | MEDIUM | 104 in a 60 zone (+44 km/h); high-priority review |
| A-444816 | V-124 | 16:38:09 | MEDIUM | P0171; inspect at next service per reference |
| A-463536 | V-113 | 16:50:39 | LOW | Harsh acceleration 0.43 g; review context |
| A-508652 | V-145 | 17:21:16 | LOW | Idling 80 min; lower-priority efficiency review |

The updated snapshot also shows **124 of 597 Hamilton events** over one hour late. The longest delay remains **29.97 hours** across the complete dataset; the longest delay in this new batch is **6 h 42 min**. Gateway unreliability is confirmed, but one reconnection does not prove sustained recovery. Verify vehicle status and arrange an alternate check-in with the vendor until recovery is established.

## What I built, and for whom

- **Snapshot selector:** Switch between the original export and the backfill-aware view.
- **Fleet-wide dispatch holds:** Keeps every unresolved Critical DTC visible regardless of queue filters. Counts Critical vehicles separately from fault actions.
- **Top three:** Three distinct highest-priority actions, even when two faults belong to the same vehicle.
- **Top-ten queue:** Search/filter by depot, owner, vehicle, driver, fault and vendor severity. Keep separate Critical DTCs visible. Edit status, assignee and notes; save locally to `python_dashboard/action_log.csv`.
- **All alerts:** Inspect priority, vendor label, evidence, duplicate count, source file and receipt time.
- **Drivers & firmware / Data quality / Work orders:** Compare exposure-adjusted signals, delayed delivery and shop history.
- **Hamilton backfill:** Inspect all ten new rows and compare event time, receipt time, vendor severity and independent assessment.
- **CSV export:** Download the current work queue.

Saving a note does not notify another user, create a work order, clear a fault or authorize dispatch. This is a local prototype, not a shared dispatch system.

## Assumptions I made

- Scenario time, not today's date, controls the model. Original cutoff is `2026-09-21T22:00:00Z`; updated cutoff is `2026-09-21T22:48:00Z`, just after the last `22:47:27Z` backfill receipt. Events must be both recorded and received by the selected cutoff.
- Alert timestamps are UTC. Display and recommendations use `America/Toronto`; supplied September shop timestamps are Eastern daylight time.
- Identical vehicle, driver, type, event timestamp, value/unit, posted limit and DTC form one event signature despite different IDs. Keep all source IDs, highest vendor severity and earliest receipt. Exact signatures can theoretically collide; this is a documented assumption.
- A repair clears an engine alert only if a Closed work order names the same DTC and closes after the alert but before cutoff. Open/Scheduled work is not a repair; a repair to another DTC does not clear it.
- Historical unresolved faults need current-status verification; they do not prove a vehicle's present condition. A DTC's inspection deadline starts at event time, not the later delivery time.
- During 23:00-00:00 Eastern, device/camera alerts are provisionally excluded under the vendor's update-window claim. No update log proves each one benign. This exclusion never applies to engine faults.
- Use only the latest maintenance reading per vehicle. A nonpositive overdue distance is not overdue. Missing speed limits stay unverified.
- DTC reference urgency outranks vendor severity. Critical=100, High=85, unknown DTC=80, service >=1,000 km overdue=78, speeding excess >=30/20/10 km/h=76/70/45, smaller overdue service=55, unknown limit=42, harsh >=0.6 g=40, Medium DTC=35, off-window device=30, lower speeding=20, Low DTC=15, smaller harsh=10 and idling=5. Other DTCs use reference urgency. Noncritical recurrence can add up to three points. These are transparent prototype weights, not calibrated probabilities, legal limits or approved company policy.
- Queue ranking is by score, recency and stable action ID. Repeat events with the same DTC can group; separate Critical DTCs cannot. The top three are fleet-wide and independent of filters. Filters are work views, not a global daily-capacity allocator.
- D-17 has 73 distinct harsh events / 3,650 assigned-vehicle km = 20.0 per 1,000 km; D-53 is close at 19.9 on the same firmware. Updated rates for firmware 4.1.8/4.2.1/4.3.0 are 5.98/17.96/5.48 per 1,000 km. These are associations; routes, loads, class, firmware sensitivity and exposure confound driver comparisons.

## What I deliberately did NOT do (and why)

- No LLM classifier: the small supplied DTC reference and explicit deterministic rules are easier to audit.
- No automatic repair inference, vehicle release, road-limit inference or driver discipline recommendation: evidence is insufficient and these require a qualified person.
- No live vendor/dispatch integration, authentication, shared assignments or real notifications: none were supplied.
- No assumption that gateway reconnection proves durable recovery: verify it with the vendor and fleet.
- No commit, publication or submission to an external service.

## How I checked it's correct

- `python -m unittest discover -s python_dashboard -v`: five focused tests verify original/updated cutoffs and counts, three distinct Critical actions and their exact top-three order, separate event/receipt times and source provenance, missing-limit handling, V-126's +44 km/h, and Hamilton's 114/587 to 124/597 change.
- `python python_dashboard/processing.py`: recomputes the updated snapshot and prints its metrics and top actions.
- The Streamlit page was opened at `http://localhost:8501`. Its rendered state showed the 18:48 snapshot, both hold vehicles, all three distinct Critical actions in order, and correct source files plus UTC-to-Eastern receipt times. The app restarted after the processing helper was corrected.
- `python -m py_compile` passed for the app, processing module and tests. The running Streamlit environment has pandas and Streamlit installed. VS Code's selected analysis interpreter currently does not resolve those two imports; select the environment used to run Streamlit or install `python_dashboard/requirements.txt` into the selected environment to clear those editor-only diagnostics.
- No production build is required for this Python/Streamlit app. The integrated browser confirmed the rendered updated page and data. The snapshot selector's native pointer interaction and an automated click-through of every widget were not completed.

The app uses only supplied synthetic data. It is decision support, not a certified diagnostic or safety system. A qualified human must confirm vehicle status, inspect and authorize release.

## AI use

- **Tools I used:** GitHub Copilot in VS Code, Python/pandas, Streamlit, Node/pdf-parse to read the two supplied briefs, unit tests and the integrated browser.
- **What AI did for me:** Inspect data and briefs, implement and test deterministic prioritization, update the live page and documentation.
- **One thing AI got wrong or incomplete, and how I caught it:** The initial queue grouped one card per vehicle/owner, hiding V-108's second Critical DTC. Distinct Critical DTCs are now separate actions, while both remain under one vehicle hold. I also corrected an earlier README claim: the delivered backfill does not repeat V-137's event.
- **Prompt record:** [PROMPT_HISTORY.md](PROMPT_HISTORY.md) transcribes the visible user prompts in order. It is not a full AI transcript; no full transcript export is included.

## If I had two more days

- Add shared assignment and an audited global daily capacity limit.
- Make backfill ingestion idempotent and monitor durable gateway recovery/data freshness.
- Integrate verified trip exposure, shop completion and dispatch release evidence.
- Add automated Streamlit/browser accessibility checks and DST-boundary tests.