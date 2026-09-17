import shutil
import unittest

from scripts_fixtures import create_manager

from ycappuccino.api.decorators import get_rpc_methods
from ycappuccino.api.endpoints_storage import NotFound
from ycappuccino.endpoints_service.endpoint import ServiceEndpoint
from ycappuccino.scripts.models.script import Script
from ycappuccino.scripts.service import ScriptService


class FakeService:
    def greet(self):
        return "hi"


class TestScriptService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.manager, directory = create_manager()
        self.addCleanup(shutil.rmtree, directory, True)

    async def _create_script(self, id, source):
        script = Script()
        script.id(id)
        script.source(source)
        await self.manager.up_sert_model(script)

    def test_name_and_secure(self):
        self.assertEqual(ScriptService.name, "scripts")
        self.assertTrue(ScriptService.secure)

    async def test_executes_a_script_and_returns_its_result(self):
        await self._create_script("sum", "result = 1 + 1\n")
        service = ScriptService(self.manager)

        result = await service.execute("sum", None)

        self.assertEqual(result, {"result": 2})

    async def test_defaults_to_script_executed_without_a_result_variable(self):
        await self._create_script("noop", "x = 1\n")
        service = ScriptService(self.manager)

        result = await service.execute("noop", None)

        self.assertEqual(result, {"result": "script executed"})

    async def test_injects_a_required_service_by_name(self):
        await self._create_script("hello", "# @Require FakeService svc\nresult = svc.greet()\n")
        service = ScriptService(self.manager, resolve_service=lambda spec, ldap: FakeService())

        result = await service.execute("hello", None)

        self.assertEqual(result, {"result": "hi"})

    async def test_unknown_script_is_not_found(self):
        service = ScriptService(self.manager)

        with self.assertRaises(NotFound):
            await service.execute("missing", None)

    def test_it_declares_a_secure_post_method_with_the_script_id_in_the_path(self):
        metadata = get_rpc_methods(ScriptService)["execute"]

        self.assertEqual((metadata["method"], metadata["path"], metadata["secure"]), ("POST", "/{script_id}/execute", True))

    async def test_post_execute_runs_the_script_of_the_path(self):
        await self._create_script("sum", "result = 1 + 1\n")
        service = ScriptService(self.manager)
        service.secure = False  # routing only: authorization is ServiceEndpoint's own tests
        endpoint = ServiceEndpoint([service], [])

        result = await endpoint.call("scripts", "POST", ["sum", "execute"], {}, None, None)

        self.assertEqual(result.body, {"result": 2})

    async def test_wrong_method_or_extra_path_is_not_found(self):
        await self._create_script("sum", "result = 1\n")
        service = ScriptService(self.manager)
        service.secure = False
        endpoint = ServiceEndpoint([service], [])

        for method, extra_path in (("GET", ["sum", "execute"]), ("POST", ["sum"])):
            with self.subTest(method=method, extra_path=extra_path):
                with self.assertRaises(NotFound):
                    await endpoint.call("scripts", method, extra_path, {}, None, None)


if __name__ == "__main__":
    unittest.main()
