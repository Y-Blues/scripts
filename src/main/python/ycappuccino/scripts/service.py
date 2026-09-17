"""
ScriptService: executes a Script's Python source as an IExposedService, mirroring the legacy
`POST /api/services/scripts/{scriptId}/execute` shape (ycappuccino.scripts.bundles.script_interpreter,
retired: see the design spec for why this is now Python, not JS/dukpy).
"""

from typing import Any

from ycappuccino.api.endpoints_service import IExposedService, ServiceResult
from ycappuccino.api.endpoints_storage import NotFound
from ycappuccino.api.storage import IManager
from ycappuccino.scripts.execution import execute


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

    async def call(
        self, method: str, extra_path: list, params: dict, body: Any, subject: dict | None
    ) -> ServiceResult:
        if method != "POST" or len(extra_path) != 2 or extra_path[1] != "execute":
            raise NotFound("not found")
        script_id = extra_path[0]
        script = await self._manager.get_one("script", script_id, subject=subject)
        if script is None:
            raise NotFound(f"unknown script {script_id}")
        result = execute(script.get_storage_model()["source"], self._resolve_service)
        return ServiceResult(body={"result": result})


def _resolve_from_framework(spec_name: str, ldap_filter: str | None) -> Any:
    from ycappuccino.core.framework import Framework  # lazy: keeps unit tests framework-free

    context = Framework.get_framework().context
    reference = context.get_service_reference(spec_name, ldap_filter)
    if reference is None:
        raise NotFound(f"no service available for {spec_name}")
    return context.get_service(reference)
