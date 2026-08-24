import unittest

from adapt import atlas_tools


class AtlasToolsTest(unittest.TestCase):
    def test_extract_payload_keeps_nested_data(self):
        payload = {
            "schema_version": "1.0",
            "status": "OK",
            "code": "OK",
            "data": {"ticketing_available": True, "booking_id": "BK123"},
        }

        self.assertEqual(atlas_tools.extract_payload(payload), payload["data"])

    def test_build_order_command_uses_explicit_seat_policy(self):
        command = atlas_tools.build_order_command(
            "BK123",
            "passengers-stdin",
            seat_policy="continue-without-seat",
        )

        self.assertIn("atlas-flight", command)
        self.assertIn("order", command)
        self.assertIn("create", command)
        self.assertIn("--seat-policy", command)
        self.assertIn("continue-without-seat", command)


if __name__ == "__main__":
    unittest.main()
