import { readFileSync } from 'node:fs';
import { buildModel, parseCsv, selectQueue } from './engine.js';
const load = (name) => parseCsv(readFileSync(new URL(`../data/${name}.csv`, import.meta.url), 'utf8'));
const model = buildModel({ alerts: load('alerts'), vehicles: load('vehicles'), references: load('dtc_reference'), orders: load('work_orders') });
console.log(JSON.stringify({ raw: model.rawCount, unique: model.unique.length, duplicates: model.duplicates, high: model.vendorHigh,
  critical: model.critical, missingLimits: model.missingLimits, excluded: model.excluded,
  top10: selectQueue(model).map(({ vehicle_id, dtc_code, vendor_severity, title, count, score, latestTime, reason }) => ({ vehicle_id, dtc_code, vendor_severity, title, count, score, latestTime, reason })),
  firmware: model.firmware, drivers: model.drivers.slice(0, 8), delays: model.delays,
  criticalEvents: model.evaluated.filter((row) => row.priority === 'Critical'),
}, null, 2));