"""
Parses the leading `# @Require ClassName varname [ldapFilter]` lines of a script and executes
the remaining source with the resolved services injected as globals.

Kept from the legacy convention (ycappuccino.scripts.bundles.script_interpreter, retired): one
binding per line, at the top of the script. Improved over the legacy single-line limit: several
leading @Require lines are now accepted, one per requirement.
"""

import re

_REQUIRE = re.compile(r"^#\s*@Require\s+(\S+)\s+(\S+)(?:\s+(\S+))?\s*$")


def parse_requirements(source):
    """returns ([(spec_name, variable_name, ldap_filter_or_None), ...], remaining_source)"""
    lines = source.splitlines(keepends=True)
    requirements = []
    index = 0
    for line in lines:
        match = _REQUIRE.match(line.rstrip("\n"))
        if match is None:
            break
        requirements.append(match.groups())
        index += 1
    return requirements, "".join(lines[index:])


def execute(source, resolve_service, extra_globals=None):
    """
    resolve_service(spec_name, ldap_filter) -> object, called once per leading @Require line.
    Runs the remaining source with the resolved services (and extra_globals) as globals; returns
    the script's global `result`, or "script executed" if it did not set one (legacy default).
    """
    requirements, body = parse_requirements(source)
    script_globals = dict(extra_globals or {})
    for spec_name, variable_name, ldap_filter in requirements:
        script_globals[variable_name] = resolve_service(spec_name, ldap_filter)
    exec(compile(body, "<script>", "exec"), script_globals)
    return script_globals.get("result", "script executed")
