"""
The example of README.md ("Tester avec scripts"), kept runnable.
"""

import shutil
import unittest

from scripts_fixtures import create_manager

from ycappuccino.scripts.models.script import Script
from ycappuccino.scripts.service import ScriptService


class TestGreetScript(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.manager, directory = create_manager()
        self.addCleanup(shutil.rmtree, directory, True)

    async def test_script_sets_result(self):
        manager = self.manager
        script = Script()
        script.id("greet")
        script.source("result = 1 + 1\n")
        await manager.up_sert_model(script)

        service = ScriptService(manager)
        result = await service.execute("greet", None)

        self.assertEqual(result, {"result": 2})


if __name__ == "__main__":
    unittest.main()
