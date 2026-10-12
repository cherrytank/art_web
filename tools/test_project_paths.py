import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import project_paths


class ProjectPathsTests(unittest.TestCase):
    def test_frozen_root_uses_exe_location_not_temp_or_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename in ("content/site.json", "templates/base.html", "static/css/styles.css"):
                path = root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            with patch.object(project_paths, "_project_root", None), patch.object(project_paths.sys, "frozen", True, create=True), patch.object(project_paths.sys, "executable", str(root / "release/manager.exe")):
                self.assertEqual(project_paths.get_project_root(), root.resolve())
            with patch.object(project_paths, "_project_root", None):
                project_paths.configure_project(root)
                self.assertEqual(project_paths.get_project_root(), root.resolve())
                with self.assertRaises(ValueError):
                    project_paths.configure_project(root / "missing")
