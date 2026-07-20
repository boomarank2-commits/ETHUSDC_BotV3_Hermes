from __future__ import annotations

from pathlib import Path


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{label} replacement mismatch: {old[:120]!r}")
    return text.replace(old, new)


state_path = Path("src/ethusdc_bot/ui/protocol_v3_operator_state.py")
state = state_path.read_text(encoding="utf-8")
state = replace_exact(
    state,
    "PROTOCOL_V3_DONE_TASKS: Final = 29",
    "PROTOCOL_V3_DONE_TASKS: Final = 30",
    "operator-state done count",
)
state = replace_exact(
    state,
    '            "active_task": 30,\n            "active_task_status": "IN_PROGRESS",',
    '            "active_task": 31,\n            "active_task_status": "NOT_STARTED",',
    "operator-state active task",
)
state_path.write_text(state, encoding="utf-8")


test_path = Path("tests/unit/test_protocol_v3_operator_state.py")
test = test_path.read_text(encoding="utf-8")
test = replace_exact(
    test,
    '''    assert state["task_progress"] == {
        "done_tasks": 29,
        "total_tasks": 33,
        "progress_pct": 87.88,
        "active_task": 30,
        "active_task_status": "IN_PROGRESS",
    }
''',
    '''    assert state["task_progress"] == {
        "done_tasks": 30,
        "total_tasks": 33,
        "progress_pct": 90.91,
        "active_task": 31,
        "active_task_status": "NOT_STARTED",
    }
''',
    "operator-state progress test",
)
test_path.write_text(test, encoding="utf-8")


Path("handoff/PROTOCOL_V3_TASK_30_2026-07-20.md").write_text(
    Path("scripts/task30_handoff_content.md").read_text(encoding="utf-8"),
    encoding="utf-8",
)
Path("handoff/CURRENT_STATUS.md").write_text(
    Path("scripts/task30_current_status_content.md").read_text(encoding="utf-8"),
    encoding="utf-8",
)
Path("handoff/NEXT_ACTION.md").write_text(
    Path("scripts/task31_next_action_content.md").read_text(encoding="utf-8"),
    encoding="utf-8",
)


docs_path = Path("docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md")
docs = docs_path.read_text(encoding="utf-8")
docs = replace_exact(
    docs,
    "Status: Protocol-v3-Vertragsgeneration 3.0.0 aktiv; Umsetzung 29/33 abgeschlossen",
    "Status: Protocol-v3-Vertragsgeneration 3.0.0 aktiv; Umsetzung 30/33 abgeschlossen",
    "docs/41 header",
)
docs = replace_exact(
    docs,
    '''### Aufgabe 30 – UI und Bedienzustände vollständig anschließen

**Status:** `NOT_STARTED`

Origins, Folds, Fortschritt, Safety, Ergebnisbedeutung und manuelle Challenger-Aktion werden korrekt angezeigt; keine vorzeitige Outer-PnL, Paper/Testtrade/Live/Orders bleiben gesperrt.
''',
    '''### Aufgabe 30 – UI und Bedienzustände vollständig anschließen

**Status:** `DONE_100`

Das bestehende Operator-Dashboard zeigt genau einen fail-closed Protocol-v3-Zustand. Origins, Folds, Cycles, Kandidatenfortschritt, aktueller Rechenschritt, Drei-Markt-Watermark, Monatsrefit, Research-Challenger, Finalfenster und kanonischer Shadow sind semantisch getrennt.

**Abnahme:**

- Task-28-/29-/13-Evidenz wird nur typisiert und transitiv validiert in die read-only UI-Bridge übernommen; rohe JSON-, Bool- oder Dateifund-Claims können keinen Button aktivieren.
- Manueller Start verlangt aktuelle geschlossene Drei-Markt-Daten, passende Pipelinegeneration, gültiges Task-28-Fenster, Exchange-Info-Parität und einen öffentlichen checkpointfähigen Backend-Worker.
- Resume verlangt bitgleichen State, Checkpoint-Receipt, Ledger-Head und dieselbe Generation. Uncheckpointed In-Memory-State ist nicht resume-fähig.
- Der Task-29-Controller bleibt asynchron, kooperativ stoppbar, orderfrei und strikt von kanonischer Adoption getrennt.
- Restart, Refresh und wiederholtes Öffnen verändern keine Research-, Signal-, Fill-, Ledger-, Report- oder Checkpointidentität.
- Historisches Prozess-OOS, aktueller Refit, späteres Finalfenster und kanonischer Shadow besitzen getrennte sichtbare Lebenszykluszustände.
- Outer-PnL bleibt bis zu einem vollständig publizierten Ergebnis verborgen. Task 27 bis 29 bleiben `NOT_FRESH`, `diagnostic_only`, nicht statistisch unterstützt, nicht adoptionfähig und nicht final.
- Paper, Testtrade, Live, Orders, private Endpunkte, API-Keys, `active_config.json`, kanonische Adoption und Botstart bleiben sichtbar und technisch gesperrt.

**Bericht:** `handoff/PROTOCOL_V3_TASK_30_2026-07-20.md`
''',
    "docs/41 task30 block",
)
docs = replace_exact(
    docs,
    '''Protocol v3: Aufgabe 29/33 – Orderfreier Research-Challenger-Shadow – DONE_100
Gesamt: 29/33 DONE_100 = 87,88 %''',
    '''Protocol v3: Aufgabe 29/33 – Orderfreier Research-Challenger-Shadow – DONE_100
Protocol v3: Aufgabe 30/33 – UI und Bedienzustände vollständig anschließen – DONE_100
Gesamt: 30/33 DONE_100 = 90,91 %''',
    "docs/41 progress",
)
docs_path.write_text(docs, encoding="utf-8")
