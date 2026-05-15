
import os
import sys
from uuid import uuid4
from math import isclose

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
parent_dir = os.path.dirname(backend_dir)
sys.path.insert(0, backend_dir)
sys.path.insert(0, parent_dir)

from app import create_app
from backend.models.database import db
from backend.models.models import SPLMapping
from backend.utils.spl_service import spl_service


def main():
    app = create_app('default')

    keep = os.environ.get("SPL_TEST_KEEP", "").strip() in {"1", "true", "TRUE", "yes", "YES"}
    mapping_id = None

    with app.app_context():
        name = f"__spl_mapping_test__{uuid4().hex[:8]}"
        mapping = SPLMapping(
            name=name,
            description="temporary mapping for SPLMappingService.spl_to_gain",
            device_id=None,
            device_type="dry",
            distance=1.0,
            target_spl=65.0,
            digital_gain=50,
            test_frequency=1000,
            calibration_status="calibrated",
            calibration_data={
                "points": [
                    {"spl": 60.0, "gain": 10},
                    {"spl": 65.0, "gain": 50},
                    {"spl": 70.0, "gain": 100},
                ]
            },
        )
        db.session.add(mapping)
        db.session.commit()
        mapping_id = mapping.id

        print(f"Created SPLMapping: id={mapping_id}, name={name}")
        print("Calibration points (spl->gain%): 60->10, 65->50, 70->100")

        cases = [
            (60.0, 0.10),
            (65.0, 0.50),
            (70.0, 1.00),
            (62.5, 0.30),
            (55.0, 0.10),
            (75.0, 1.00),
        ]

        ok = True
        for target_spl, expected_gain in cases:
            calculated_gain = spl_service.spl_to_gain(mapping_id, target_spl)
            passed = isclose(calculated_gain, expected_gain, rel_tol=1e-6, abs_tol=1e-6)
            ok = ok and passed
            print(
                f"target_spl={target_spl:>5.1f} => gain={calculated_gain:.6f} "
                f"(expected {expected_gain:.6f}) {'OK' if passed else 'FAIL'}"
            )

        if not keep:
            db.session.delete(mapping)
            db.session.commit()
            print(f"Deleted SPLMapping: id={mapping_id}")
        else:
            print("SPL_TEST_KEEP enabled: mapping kept in DB")

        if not ok:
            raise SystemExit(1)


if __name__ == "__main__":
    main()

