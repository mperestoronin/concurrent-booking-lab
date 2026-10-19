"""Единый раннер: не скрывает падения starter и не начисляет баллы за skip."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


class Results:
    def __init__(self, cases, modes):
        self.cases = {case["id"]: case for case in cases}
        self.modes = modes
        self.nodes = {}
        self.reports = {}
        self.infrastructure_errors = []

    def pytest_collection_modifyitems(self, config, items):
        selected, deselected = [], []
        for item in items:
            marker = item.get_closest_marker("case")
            if not marker or marker.args[0] not in self.cases:
                raise pytest.UsageError(f"Неизвестный сценарий: {item.nodeid}")
            case_id = marker.args[0]
            if case_id in self.nodes.values():
                raise pytest.UsageError(f"ID сценария повторён: {case_id}")
            self.nodes[item.nodeid] = case_id
            if self.cases[case_id]["mode"] in self.modes:
                selected.append(item)
            else:
                deselected.append(item)
        if deselected:
            config.hook.pytest_deselected(items=deselected)
        items[:] = selected

    def pytest_collectreport(self, report):
        if report.failed:
            self.infrastructure_errors.append(str(report.longrepr))

    def pytest_runtest_logreport(self, report):
        case_id = self.nodes.get(report.nodeid)
        if case_id:
            self.reports.setdefault(case_id, []).append(report)

    def rows(self):
        rows = []
        for case_id, case in self.cases.items():
            reports = self.reports.get(case_id, [])
            passed = (any(r.when == "call" and r.passed for r in reports)
                      and all(r.passed for r in reports)
                      and {r.when for r in reports} == {"setup", "call", "teardown"})
            problems = [str(r.longrepr) for r in reports if not r.passed]
            reason = "Проверка пройдена" if passed else (problems[0] if problems else "Сценарий не выполнен")
            rows.append(dict(case, passed=passed, earned=case["points"] if passed else 0,
                             reason=reason))
        return rows


def main():
    parser = argparse.ArgumentParser(description="Проверки учебного бронирования")
    parser.add_argument("--mode", choices=["smoke", "base", "expert"], default="smoke")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "tests/cases.json").read_text())
    assert sum(c["points"] for c in manifest if c["mode"] == "base") == 60
    modes = {"smoke"} if args.mode == "smoke" else {"smoke", "base"}
    if args.mode == "expert":
        modes.add("expert")
    plugin = Results(manifest, modes)
    files = ["tests/test_smoke.py"]
    if args.mode != "smoke":
        files.append("tests/test_booking.py")
    # Режим задаётся manifest, имена функций не определяют принадлежность к base/expert.
    code = pytest.main([*files, "-q", "--tb=short"], plugins=[plugin])
    rows = [row for row in plugin.rows() if row["mode"] in modes]
    earned = sum(row["earned"] for row in rows)
    maximum = sum(row["points"] for row in rows)
    result = {"mode": args.mode, "timestamp": datetime.now(timezone.utc).isoformat(),
              "earned": earned, "maximum": maximum, "cases": rows,
              "infrastructure_errors": plugin.infrastructure_errors,
              "passed": code == 0 and all(r["passed"] for r in rows)}
    output = ROOT / "reports"
    output.mkdir(exist_ok=True)
    (output / f"{args.mode}-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    lines = [f"# Результаты: {args.mode}", "", f"Функциональные баллы: {earned}/{maximum}", ""]
    for row in rows:
        label = "ПРОЙДЕН" if row["passed"] else "НЕ ПРОЙДЕН"
        line = f'{row["id"]}: {label}, {row["earned"]}/{row["points"]}. {row["title"]}'
        if not row["passed"]:
            details = row["reason"].splitlines()
            brief = next((part.strip() for part in details if part.startswith("E ")),
                         details[-1] if details else "Сценарий не выполнен")
            line += f". Причина: {brief[:240]}"
        print(line)
        lines.append(f"- {line}")
        if not row["passed"]:
            lines.extend(["", "```text", row["reason"], "```", ""])
    (output / f"{args.mode}-results.md").write_text("\n".join(lines) + "\n")
    print(f"Функциональные баллы: {earned}/{maximum}. Видео и отчёт оцениваются отдельно.")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
