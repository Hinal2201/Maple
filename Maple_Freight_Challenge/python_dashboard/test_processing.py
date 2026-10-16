import unittest

from processing import build_snapshots, load_data, select_queue


class BackfillDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = build_snapshots(load_data())

    def test_original_and_updated_snapshots_have_distinct_cutoffs(self):
        original = self.models["original"]["kpis"]
        updated = self.models["updated"]["kpis"]
        self.assertEqual(original["raw"], 2370)
        self.assertEqual(updated["raw"], 2380)
        self.assertEqual(updated["unique"], 2246)
        self.assertEqual(updated["duplicates"], 134)
        self.assertEqual(updated["vendor_high"], 326)

    def test_all_critical_faults_survive_vehicle_queue_grouping(self):
        model = self.models["updated"]
        critical = model["actions"][model["actions"].priority == "Critical"]
        self.assertEqual(len(critical), 3)
        self.assertEqual(model["kpis"]["critical_vehicles"], 2)
        queue = select_queue(model["actions"], top=3)
        self.assertEqual(
            list(zip(queue.vehicle_id, queue.dtc_code)),
            [("V-108", "P0524"), ("V-137", "P0524"), ("V-108", "P0217")],
        )

    def test_late_backfill_rows_keep_source_and_separate_event_and_receipt(self):
        model = self.models["updated"]
        fault = model["evaluated"].set_index("alert_id").loc["A-707191"]
        self.assertEqual(fault.source_files, ["hamilton_backfill.csv"])
        self.assertEqual(fault.vendor_severity, "MEDIUM")
        self.assertEqual(fault.event_local, "Sep 21 15:41")
        self.assertEqual(fault.received_time.tz_convert("America/Toronto").strftime("%H:%M:%S"), "18:47:15")
        self.assertEqual(model["kpis"]["critical"], 3)

    def test_new_speeding_evidence_preserves_missing_limit_uncertainty(self):
        model = self.models["updated"]
        evaluated = model["evaluated"].set_index("alert_id")
        self.assertEqual(evaluated.loc["A-499391", "priority"], "High")
        self.assertIn("+44", evaluated.loc["A-499391", "reason"])
        self.assertEqual(evaluated.loc["A-403125", "priority"], "Review")
        self.assertEqual(model["kpis"]["missing_limits"], 84)

    def test_hamilton_delivery_lag_updates_without_rewriting_original(self):
        original = self.models["original"]["delays"].set_index("depot").loc["Hamilton Depot"]
        updated = self.models["updated"]["delays"].set_index("depot").loc["Hamilton Depot"]
        self.assertEqual((original.events, original.delayed_over_1h), (587, 114))
        self.assertEqual((updated.events, updated.delayed_over_1h), (597, 124))


if __name__ == "__main__":
    unittest.main()