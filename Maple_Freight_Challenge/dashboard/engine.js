import Papa from 'papaparse';

export const AS_OF = '2026-09-21T22:00:00Z';
export const TIME_ZONE = 'America/Toronto';
const severityOrder = { LOW: 1, MEDIUM: 2, HIGH: 3 };
export const parseCsv = (text) => {
  const result = Papa.parse(text.trim(), { header: true, skipEmptyLines: true });
  if (result.errors.length) throw new Error(`Invalid CSV: ${result.errors[0].message}`);
  return result.data;
};
export const localDate = (time) => new Intl.DateTimeFormat('en-CA', {
  timeZone: TIME_ZONE, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
}).format(new Date(time));
export const eventKey = (row) => JSON.stringify([
  row.vehicle_id, row.driver_id, row.alert_type, row.event_time_utc,
  row.value, row.unit, row.posted_limit_kmh, row.dtc_code,
]);
export function deduplicate(rows) {
  const events = new Map();
  for (const row of rows) {
    const key = eventKey(row);
    if (!events.has(key)) events.set(key, { ...row, sourceIds: [], sourceRows: [] });
    const event = events.get(key);
    event.sourceIds.push(row.alert_id);
    event.sourceRows.push(row);
    if (severityOrder[row.vendor_severity] > severityOrder[event.vendor_severity]) event.vendor_severity = row.vendor_severity;
    if (row.received_time_utc < event.received_time_utc) event.received_time_utc = row.received_time_utc;
  }
  return [...events.values()];
}
const workTime = (value) => new Date(`${value.replace(' ', 'T')}:00-04:00`).getTime();
export function matchingRepair(event, orders, asOf = AS_OF) {
  return orders.find((order) => order.vehicle_id === event.vehicle_id && order.status === 'Closed'
    && order.closed_local && workTime(order.closed_local) >= Date.parse(event.event_time_utc)
    && workTime(order.closed_local) <= Date.parse(asOf)
    && (event.dtc_code
      ? `${order.work_done} ${order.technician_note}`.includes(event.dtc_code)
      : ['device_unplugged', 'camera_offline'].includes(event.alert_type) && /harness|connector/i.test(order.work_done)));
}
export function classify(event, { orders, references, asOf = AS_OF }) {
  const repair = matchingRepair(event, orders, asOf);
  if (repair) return { score: 0, priority: 'Closed', reason: `Addressed by ${repair.wo_id}; no later matching event in this export.`, repair };
  if (event.alert_type === 'engine_fault') {
    const reference = references.find((row) => row.dtc_code === event.dtc_code);
    const urgency = reference?.reference_urgency || 'Unknown - inspect before dispatch';
    const score = urgency.startsWith('Critical') ? 100 : urgency.startsWith('High') ? 85 : urgency.startsWith('Medium') ? 35 : urgency.startsWith('Low') ? 15 : 80;
    const deadline = Date.parse(event.event_time_utc) + 24 * 3600000;
    const overdue = Date.parse(asOf) > deadline;
    return { score, priority: score === 100 ? 'Critical' : score >= 80 ? 'High' : 'Planned',
      title: reference?.meaning || `Unknown engine fault ${event.dtc_code}`,
      reason: `${event.dtc_code}: ${urgency}. Vendor label is not the dispatch decision.`,
      action: score === 100 ? 'Hold dispatch; contact driver and inspect immediately. Confirm repair before release.' : score >= 80 ? (overdue ? 'The reference inspection window has elapsed. Confirm current fault status and inspect now if unresolved, before dispatch.' : 'Inspect within 24 hours of the event; confirm a safe vehicle before the 06:00 dispatch.') : 'Verify current fault status and schedule the reference-recommended service.',
      owner: 'Maintenance lead', due: score === 100 ? 'Before dispatch' : score >= 80 ? (overdue ? 'Overdue - verify now' : `By ${localDate(deadline)} ET`) : 'Next service' };
  }
  if (event.alert_type === 'maintenance_due') {
    if (Number(event.value) <= 0) return { score: 0, priority: 'Not due', reason: 'Zero or negative km overdue; no overdue action.' };
    return { score: Number(event.value) >= 1000 ? 78 : 55, priority: 'High', title: 'Service overdue',
      reason: `${Number(event.value).toLocaleString()} km overdue at the latest maintenance reading.`,
      action: 'Confirm service history and bring the booking forward; agree dispatch availability with the shop.', owner: 'Maintenance lead', due: 'Before 06:00 dispatch' };
  }
  if (event.alert_type === 'speeding') {
    const known = event.posted_limit_kmh !== '' && Number(event.posted_limit_kmh) > 0;
    const excess = known ? Number(event.value) - Number(event.posted_limit_kmh) : null;
    return { score: known ? excess >= 30 ? 76 : excess >= 20 ? 70 : excess >= 10 ? 45 : 20 : 42,
      priority: known && excess >= 20 ? 'High' : 'Review', title: known ? 'Repeated speeding exposure' : 'Speeding needs limit verification',
      reason: known ? `${event.value} km/h in a ${event.posted_limit_kmh} km/h zone (+${excess}).` : `${event.value} km/h recorded, but no posted limit. Vendor HIGH is unverified.`,
      action: known ? 'Review route and event evidence with the event driver; agree targeted coaching before the next shift.' : 'Verify road limit and location before making a speeding or driver-performance judgment.',
      owner: 'Operations manager', due: 'Before next shift' };
  }
  if (['device_unplugged', 'camera_offline'].includes(event.alert_type)) {
    const hour = Number(new Intl.DateTimeFormat('en-GB', { timeZone: TIME_ZONE, hour: '2-digit', hourCycle: 'h23' }).format(new Date(event.event_time_utc)));
    if (hour === 23) return { score: 0, priority: 'Expected window', reason: '23:00-00:00 Eastern update window; provisionally excluded, not proof of an update.' };
    const parked = orders.find((order) => order.vehicle_id === event.vehicle_id && order.status === 'Open'
      && workTime(order.opened_local) <= Date.parse(asOf) && /not dispatched/i.test(order.technician_note));
    if (parked) return { score: 0, priority: 'Known shop work', reason: `Vehicle not dispatched per ${parked.wo_id}; confirm availability separately.` };
    return { score: 30, priority: 'Review', title: 'Telematics coverage gap', reason: 'Outside the expected nightly update window.',
      action: 'Check power, harness and camera before next dispatch; reconcile with workshop activity.', owner: 'Maintenance lead', due: 'Before next dispatch' };
  }
  if (event.alert_type.startsWith('harsh_')) return {
    score: Number(event.value) >= 0.6 ? 40 : 10, priority: 'Review', title: 'Harsh-event pattern',
    reason: `${event.value} g recorded; firmware and driving exposure affect comparisons.`,
    action: 'Review event context with the driver; compare rates within the same firmware, not raw alert totals.', owner: 'Operations manager', due: 'Next safety review',
  };
  return { score: 5, priority: 'Monitor', title: 'Idling pattern', reason: 'Lower urgency than safety and mechanical actions.',
    action: 'Review route and idle time at the next efficiency review.', owner: 'Operations manager', due: 'Weekly review' };
}
export function buildModel({ alerts, vehicles, references, orders, asOf = AS_OF }) {
  const available = alerts.filter((row) => Date.parse(row.received_time_utc) <= Date.parse(asOf) && Date.parse(row.event_time_utc) <= Date.parse(asOf));
  const unique = deduplicate(available);
  const vehicleMap = new Map(vehicles.map((vehicle) => [vehicle.vehicle_id, vehicle]));
  const latestMaintenance = new Map();
  for (const event of unique.filter((row) => row.alert_type === 'maintenance_due')) {
    const previous = latestMaintenance.get(event.vehicle_id);
    if (!previous || event.event_time_utc > previous.event_time_utc) latestMaintenance.set(event.vehicle_id, event);
  }
  const evaluated = unique.map((event) => {
    const decision = event.alert_type === 'maintenance_due' && latestMaintenance.get(event.vehicle_id) !== event
      ? { score: 0, priority: 'Superseded', reason: 'A later maintenance reading is available.' }
      : classify(event, { orders, references, asOf });
    return { ...event, vehicle: vehicleMap.get(event.vehicle_id), ...decision };
  });
  const groups = new Map();
  for (const event of evaluated.filter((row) => row.score > 0)) {
    const key = [event.vehicle_id, event.alert_type, event.dtc_code || '', event.alert_type === 'speeding' ? (event.posted_limit_kmh ? 'known' : 'unknown') : ''].join('|');
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(event);
  }
  const actions = [...groups.entries()].map(([id, events]) => {
    const strongest = [...events].sort((first, second) => second.score - first.score || Date.parse(second.event_time_utc) - Date.parse(first.event_time_utc))[0];
    const latest = events.reduce((first, second) => first.event_time_utc > second.event_time_utc ? first : second);
    const relatedOrders = orders.filter((order) => order.vehicle_id === strongest.vehicle_id);
    return { ...strongest, id, events, count: events.length, latestTime: latest.event_time_utc, relatedOrders,
      score: strongest.score + (strongest.score < 80 ? Math.min(3, Math.floor(events.length / 3)) : 0),
      vendorHighCount: events.filter((event) => event.vendor_severity === 'HIGH').length,
      ageHours: (Date.parse(asOf) - Date.parse(latest.event_time_utc)) / 3600000 };
  }).sort((first, second) => second.score - first.score || Date.parse(second.latestTime) - Date.parse(first.latestTime) || first.id.localeCompare(second.id));
  const drivers = [...new Set(vehicles.map((vehicle) => vehicle.assigned_driver))].map((driver) => {
    const assigned = vehicles.filter((vehicle) => vehicle.assigned_driver === driver);
    const distance = assigned.reduce((total, vehicle) => total + Number(vehicle.km_driven_14d), 0);
    const events = unique.filter((row) => row.driver_id === driver && row.alert_type.startsWith('harsh_'));
    return { driver, distance, count: events.length, rate: events.length * 1000 / distance, firmware: [...new Set(assigned.map((vehicle) => vehicle.device_firmware))].join(', ') };
  }).sort((first, second) => second.rate - first.rate);
  const firmware = [...new Set(vehicles.map((vehicle) => vehicle.device_firmware))].sort().map((version) => {
    const fleet = vehicles.filter((vehicle) => vehicle.device_firmware === version);
    const ids = new Set(fleet.map((vehicle) => vehicle.vehicle_id));
    const distance = fleet.reduce((total, vehicle) => total + Number(vehicle.km_driven_14d), 0);
    const count = unique.filter((row) => ids.has(row.vehicle_id) && row.alert_type.startsWith('harsh_')).length;
    return { version, vehicles: fleet.length, count, distance, rate: count * 1000 / distance };
  });
  const delays = vehicles.reduce((result, vehicle) => {
    if (!result.some((row) => row.depot === vehicle.depot)) {
      const events = unique.filter((event) => vehicleMap.get(event.vehicle_id)?.depot === vehicle.depot);
      const hours = events.map((event) => (Date.parse(event.received_time_utc) - Date.parse(event.event_time_utc)) / 3600000);
      result.push({ depot: vehicle.depot, count: hours.length, delayed: hours.filter((value) => value > 1).length, maxHours: Math.max(0, ...hours) });
    }
    return result;
  }, []);
  return { asOf, available, unique, evaluated, actions, drivers, firmware, delays, vehicles,
    rawCount: available.length, duplicates: available.length - unique.length,
    vendorHigh: available.filter((row) => row.vendor_severity === 'HIGH').length,
    critical: actions.filter((action) => action.priority === 'Critical').length,
    missingLimits: unique.filter((row) => row.alert_type === 'speeding' && !row.posted_limit_kmh).length,
    excluded: evaluated.filter((row) => row.score === 0).length };
}
export function selectQueue(model, { depot = '', role = '', search = '', vendorOnly = false } = {}) {
  const query = search.trim().toLowerCase();
  const filtered = model.actions.filter((action) => (!depot || action.vehicle?.depot === depot)
    && (!role || action.owner === role) && (!vendorOnly || action.vendorHighCount > 0)
    && (!query || [action.vehicle_id, action.driver_id, action.title, action.dtc_code, action.vehicle?.depot].join(' ').toLowerCase().includes(query)));
  const combined = new Map();
  for (const action of filtered) {
    const key = `${action.vehicle_id}|${action.owner}`;
    if (!combined.has(key)) combined.set(key, { ...action, supportingActions: [], events: [...action.events] });
    else {
      const primary = combined.get(key);
      primary.supportingActions.push(action);
      primary.events.push(...action.events);
      if (action.latestTime > primary.latestTime) primary.latestTime = action.latestTime;
    }
  }
  return [...combined.values()].slice(0, 10);
}