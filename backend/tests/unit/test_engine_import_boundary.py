import subprocess
import sys
import unittest
from pathlib import Path


class EngineImportBoundaryTests(unittest.TestCase):
    def test_public_facades_import_without_django(self):
        code = """
import engines.allocation
import engines.delinquency
import engines.deposit
import engines.maintenance.priority
import engines.maintenance.technician_matching
import engines.meter
import engines.money
import engines.proration
import engines.tariff
import sys
assert "django" not in sys.modules
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
