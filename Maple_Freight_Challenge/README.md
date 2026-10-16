# Maple Freight: Fleet Alert Triage

## How to run it

Requires Python 3.9 or newer.

From the repository root:

```powershell
python -m pip install -r python_dashboard/requirements.txt
streamlit run python_dashboard/app.py
```

To run the processing model without the dashboard:

```powershell
cd python_dashboard
python processing.py
```

## Tonight's top 3 for Maple Freight

These are the three highest-scoring distinct alert actions after considering `hamilton_backfill.csv`, with data evaluated through Sep 21, 2026, 18:48 ET. All three are Critical engine faults; hold the affected vehicles from dispatch until inspected.

1. **Item:** V-108, P0524 oil pressure too low (alert A-707191, event 15:41 ET). **Why it matters:** The DTC reference says stop the vehicle immediately; low oil pressure can cause engine damage. **Evidence from the data:** Critical DTC P0524 in the Hamilton backfill. **Next action (who, by when):** Maintenance lead: contact the driver and inspect immediately, before dispatch.
2. **Item:** V-137, P0524 oil pressure too low (alert A-784686, event 14:32 ET). **Why it matters:** The same Critical stop-vehicle guidance applies. **Evidence from the data:** P0524 is already present in the original alert export; the backfill repeats this event. **Next action (who, by when):** Maintenance lead: confirm vehicle status and inspect immediately, before dispatch.
3. **Item:** V-108, P0217 engine coolant over-temperature (alert A-120811, event 12:05 ET). **Why it matters:** The DTC reference warns of engine damage and directs that the vehicle be stopped. **Evidence from the data:** A separate Critical P0217 fault in the Hamilton backfill, on the same vehicle as the P0524 fault above. **Next action (who, by when):** Maintenance lead: contact the driver and inspect the cooling system immediately, before dispatch. Do not treat the P0524 inspection as resolving P0217 without checking both faults.

## What I built, and for whom

A Streamlit fleet-alert dashboard for dispatch and maintenance leads. It turns raw vendor alerts into prioritized actions, shows supporting evidence and related work orders, and provides filters, a work queue, and data-quality and firmware views. The action queue can record an assignee, status, and notes.

## Assumptions I made

- Alert timestamps are UTC; recommendations and displayed event times use Eastern Time.
- The backfill should be included by moving the analysis cutoff to 18:48 ET on Sep 21, 2026, just after its 18:47 ET receipt time.
- DTC reference urgency takes precedence over the vendor severity label when deciding dispatch urgency.
- A vehicle with a Critical stop-vehicle fault remains out of dispatch until maintenance verifies and clears the condition.

## What I deliberately did NOT do (and why)

- I did not infer that either V-108 fault was repaired or safe to dispatch; the provided work orders do not show a later matching repair.
- I did not treat the repeated V-137 event in the backfill as a new distinct alert.
- I did not infer driver fault from alerts alone.

## How I checked it's correct

- Ran `python processing.py` to check the existing model and queue.
- Compared the backfill records against the alert export and DTC reference, then recalculated the queue at 22:48 UTC so the 22:47 UTC backfill deliveries were eligible.
- Confirmed the model ranks P0524 and P0217 as Critical and assigns both the action “Hold dispatch; contact driver and inspect immediately.”
- The existing dashboard's default cutoff is 22:00 UTC, and its queue keeps one card per vehicle and owner. Therefore this README's backfill-informed recommendations are not yet reflected in the dashboard automatically, and the queue can hide V-108's second distinct fault.

## AI use

- **Tools I used:** GitHub Copilot and the project's Python/pandas processing model.
- **What AI did for me:** Compared the backfill with the existing alert logic and summarized the highest-priority actions.
- **One thing AI got wrong or incomplete, and how I caught it:** An initial top-three queue view hid V-108's second Critical fault because the dashboard keeps one card per vehicle and owner. I checked the distinct alert actions and included both V-108 DTCs.
- **Link to / export of my AI session:** No session export or share link is included with this project.

## If I had two more days

- Integrate the Hamilton backfill into the dashboard's input data and make the analysis cutoff explicit and configurable.
- Change the queue so separate Critical faults on one vehicle remain visible, while still grouping genuinely related repeat events.
- Add regression tests for delayed deliveries, repeated alert IDs, DTC urgency, and multiple active faults on one vehicle.