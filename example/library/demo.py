"""
ScriptDemo: stores a script then executes it, to show ScriptService end to end.

Calls ScriptService.call(...) directly rather than through IServiceEndpoint: a secure=True
service's authorization is IServiceEndpoint's job (endpoints_service/README.md, "Autorisation"),
which needs an IAuthorization — provided by permissions_app, a separate repo not available as a
dependency of this small example. See the design spec, section 5.
"""

from ycappuccino.api.core import IActivityLogger
from ycappuccino.api.core_base import YCappuccinoComponent, YCappuccinoType
from ycappuccino.api.storage import IManager
from ycappuccino.scripts.models.script import Script
from ycappuccino.scripts.service import ScriptService


class ScriptDemo(YCappuccinoComponent):
    def __init__(
        self,
        manager: IManager,
        scripts: ScriptService,
        logger: YCappuccinoType(IActivityLogger, "(name=main)"),
    ):
        self._manager = manager
        self._scripts = scripts
        self._logger = logger

    async def start(self):
        script = Script()
        script.id("greet")
        script.name("Greet")
        script.source(
            "# @Require IActivityLogger logger\n"
            "logger.info('hello from a script')\n"
            "result = 'ok'\n"
        )
        await self._manager.up_sert_model(script)

        result = await self._scripts.call("POST", ["greet", "execute"], {}, None, None)
        self._logger.info(f"script result: {result.body}")

    async def stop(self):
        pass
