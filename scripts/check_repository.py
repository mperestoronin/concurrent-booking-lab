"""Проверка материалов без Docker и сторонних Python-библиотек."""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    cases = json.loads((ROOT / "tests/cases.json").read_text())
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)) == 17, "ID сценариев должны быть уникальны"
    assert sum(c["points"] for c in cases if c["mode"] == "base") == 60
    test_ids = []
    for source in (ROOT / "tests").glob("test_*.py"):
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "case":
                    test_ids.append(ast.literal_eval(node.args[0]))
    assert sorted(test_ids) == sorted(ids), "Каждому сценарию нужен ровно один тест"
    table = (ROOT / "docs/TEST_CASES.md").read_text()
    for case in cases:
        pattern = rf"^\| {case['id']} \|.*\| {case['points']} \|$"
        assert re.search(pattern, table, re.M), f"Не совпали баллы {case['id']}"
    markdown = [ROOT / "README.md", ROOT / "REPORT.md",
                *sorted((ROOT / "docs").glob("*.md")),
                *sorted((ROOT / "slides").glob("*.md")),
                *sorted((ROOT / ".github").rglob("*.md"))]
    for path in markdown:
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text()):
            if "://" in link or link.startswith("#"):
                continue
            target = link.split("#")[0]
            assert (path.parent / target).exists(), f"Битая ссылка {path.name}: {link}"
    assert ".instructor/" in (ROOT / ".gitignore").read_text()
    assignment = (ROOT / "docs/ASSIGNMENT.md").read_text()
    mandatory_minutes = [int(n) for n in re.findall(
        r"^\| (?:Этап [0-5]|Резерв) \| (\d+) \|", assignment, re.M)]
    optional_minutes = [int(n) for n in re.findall(
        r"^\| Дополнение [AB] \| (\d+) \|", assignment, re.M)]
    assert len(mandatory_minutes) == 7 and sum(mandatory_minutes) == 510
    assert len(optional_minutes) == 2 and sum(optional_minutes) == 150
    slides = (ROOT / "slides/SEMINAR.md").read_text()
    content = slides.split("---", 2)[2]
    assert len(re.split(r"^---\s*$", content, flags=re.M)) == 9, "Нужны 9 слайдов"
    for source in [*(ROOT / "app").rglob("*.py"), *(ROOT / "scripts").rglob("*.py"),
                   *(ROOT / "tests").rglob("*.py")]:
        ast.parse(source.read_text())
    print("Проверено: 17 ID, 60 баллов, бюджет 510+150 минут, ссылки, 9 слайдов и синтаксис Python")


if __name__ == "__main__":
    main()
