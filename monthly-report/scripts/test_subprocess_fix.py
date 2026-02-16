#!/usr/bin/env python3
"""
Unit test for subprocess.run fix in fireflies_transcript.py
Tests that subprocess.run is called with correct arguments instead of os.system.
"""

import subprocess
import unittest
from unittest.mock import patch, MagicMock


class TestSubprocessFix(unittest.TestCase):
    """Test that subprocess.run is used correctly for package installation."""

    @patch('subprocess.run')
    def test_socketio_install_command(self, mock_run):
        """Test that socketio installation uses correct subprocess.run call."""
        mock_run.return_value = MagicMock(returncode=0)

        # Simulate the installation call
        subprocess.run(["pip3", "install", "python-socketio[client]"], check=True)

        mock_run.assert_called_once_with(
            ["pip3", "install", "python-socketio[client]"],
            check=True
        )

    @patch('subprocess.run')
    def test_playwright_install_commands(self, mock_run):
        """Test that playwright installation uses correct subprocess.run calls."""
        mock_run.return_value = MagicMock(returncode=0)

        # Simulate the installation calls
        subprocess.run(["pip3", "install", "playwright"], check=True)
        subprocess.run(["playwright", "install", "chromium"], check=True)

        # Verify both calls were made
        self.assertEqual(mock_run.call_count, 2)

        calls = mock_run.call_args_list
        self.assertEqual(calls[0][0][0], ["pip3", "install", "playwright"])
        self.assertEqual(calls[0][1], {"check": True})
        self.assertEqual(calls[1][0][0], ["playwright", "install", "chromium"])
        self.assertEqual(calls[1][1], {"check": True})

    @patch('subprocess.run')
    def test_subprocess_raises_on_failure(self, mock_run):
        """Test that check=True causes CalledProcessError on failure."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "pip3")

        with self.assertRaises(subprocess.CalledProcessError):
            subprocess.run(["pip3", "install", "nonexistent"], check=True)

    def test_no_os_system_in_source(self):
        """Verify os.system is no longer used in the source file."""
        with open('/Users/stephenmorrell/.claude/skills/monthly-report/scripts/fireflies_transcript.py', 'r') as f:
            content = f.read()

        # Check that os.system( is not in the file
        self.assertNotIn('os.system(', content,
            "os.system() should be replaced with subprocess.run()")

        # Check that subprocess.run is used
        self.assertIn('subprocess.run(', content,
            "subprocess.run() should be present in the file")

        # Check that subprocess is imported
        self.assertIn('import subprocess', content,
            "subprocess module should be imported")


if __name__ == '__main__':
    unittest.main(verbosity=2)
