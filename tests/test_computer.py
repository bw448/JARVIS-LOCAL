from __future__ import annotations

import unittest
from unittest.mock import patch

from jarvis.computer import ComputerToolError, ComputerToolService


class ComputerToolTests(unittest.TestCase):
    def test_schemas_forbid_unknown_parameters(self) -> None:
        service = ComputerToolService()
        schemas = service.schemas()

        self.assertEqual(len(schemas), 4)
        self.assertTrue(
            all(
                schema["function"]["parameters"]["additionalProperties"] is False
                for schema in schemas
            )
        )
        self.assertNotIn("shell", str(schemas).lower())
        self.assertNotIn("command", [schema["function"]["name"] for schema in schemas])

    def test_unknown_tool_and_extra_arguments_are_rejected(self) -> None:
        service = ComputerToolService()
        with self.assertRaises(ComputerToolError):
            service.propose("run_command", {"command": "whoami"})
        with self.assertRaises(ComputerToolError):
            service.propose(
                "open_application",
                {"application": "notepad", "command": "calc.exe"},
            )
        with self.assertRaises(ComputerToolError):
            service.propose("open_folder", {"folder": "C:/"})

    def test_read_only_status_executes_without_confirmation(self) -> None:
        result = ComputerToolService().propose("get_system_status", {})

        self.assertEqual(result["kind"], "result")
        self.assertIn("CPU", result["message"])

    def test_mutating_action_requires_one_time_confirmation(self) -> None:
        service = ComputerToolService()
        proposal = service.propose("open_application", {"application": "notepad"})

        self.assertEqual(proposal["kind"], "proposal")
        self.assertIn("记事本", proposal["preview"])
        with patch("jarvis.computer.sys.platform", "win32"), patch(
            "jarvis.computer.subprocess.Popen"
        ) as popen, patch.object(
            service, "_application_path", return_value="C:/Windows/System32/notepad.exe"
        ):
            result = service.resolve(proposal["proposal_id"], True)

        self.assertTrue(result["executed"])
        popen.assert_called_once()
        with self.assertRaises(ComputerToolError):
            service.resolve(proposal["proposal_id"], True)

    def test_rejection_consumes_proposal_without_execution(self) -> None:
        service = ComputerToolService()
        proposal = service.propose("lock_workstation", {})

        result = service.resolve(proposal["proposal_id"], False)

        self.assertFalse(result["executed"])
        self.assertIn("已取消", result["message"])
        with self.assertRaises(ComputerToolError):
            service.resolve(proposal["proposal_id"], False)


if __name__ == "__main__":
    unittest.main()
