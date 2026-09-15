import unittest

from ycappuccino.scripts.execution import execute, parse_requirements


class TestParseRequirements(unittest.TestCase):

    def test_no_requirement(self):
        requirements, body = parse_requirements("result = 1\n")

        self.assertEqual(requirements, [])
        self.assertEqual(body, "result = 1\n")

    def test_single_requirement_without_filter(self):
        requirements, body = parse_requirements("# @Require IActivityLogger logger\nresult = 1\n")

        self.assertEqual(requirements, [("IActivityLogger", "logger", None)])
        self.assertEqual(body, "result = 1\n")

    def test_requirement_with_an_ldap_filter(self):
        requirements, _ = parse_requirements("# @Require IActivityLogger logger (name=main)\n")

        self.assertEqual(requirements, [("IActivityLogger", "logger", "(name=main)")])

    def test_several_leading_requirements(self):
        source = "# @Require IActivityLogger logger\n# @Require IManager manager\nresult = 1\n"

        requirements, body = parse_requirements(source)

        self.assertEqual([requirement[1] for requirement in requirements], ["logger", "manager"])
        self.assertEqual(body, "result = 1\n")

    def test_a_require_line_only_counts_at_the_top(self):
        source = "result = 1\n# @Require IManager manager\n"

        requirements, body = parse_requirements(source)

        self.assertEqual(requirements, [])
        self.assertEqual(body, source)


class TestExecute(unittest.TestCase):

    def test_returns_the_result_global(self):
        value = execute("result = 1 + 1\n", resolve_service=lambda *_: None)

        self.assertEqual(value, 2)

    def test_defaults_to_script_executed_without_a_result(self):
        value = execute("x = 1\n", resolve_service=lambda *_: None)

        self.assertEqual(value, "script executed")

    def test_injects_the_required_service_under_its_variable_name(self):
        resolved = []

        def resolve_service(spec_name, ldap_filter):
            resolved.append((spec_name, ldap_filter))
            return {"called": True}

        value = execute("# @Require IActivityLogger logger\nresult = logger['called']\n", resolve_service)

        self.assertEqual(value, True)
        self.assertEqual(resolved, [("IActivityLogger", None)])


if __name__ == "__main__":
    unittest.main()
