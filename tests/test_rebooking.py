import unittest

from adapt.agents.rebooking import build_rebooking_plan


class RebookingPlanTest(unittest.TestCase):
    def test_build_rebooking_plan_includes_required_steps(self):
        plan = build_rebooking_plan(
            origin="ORD",
            destination="LAX",
            depart="2026-09-04",
            adults=2,
            reason="cancelled outbound leg",
        )

        self.assertEqual(plan["reason"], "cancelled outbound leg")
        self.assertIn("atlas-flight auth status --json", plan["steps"][0]["command"])
        self.assertIn("atlas-flight search", plan["steps"][1]["command"])
        self.assertIn("--seat-policy", plan["steps"][3]["command"])


if __name__ == "__main__":
    unittest.main()
