"""Text, JSON, JUnit, and SARIF report renderers."""

from __future__ import annotations

import json
from typing import Dict, List, Sequence
from xml.etree import ElementTree as ET

from .operators import OperatorInfo
from .runner import RunReport


def render_text(report: RunReport) -> str:
    lines = ["Citation Chaos run %s (%s)" % (report.run_id, report.adapter), ""]
    for result in report.results:
        marker = {"passed": "PASS", "failed": "FAIL", "error": "ERROR"}[result.status]
        lines.append("%s %s [%s]" % (marker, result.mutation_id, result.operator))
        if result.error:
            lines.append("  ! %s" % result.error.replace("\n", "\n    ").rstrip())
        for check in result.checks:
            lines.append("  %s %-31s %s" % ("ok" if check.passed else "not ok", check.name, check.details))
    lines.extend(
        [
            "",
            "Summary: %d total, %d passed, %d failed, %d errors"
            % (report.total, report.passed, report.failed, report.errors),
            "Note: these are mutation-response checks, not proof of semantic truth.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_json(report: RunReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def render_junit(report: RunReport) -> str:
    suite = ET.Element(
        "testsuite",
        {
            "name": "citation-chaos",
            "tests": str(report.total),
            "failures": str(report.failed),
            "errors": str(report.errors),
        },
    )
    properties = ET.SubElement(suite, "properties")
    ET.SubElement(properties, "property", {"name": "run_id", "value": report.run_id})
    ET.SubElement(properties, "property", {"name": "adapter", "value": report.adapter})
    for result in report.results:
        case = ET.SubElement(
            suite,
            "testcase",
            {"classname": "citation_chaos.%s" % result.operator, "name": result.mutation_id},
        )
        if result.status == "error":
            error = ET.SubElement(case, "error", {"message": result.error or "adapter error"})
            error.text = result.error or "adapter error"
        elif result.status == "failed":
            failed_checks = [check for check in result.checks if not check.passed]
            message = ", ".join(check.name for check in failed_checks)
            failure = ET.SubElement(case, "failure", {"message": "failed checks: " + message})
            failure.text = "\n".join("%s: %s" % (check.name, check.details) for check in failed_checks)
        output = ET.SubElement(case, "system-out")
        output.text = json.dumps(result.to_dict(), sort_keys=True, ensure_ascii=False)
    data = ET.tostring(suite, encoding="utf-8", xml_declaration=True)
    return data.decode("utf-8") + "\n"


def render_sarif(report: RunReport) -> str:
    rule_descriptions = {
        "abstention": "Pipeline abstains exactly when the mutation invalidates all baseline claims.",
        "unsupported-claim-removal": "Claims invalidated by the mutation are not emitted.",
        "unaffected-claim-preservation": "Claims outside the mutation impact remain unchanged.",
        "impact-localization": "Observed answer changes are limited to the expected claim set.",
        "explicit-reason": "The answer provides an explicit mutation-appropriate reason.",
        "citation-resolvability": "Every emitted citation resolves to a present source and span.",
        "adapter-error": "The pipeline adapter raised an exception or returned an invalid answer.",
    }
    rules = [
        {
            "id": rule_id,
            "name": rule_id.replace("-", "_").title().replace("_", ""),
            "shortDescription": {"text": description},
            "defaultConfiguration": {"level": "error"},
        }
        for rule_id, description in rule_descriptions.items()
    ]
    results: List[Dict[str, object]] = []
    for result in report.results:
        location = {
            "physicalLocation": {
                "artifactLocation": {"uri": "citation-chaos://mutation/%s" % result.mutation_id}
            }
        }
        if result.status == "error":
            results.append(
                {
                    "ruleId": "adapter-error",
                    "level": "error",
                    "message": {"text": result.error or "adapter error"},
                    "locations": [location],
                    "properties": {"operator": result.operator, "mutationId": result.mutation_id},
                }
            )
        else:
            for check in result.checks:
                if check.passed:
                    continue
                results.append(
                    {
                        "ruleId": check.name,
                        "level": "error",
                        "message": {"text": check.details},
                        "locations": [location],
                        "properties": {
                            "operator": result.operator,
                            "mutationId": result.mutation_id,
                            "expected": check.expected,
                            "observed": check.observed,
                        },
                    }
                )
    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Citation Chaos",
                        "rules": rules,
                    }
                },
                "invocations": [{"executionSuccessful": report.errors == 0}],
                "results": results,
                "properties": {"runId": report.run_id, "adapter": report.adapter},
            }
        ],
    }
    return json.dumps(sarif, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def render_report(report: RunReport, output_format: str) -> str:
    renderers = {
        "text": render_text,
        "json": render_json,
        "junit": render_junit,
        "sarif": render_sarif,
    }
    try:
        renderer = renderers[output_format]
    except KeyError as exc:
        raise ValueError("unknown report format: %s" % output_format) from exc
    return renderer(report)


def render_operator_list(infos: Sequence[OperatorInfo], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(
            {"schema_version": "1.0", "operators": [info.to_dict() for info in infos]},
            indent=2,
            sort_keys=True,
        ) + "\n"
    if output_format != "text":
        raise ValueError("operator list format must be text or json")
    width = max((len(info.name) for info in infos), default=0)
    lines = ["Available deterministic mutation operators:"]
    for info in infos:
        lines.append("  %-*s  %-13s  %s" % (width, info.name, info.category, info.summary))
    return "\n".join(lines) + "\n"
