import base64
import subprocess
import sys
import unittest
from pathlib import Path

from py_vapid import Vapid


class VapidKeyGeneratorTests(unittest.TestCase):
    def test_generated_values_are_compatible_with_web_push(self):
        root = Path(__file__).parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / "generate_vapid_keys.py")],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        values = dict(
            line.split("=", 1)
            for line in result.stdout.splitlines()
            if line.startswith("VAPID_")
        )
        public = base64.urlsafe_b64decode(values["VAPID_PUBLIC_KEY"] + "==")
        self.assertEqual(len(public), 65)
        self.assertEqual(public[0], 4)
        self.assertIsNotNone(Vapid.from_string(values["VAPID_PRIVATE_KEY"]).private_key)


if __name__ == "__main__":
    unittest.main()
