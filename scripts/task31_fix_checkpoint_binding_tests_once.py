from pathlib import Path

path = Path("tests/unit/test_protocol_v3_pipeline_final_checkpoint.py")
text = path.read_text(encoding="utf-8")
old = '''        with pytest.raises(
            checkpointing.PipelineFinalCheckpointError,
            match="Task-13 transaction uses another",
        ):
'''
new = '''        with pytest.raises(
            checkpointing.PipelineFinalCheckpointError,
            match="another registration or claim",
        ):
'''
if text.count(old) != 1:
    raise SystemExit("source-binding expectation replacement mismatch")
text = text.replace(old, new)
anchor = '''def test_registration_or_claim_receipt_mismatch_is_blocked(
'''
addition = '''def test_valid_alternate_task13_transaction_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, registration, claim, _, receipt = _built(tmp_path, monkeypatch)
    monkeypatch.setattr(task13, "COMMIT", "b" * 40)
    alternate = task13.build_state(tmp_path / "alternate_transaction", monkeypatch)
    with pytest.raises(
        checkpointing.PipelineFinalCheckpointError,
        match="Task-13 transaction uses another run fingerprint",
    ):
        checkpointing.commit_pipeline_final_checkpoint(
            receipt,
            registration=registration,
            claim=claim,
            identity=alternate["identity"],
            pre_run_manifest=alternate["manifest"],
            seed_state=alternate["seed"],
            budget_usage=alternate["budget"],
            stop_state=alternate["stop"],
            repository_root=alternate["repo"],
            trial_ledger_root=alternate["ledger_root"],
            owner_id="task31-alternate-transaction",
        )


'''
if text.count(anchor) != 1:
    raise SystemExit("alternate transaction test insertion anchor mismatch")
path.write_text(text.replace(anchor, addition + anchor), encoding="utf-8")
