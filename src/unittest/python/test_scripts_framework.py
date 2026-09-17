import asyncio
import unittest

from ycappuccino.core.framework import Framework
from ycappuccino.core.testing import TemporaryApplication, wait_until

APPLICATION = {
    "conf/application.yml": """
        name: scriptstest
        bundle_prefix:
          - ycappuccino.storage
          - ycappuccino.endpoints_service
          - ycappuccino.scripts
        layers:
          ycappuccino_storage_memory:
            active: true
        config:
          shell:
            console: false
    """,
}


class TestScriptsInFramework(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = TemporaryApplication(APPLICATION).open()
        cls.addClassCleanup(cls.app.close)
        cls.framework = Framework()
        cls.framework.init(cls.app.yml_path)
        cls.addClassCleanup(cls.framework.stop)
        wait_until(lambda: cls.framework.context.get_service_reference("ScriptService"))

    def test_service_is_published(self):
        self.assertIsNotNone(self.framework.context.get_service_reference("ScriptService"))
        self.assertIsNotNone(self.framework.context.get_service_reference("IExposedService"))

    def test_executes_a_script_stored_through_the_manager_injecting_a_real_service(self):
        from ycappuccino.scripts.models.script import Script

        manager = self.framework.context.get_service(self.framework.context.get_service_reference("IManager"))
        service = self.framework.context.get_service(self.framework.context.get_service_reference("ScriptService"))

        script = Script()
        script.id("greet")
        script.source(
            "# @Require IActivityLogger logger\n"
            "logger.info('hello from a script')\n"
            "result = 'ok'\n"
        )
        asyncio.run(manager.up_sert_model(script))

        result = asyncio.run(service.execute("greet", None))

        self.assertEqual(result, {"result": "ok"})


if __name__ == "__main__":
    unittest.main()
