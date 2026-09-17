"""
ScriptService: executes a Script's Python source as an IExposedService, mirroring the legacy
`POST /api/services/scripts/{scriptId}/execute` shape (ycappuccino.scripts.bundles.script_interpreter,
retired: see the design spec for why this is now Python, not JS/dukpy).
"""

from typing import Any

from ycappuccino.api.decorators import rpc_method
from ycappuccino.api.endpoints_service import IExposedService
from ycappuccino.api.endpoints_storage import NotFound
from ycappuccino.api.storage import IManager
from ycappuccino.scripts import execution


class ScriptService(IExposedService):
    name = "scripts"
    secure = True

    def __init__(self, manager: IManager, resolve_service=None) -> None:
        self._manager = manager
        # unannotated on purpose: not a native dependency, only a seam for unit tests to inject
        # a fake resolver without a real Pelix framework (see the design spec, section 3)
        self._resolve_service = resolve_service or _resolve_from_framework

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    @rpc_method(method="POST", path="/{script_id}/execute", summary="execute a script")
    async def execute(self, script_id: str, subject: dict | None) -> dict:
        script = await self._manager.get_one("script", script_id, subject=subject)
        if script is None:
            raise NotFound(f"unknown script {script_id}")
        return {"result": execution.execute(script.get_storage_model()["source"], self._resolve_service)}


def _resolve_from_framework(spec_name: str, ldap_filter: str | None) -> Any:
    from ycappuccino.core.framework import Framework  # lazy: keeps unit tests framework-free

    context = Framework.get_framework().context
    reference = context.get_service_reference(spec_name, ldap_filter)
    if reference is None:
        raise NotFound(f"no service available for {spec_name}")
    return context.get_service(reference)
