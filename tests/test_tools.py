import unittest

from app.resources import get_resources_by_required_capability, list_available_resources
from app.tools import (
    get_available_resources,
    get_resources_by_required_capability as get_resources_by_required_capability_tool,
)


class GetAvailableResourcesTest(unittest.TestCase):
    def test_returns_only_available_resources(self) -> None:
        self.assertEqual(
            get_available_resources(),
            {
                "resources": [
                    {
                        "id": "truck-01",
                        "name": "Heavy Rescue Truck",
                        "category": "ground transport",
                        "location": "Albany Depot",
                        "status": "available",
                        "availability": True,
                        "reliability": 0.96,
                        "capacity": 1200,
                        "capacity_unit": "kg",
                        "capability_codes": ["road_transport"],
                        "synthetic_data": True,
                    },
                    {
                        "id": "drone-02",
                        "name": "High-Water Drone",
                        "category": "aerial support",
                        "location": "Airfield Hangar",
                        "status": "available",
                        "availability": True,
                        "reliability": 0.89,
                        "capacity": 2,
                        "capacity_unit": "people",
                        "capability_codes": ["flood_access"],
                        "synthetic_data": True,
                    },
                    {
                        "id": "med-team-alpha",
                        "name": "Medical Team Alpha",
                        "category": "field care",
                        "location": "North Clinic",
                        "status": "available",
                        "availability": True,
                        "reliability": 0.91,
                        "capacity": 6,
                        "capacity_unit": "patients",
                        "capability_codes": ["field_triage"],
                        "synthetic_data": True,
                    },
                    {
                        "id": "satcom-01",
                        "name": "Satellite Comms Kit",
                        "category": "communications",
                        "location": "Command Post",
                        "status": "available",
                        "availability": True,
                        "reliability": 0.86,
                        "capacity": None,
                        "capacity_unit": None,
                        "capability_codes": ["communications"],
                        "synthetic_data": True,
                    },
                ]
            },
        )

    def test_available_catalog_excludes_unavailable_resources(self) -> None:
        resources = list_available_resources()

        self.assertEqual([resource.id for resource in resources], [
            "truck-01",
            "drone-02",
            "med-team-alpha",
            "satcom-01",
        ])
        self.assertNotIn("boat-07", [resource.id for resource in resources])

    def test_tool_returns_available_resources_for_capability(self) -> None:
        self.assertEqual(
            get_resources_by_required_capability_tool("flood access"),
            {
                "required_capability": "flood access",
                "resources": [
                    {
                        "id": "drone-02",
                        "name": "High-Water Drone",
                        "category": "aerial support",
                        "location": "Airfield Hangar",
                        "status": "available",
                        "availability": True,
                        "reliability": 0.89,
                        "capacity": 2,
                        "capacity_unit": "people",
                        "capability_codes": ["flood_access"],
                        "synthetic_data": True,
                    }
                ],
            },
        )

    def test_unavailable_resources_are_excluded_from_capability_lookup(self) -> None:
        resources = get_resources_by_required_capability("flood access")

        self.assertEqual([resource.id for resource in resources], ["drone-02"])
        self.assertNotIn("boat-07", [resource.id for resource in resources])


if __name__ == "__main__":
    unittest.main()
