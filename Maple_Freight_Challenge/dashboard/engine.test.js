import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildModel, classify, deduplicate, matchingRepair, parseCsv, selectQueue } from './engine.js';

const load = (name) => parseCsv(readFileSync(new URL(`../data/${name}.csv`, import.meta.url), 'utf8'));
const input = { alerts: load('alerts'), vehicles: load('vehicles'), references: load('dtc_reference'), orders: load('work_orders') };
const model = buildModel(input);
test('all source rows reconcile and queue never exceeds ten', () => {
  assert.equal(input.alerts.length, 2370);
  assert.equal(model.rawCount + (input.alerts.length - model.rawCount), 2370);
  assert.equal(model.unique.length + model.duplicates, model.rawCount);
  assert.equal(selectQueue(model).length, 10);
  assert.ok(selectQueue(model, { role: 'Maintenance lead' }).every((row) => row.owner === 'Maintenance lead'));
});
test('different alert IDs do not prevent event deduplication', () => {
  const sample = input.alerts.find((row) => row.alert_id === 'A-858916');
  const result = deduplicate([sample, { ...sample, alert_id: 'duplicate', received_time_utc: '2026-09-08T14:31:30Z' }]);
  assert.equal(result.length, 1);
  assert.equal(result[0].sourceIds.length, 2);
});
test('V-137 oil pressure survives the unrelated overheating repair regardless of vendor label', () => {
  const fault = model.evaluated.find((row) => row.vehicle_id === 'V-137' && row.dtc_code === 'P0524');
  assert.equal(fault.priority, 'Critical');
  assert.equal(matchingRepair(fault, input.orders), undefined);
  assert.equal(selectQueue(model)[0].dtc_code, 'P0524');
});
test('matching completed repairs clear earlier faults, not later recurrences', () => {
  const event = input.alerts.find((row) => row.vehicle_id === 'V-137' && row.dtc_code === 'P0217');
  assert.ok(matchingRepair(event, input.orders));
  assert.equal(matchingRepair({ ...event, event_time_utc: '2026-09-21T20:00:00Z' }, input.orders), undefined);
});
test('missing limits stay unverified and negative maintenance is not overdue', () => {
  const context = { references: input.references, orders: [] };
  assert.equal(classify({ alert_type: 'speeding', value: '130', posted_limit_kmh: '', event_time_utc: '2026-09-21T12:00:00Z' }, context).priority, 'Review');
  assert.equal(classify({ alert_type: 'maintenance_due', value: '-50', event_time_utc: '2026-09-21T12:00:00Z' }, context).score, 0);
});
test('nightly window uses Eastern event time, not UTC or receipt time', () => {
  const context = { references: [], orders: [] };
  assert.equal(classify({ alert_type: 'camera_offline', event_time_utc: '2026-09-21T03:30:00Z' }, context).priority, 'Expected window');
  assert.equal(classify({ alert_type: 'camera_offline', event_time_utc: '2026-09-21T23:30:00Z' }, context).priority, 'Review');
});
test('only events available at snapshot can influence decisions', () => {
  const future = { ...input.alerts[0], alert_id: 'future', received_time_utc: '2026-09-22T01:00:00Z' };
  assert.equal(buildModel({ ...input, alerts: [...input.alerts, future] }).rawCount, model.rawCount);
});
test('driver comparisons use deduplicated events per distance and expose firmware', () => {
  const driver = model.drivers.find((row) => row.driver === 'D-17');
  assert.equal(driver.distance, 3650);
  assert.equal(driver.firmware, '4.2.1');
  assert.equal(driver.rate, driver.count * 1000 / 3650);
});
test('one maintenance handoff per vehicle combines overdue service and faults', () => {
  const queue = selectQueue(model);
  const service = queue.find((row) => row.vehicle_id === 'V-151');
  assert.ok(service.supportingActions.some((row) => row.alert_type === 'maintenance_due' && row.value === '2350'));
  assert.equal(queue.filter((row) => row.vehicle_id === 'V-151' && row.owner === 'Maintenance lead').length, 1);
});
test('source totals and critical vendor mismatch are reproducible', () => {
  assert.equal(model.vendorHigh, 326);
  assert.equal(model.duplicates, 134);
  assert.equal(model.unique.length, 2236);
  assert.equal(model.evaluated.find((row) => row.dtc_code === 'P0524').vendor_severity, 'MEDIUM');
  assert.equal(model.delays.find((row) => row.depot === 'Hamilton Depot').delayed, 114);
});
test('an old misfire does not get a fresh 24-hour window at export time', () => {
  const fault = model.evaluated.find((row) => row.vehicle_id === 'V-151' && row.dtc_code === 'P0300');
  assert.equal(fault.due, 'Overdue - verify now');
  const recent = model.evaluated.find((row) => row.vehicle_id === 'V-158' && row.dtc_code === 'P0300');
  assert.ok(recent.due.startsWith('By Sep 22'));
});