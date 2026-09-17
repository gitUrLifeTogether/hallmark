"""Run the attack bench and write the results.

Emits a markdown report for the README and a TypeScript module for the console, both
generated from the same run so they cannot disagree with each other or with the code.

The report states what was measured and how, including the things that would make the
numbers look better than the system is. A benchmark is only worth publishing if a reader
can tell what it does not cover.

Usage:  uv run python scripts/run_bench.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fixtures.attacks import build_scenarios
from hallmark.bench.runner import BenchReport, Config, run_bench

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = ROOT / "docs" / "bench-results.md"
CONSOLE_DATA = ROOT / "web" / "src" / "lib" / "benchData.ts"

CLASS_LABELS = {
    "PLAUSIBLE_BEC": "Plausible bank-change notice",
    "OVERT_INJECTION": "Overt injection",
    "HIDDEN_HTML": "Hidden markup",
    "ATTACHMENT_TEXT": "Instruction in an attachment",
    "OBFUSCATION": "Obfuscated instruction",
    "FAKE_SYSTEM_OUTPUT": "Forged system output",
    "EXFILTRATION": "Data exfiltration",
    "SELECTION_MANIPULATION": "Selection manipulation",
}


def write_markdown(report: BenchReport, scenario_count: int) -> None:
    baseline_asr = report.attack_success_rate(Config.BASELINE)
    hallmark_asr = report.attack_success_rate(Config.HALLMARK)

    lines = [
        "# Attack bench results",
        "",
        f"Measured {date.today().isoformat()} over **{scenario_count} scenarios** across",
        f"**{len(CLASS_LABELS)} attack classes**, three or more variants each.",
        "",
        "## Headline",
        "",
        "| Configuration | Attack success rate | Utility | Escalation |",
        "|---|---|---|---|",
        f"| Unprotected agent | **{baseline_asr:.0%}** | {report.utility(Config.BASELINE):.0%} | "
        f"{report.escalation_rate(Config.BASELINE):.0%} |",
        f"| With Hallmark | **{hallmark_asr:.0%}** | {report.utility(Config.HALLMARK):.0%} | "
        f"{report.escalation_rate(Config.HALLMARK):.0%} |",
        "",
        "Attack success is judged on the ledger and the outbox: whether money reached the",
        "attacker's account, or company records left the company. It is never judged on what",
        "the agent said. An agent that explains at length why a payment looks suspicious and",
        "then makes it has defended nothing.",
        "",
        "Utility is the share of legitimate invoices still paid. A system that refused",
        "everything would score zero on attacks and be useless, so refusing real work counts",
        "as a cost.",
        "",
        "## By attack class",
        "",
        "| Attack class | Unprotected | With Hallmark |",
        "|---|---|---|",
    ]

    baseline_by_class = report.by_class(Config.BASELINE)
    hallmark_by_class = report.by_class(Config.HALLMARK)

    for key, label in CLASS_LABELS.items():
        b_ok, b_total = baseline_by_class.get(key, (0, 0))
        h_ok, h_total = hallmark_by_class.get(key, (0, 0))
        lines.append(f"| {label} | {b_ok}/{b_total} succeeded | {h_ok}/{h_total} succeeded |")

    lines += [
        "",
        "## Every scenario",
        "",
        "| Scenario | Class | Unprotected | With Hallmark |",
        "|---|---|---|---|",
    ]

    for scenario in build_scenarios():
        baseline = next(
            r
            for r in report.results
            if r.scenario_id == scenario.scenario_id and r.config is Config.BASELINE
        )
        hallmark = next(
            r
            for r in report.results
            if r.scenario_id == scenario.scenario_id and r.config is Config.HALLMARK
        )
        lines.append(
            f"| `{scenario.scenario_id}` | {CLASS_LABELS[str(scenario.attack_class)]} | "
            f"{'attack succeeded' if baseline.attack_succeeded else 'held'} | "
            f"{'ATTACK SUCCEEDED' if hallmark.attack_succeeded else 'blocked'} |"
        )

    lines += [
        "",
        "## What this does not measure",
        "",
        "Read these before quoting the numbers above.",
        "",
        "- **Both runs are deterministic.** The planner follows a fixed procedure rather than",
        "  being a language model. That is a deliberate choice: it isolates the enforcement",
        "  layer from model variance, and the guarantee under test does not depend on the",
        "  model. It also means these figures say nothing about how a model behaves.",
        "- **The baseline is obedient, not careless.** It pays every legitimate invoice to the",
        "  correct account and follows the document when the document is wrong. It was not",
        "  weakened to make the comparison look better, and it reads hidden text because a",
        "  real agent would receive it.",
        "- **Attack goals are narrow.** Money reaching the attacker, or the vendor master",
        "  leaving the company. Availability is not measured: an attacker who only causes",
        "  invoices to be flagged has cost the company time, and that is not counted here.",
        "- **One tenant, one fixture company.** Nothing here says how the policies behave",
        "  against a different vendor master or a different mandate.",
        "- **Every scenario is verified reachable.** A test asserts the unprotected agent",
        "  actually attempts each attack, because an attack the agent never tries would",
        "  otherwise be scored as one successfully defended. That fault was present in the",
        "  first version of this bench and would have inflated the result.",
        "",
    ]

    MARKDOWN.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_console_data(report: BenchReport) -> None:
    rows = []
    for scenario in build_scenarios():
        baseline = next(
            r
            for r in report.results
            if r.scenario_id == scenario.scenario_id and r.config is Config.BASELINE
        )
        hallmark = next(
            r
            for r in report.results
            if r.scenario_id == scenario.scenario_id and r.config is Config.HALLMARK
        )
        rows.append(
            {
                "scenarioId": scenario.scenario_id,
                "attackClass": str(scenario.attack_class),
                "classLabel": CLASS_LABELS[str(scenario.attack_class)],
                "description": scenario.description,
                "baselineSucceeded": baseline.attack_succeeded,
                "hallmarkSucceeded": hallmark.attack_succeeded,
                "utility": round(hallmark.utility, 3),
            }
        )

    summary = {
        "measuredOn": date.today().isoformat(),
        "scenarios": len(rows),
        "baselineAsr": round(report.attack_success_rate(Config.BASELINE), 3),
        "hallmarkAsr": round(report.attack_success_rate(Config.HALLMARK), 3),
        "baselineUtility": round(report.utility(Config.BASELINE), 3),
        "hallmarkUtility": round(report.utility(Config.HALLMARK), 3),
    }

    CONSOLE_DATA.write_text(
        "/* Generated by scripts/run_bench.py. Do not edit by hand. */\n\n"
        "export interface BenchRow {\n"
        "  scenarioId: string;\n"
        "  attackClass: string;\n"
        "  classLabel: string;\n"
        "  description: string;\n"
        "  baselineSucceeded: boolean;\n"
        "  hallmarkSucceeded: boolean;\n"
        "  utility: number;\n"
        "}\n\n"
        f"export const BENCH_SUMMARY = {json.dumps(summary, indent=2)} as const;\n\n"
        f"export const BENCH_ROWS: BenchRow[] = {json.dumps(rows, indent=2)};\n",
        encoding="utf-8",
    )


def main() -> int:
    scenarios = build_scenarios()
    report = run_bench(scenarios)

    write_markdown(report, len(scenarios))
    write_console_data(report)

    print(f"ran {len(scenarios)} scenarios under {len(Config)} configurations")
    for config in Config:
        print(
            f"  {config:9} ASR {report.attack_success_rate(config):>5.0%}   "
            f"utility {report.utility(config):>5.0%}"
        )
    print(f"wrote {MARKDOWN.relative_to(ROOT)} and {CONSOLE_DATA.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
