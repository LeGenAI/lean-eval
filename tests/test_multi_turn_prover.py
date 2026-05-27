"""Unit tests for the multi-turn proof evaluator.

These tests stub both the model call and the Lean verifier so the loop
logic can be exercised without external dependencies.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import List

import pytest

from src.evaluation.dataset import EvalRow
from src.evaluation.lean_verifier import (
    LeanMessage,
    LeanVerifyResult,
    contains_sorry,
    extract_lean_block,
    parse_lean_messages,
)
from src.evaluation.model_runner import ModelConfig
from src.evaluation.multi_turn_prover import (
    ModelTurnResponse,
    prove_with_refinement,
)
from src.evaluation.proof_orchestrator import summarize_proof_jsonl


# ---------- lean_verifier helpers ----------


def test_extract_lean_block_returns_last_fence():
    text = (
        "before\n```lean4\nfoo\n```\nthen\n```lean4\nbar := by rfl\n```\nafter"
    )
    assert extract_lean_block(text).strip() == "bar := by rfl"


def test_extract_lean_block_falls_back_to_raw():
    assert extract_lean_block("just text") == "just text"


def test_parse_lean_messages_collects_errors_and_warnings():
    payload = (
        "/tmp/file.lean:3:7: error: unknown identifier 'foo'\n"
        "/tmp/file.lean:4:1: warning: unused variable 'h'\n"
        "other noise\n"
        "/tmp/file.lean:10:2: error: type mismatch\n"
    )
    msgs = parse_lean_messages(payload)
    severities = [m.severity for m in msgs]
    assert severities == ["error", "warning", "error"]
    assert msgs[0].line == 3 and msgs[0].column == 7
    assert "unknown identifier" in msgs[0].body


def test_contains_sorry_ignores_comments():
    assert contains_sorry("theorem x : True := sorry") is True
    assert contains_sorry("-- sorry\ntheorem x : True := trivial") is False
    assert contains_sorry("/- sorry -/\ntheorem x : True := trivial") is False


def test_lean_verify_result_summary_complete():
    r = LeanVerifyResult(ok=True, complete=True)
    assert r.summary() == "complete"


def test_lean_verify_result_summary_pass_but_sorry():
    r = LeanVerifyResult(ok=True, complete=False)
    summary = r.summary()
    assert "sorry" in summary or "failed" in summary


def test_lean_verify_result_summary_errors_truncated():
    errs = [LeanMessage("error", i, 0, f"err-{i}") for i in range(10)]
    r = LeanVerifyResult(ok=False, complete=False, errors=errs)
    summary = r.summary(max_errors=3)
    assert "err-0" in summary and "err-2" in summary
    assert "7 more" in summary


# ---------- multi-turn loop ----------


_DUMMY_MODEL = ModelConfig(label="MockModel", provider_slug="mock/model")


def _make_model_responses(*texts: str):
    """Return a stub model_call that emits the given texts in order."""
    queue = list(texts)
    call_count = {"value": 0}

    async def stub(config, system, user, temperature, max_tokens):
        call_count["value"] += 1
        txt = queue.pop(0) if queue else ""
        return ModelTurnResponse(raw_text=txt, elapsed_seconds=0.001)

    stub.call_count = call_count
    return stub


def _make_verifier(*results: bool):
    """Verifier stub that returns LeanVerifyResult with complete=results[i]."""
    queue = list(results)

    async def stub(code, *, timeout=120.0, extra_env=None):
        ok = bool(queue.pop(0)) if queue else False
        return LeanVerifyResult(
            ok=ok,
            complete=ok,
            errors=[] if ok else [LeanMessage("error", 1, 0, "stub error")],
            verify_time=0.001,
        )

    return stub


def _proof(text: str) -> str:
    return f"```lean4\n{text}\n```"


def test_loop_succeeds_on_first_turn():
    model_call = _make_model_responses(_proof("theorem t : True := trivial"))
    verifier = _make_verifier(True)
    record = asyncio.run(
        prove_with_refinement(
            benchmark="miniF2F",
            arm="control",
            problem_id="t1",
            statement="True",
            formal_prefix="theorem t : True := by",
            model_config=_DUMMY_MODEL,
            model_call=model_call,
            verifier=verifier,
            K=3,
            T_max=4,
        )
    )
    assert record.pass_at_k is True
    assert record.min_turns_to_success == 1
    assert len(record.attempts) == 1
    assert record.attempts[0].turns[0].verify.complete is True


def test_loop_refines_to_success_on_turn_2():
    model_call = _make_model_responses(
        _proof("theorem t : True := bad"),
        _proof("theorem t : True := trivial"),
    )
    verifier = _make_verifier(False, True)
    record = asyncio.run(
        prove_with_refinement(
            benchmark="miniF2F",
            arm="treatment",
            problem_id="t2",
            statement="True",
            formal_prefix="theorem t : True := by",
            model_config=_DUMMY_MODEL,
            model_call=model_call,
            verifier=verifier,
            K=3,
            T_max=4,
        )
    )
    assert record.pass_at_k is True
    assert record.min_turns_to_success == 2
    assert len(record.attempts) == 1
    assert len(record.attempts[0].turns) == 2


def test_loop_injects_initial_and_reflection_premise_context():
    seen_users: List[str] = []

    async def model_call(config, system, user, temperature, max_tokens):
        seen_users.append(user)
        if len(seen_users) == 1:
            return ModelTurnResponse(raw_text=_proof("theorem t : True := bad"), elapsed_seconds=0.001)
        return ModelTurnResponse(raw_text=_proof("theorem t : True := trivial"), elapsed_seconds=0.001)

    verifier = _make_verifier(False, True)

    async def premise_provider(**kwargs):
        phase = kwargs["phase"]
        return {
            "prompt_block": f"Formal name: Test.{phase}",
            "digest": {"phase": phase, "validated_count": 1},
        }

    record = asyncio.run(
        prove_with_refinement(
            benchmark="miniF2F",
            arm="treatment",
            problem_id="t-premise",
            statement="True",
            formal_prefix="theorem t : True := by",
            model_config=_DUMMY_MODEL,
            model_call=model_call,
            verifier=verifier,
            K=1,
            T_max=2,
            premise_context_provider=premise_provider,
        )
    )

    assert record.pass_at_k is True
    assert "Formal name: Test.initial" in seen_users[0]
    assert "Formal name: Test.reflection" in seen_users[1]
    assert record.attempts[0].turns[0].premise_pack["phase"] == "initial"
    assert record.attempts[0].turns[1].premise_pack["phase"] == "reflection"


def test_loop_falls_back_to_next_attempt_when_all_turns_fail():
    # First attempt: 4 turns all fail. Second attempt: succeeds on turn 1.
    model_call = _make_model_responses(
        _proof("bad1"),
        _proof("bad2"),
        _proof("bad3"),
        _proof("bad4"),
        _proof("good"),
    )
    verifier = _make_verifier(False, False, False, False, True)
    record = asyncio.run(
        prove_with_refinement(
            benchmark="putnambench",
            arm="treatment",
            problem_id="p1",
            statement="...",
            formal_prefix="theorem p : True := by",
            model_config=_DUMMY_MODEL,
            model_call=model_call,
            verifier=verifier,
            K=3,
            T_max=4,
        )
    )
    assert record.pass_at_k is True
    assert len(record.attempts) == 2
    assert record.min_turns_to_success == 1  # second attempt succeeded on turn 1


def test_loop_exhausts_all_attempts_and_reports_failure():
    model_call = _make_model_responses(*[_proof("bad")] * 12)  # K=3 * T_max=4
    verifier = _make_verifier(*([False] * 12))
    record = asyncio.run(
        prove_with_refinement(
            benchmark="proofnet",
            arm="control",
            problem_id="x",
            statement="...",
            formal_prefix="theorem x : True := by",
            model_config=_DUMMY_MODEL,
            model_call=model_call,
            verifier=verifier,
            K=3,
            T_max=4,
        )
    )
    assert record.pass_at_k is False
    assert len(record.attempts) == 3
    assert all(len(a.turns) == 4 for a in record.attempts)


def test_loop_handles_empty_lean_block():
    model_call = _make_model_responses("no fence here at all", _proof("theorem t : True := trivial"))
    verifier = _make_verifier(True)  # only used once
    record = asyncio.run(
        prove_with_refinement(
            benchmark="miniF2F",
            arm="control",
            problem_id="empty",
            statement="True",
            formal_prefix="theorem t : True := by",
            model_config=_DUMMY_MODEL,
            model_call=model_call,
            verifier=verifier,
            K=2,
            T_max=2,
        )
    )
    # First turn: fence-less response falls back to raw text => verifier sees
    # "no fence here at all" which our stub still routes to the next result.
    # We accept either outcome but the loop must not crash.
    assert isinstance(record.pass_at_k, bool)


def test_goedel_v2_uses_fenced_code_and_original_statement():
    seen_codes: List[str] = []
    model = ModelConfig(
        label="Goedel",
        provider_slug="goedel",
        prompt_style="goedel_v2",
    )
    model_call = _make_model_responses(
        "Proof plan first.\n\n```lean4\n"
        "theorem changed_name : False := by\n"
        "  trivial\n"
        "```\n"
    )

    async def verifier(code, *, timeout=120.0, extra_env=None):
        seen_codes.append(code)
        return LeanVerifyResult(ok=True, complete=True)

    record = asyncio.run(
        prove_with_refinement(
            benchmark="proofnet",
            arm="control",
            problem_id="goedel-stmt",
            statement="True",
            formal_prefix="theorem original_name : True := by",
            model_config=model,
            model_call=model_call,
            verifier=verifier,
            K=1,
            T_max=1,
        )
    )

    assert record.pass_at_k is True
    assert "theorem original_name : True := by" in seen_codes[0]
    assert "changed_name" not in seen_codes[0]
    assert "Proof plan" not in seen_codes[0]


def test_goedel_v1_uses_fenced_code_and_original_statement():
    seen_codes: List[str] = []
    model = ModelConfig(
        label="Goedel",
        provider_slug="goedel",
        prompt_style="goedel_v1",
    )
    model_call = _make_model_responses(
        "```lean4\n"
        "theorem unrelated_easy_theorem : False := by\n"
        "  trivial\n"
        "```\n"
    )

    async def verifier(code, *, timeout=120.0, extra_env=None):
        seen_codes.append(code)
        return LeanVerifyResult(ok=True, complete=True)

    record = asyncio.run(
        prove_with_refinement(
            benchmark="proofnet",
            arm="control",
            problem_id="goedel-v1-stmt",
            statement="True",
            formal_prefix="theorem original_name : True := by",
            model_config=model,
            model_call=model_call,
            verifier=verifier,
            K=1,
            T_max=1,
        )
    )

    assert record.pass_at_k is True
    assert "theorem original_name : True := by" in seen_codes[0]
    assert "unrelated_easy_theorem" not in seen_codes[0]


def test_goedel_v2_accepts_statement_only_prefix():
    seen_prompts: List[str] = []
    seen_codes: List[str] = []
    model = ModelConfig(
        label="Goedel",
        provider_slug="goedel",
        prompt_style="goedel_v2",
    )

    async def model_call(config, system, user, temperature, max_tokens):
        seen_prompts.append(user)
        return ModelTurnResponse(
            raw_text=(
                "Plan.\n"
                "```lean4\n"
                "theorem generated_name : True := by\n"
                "  trivial\n"
                "```\n"
            )
        )

    async def verifier(code, *, timeout=120.0, extra_env=None):
        seen_codes.append(code)
        return LeanVerifyResult(ok=True, complete=True)

    record = asyncio.run(
        prove_with_refinement(
            benchmark="minif2f",
            arm="treatment",
            problem_id="statement-only",
            statement="True",
            formal_prefix="theorem original_name : True",
            model_config=model,
            model_call=model_call,
            verifier=verifier,
            K=1,
            T_max=1,
        )
    )

    assert record.pass_at_k is True
    assert "theorem original_name : True := by sorry" in seen_prompts[0]
    assert "theorem original_name : True := by" in seen_codes[0]
    assert "generated_name" not in seen_codes[0]


def test_goedel_v2_rejects_unfenced_prose_before_verifier():
    verifier_called = {"value": False}
    model = ModelConfig(
        label="Goedel",
        provider_slug="goedel",
        prompt_style="goedel_v2",
    )
    model_call = _make_model_responses("### Proof plan only\nNo code block.")

    async def verifier(code, *, timeout=120.0, extra_env=None):
        verifier_called["value"] = True
        return LeanVerifyResult(ok=True, complete=True)

    record = asyncio.run(
        prove_with_refinement(
            benchmark="proofnet",
            arm="control",
            problem_id="goedel-no-fence",
            statement="True",
            formal_prefix="theorem original_name : True := by",
            model_config=model,
            model_call=model_call,
            verifier=verifier,
            K=1,
            T_max=1,
        )
    )

    assert record.pass_at_k is False
    assert verifier_called["value"] is False
    assert "no fenced lean code" in record.attempts[0].turns[0].verify.summary()


def test_model_timeout_is_recorded_as_refinement_feedback():
    seen_prompts: List[str] = []

    async def model_call(config, system, user, temperature, max_tokens):
        seen_prompts.append(user)
        if len(seen_prompts) == 1:
            return ModelTurnResponse(
                raw_text="",
                finish_reason="timeout",
                error="timeout after 240s",
            )
        return ModelTurnResponse(raw_text=_proof("theorem t : True := trivial"))

    verifier = _make_verifier(True)
    record = asyncio.run(
        prove_with_refinement(
            benchmark="proofnet",
            arm="gen0",
            problem_id="timeout",
            statement="True",
            formal_prefix="theorem t : True := by",
            model_config=_DUMMY_MODEL,
            model_call=model_call,
            verifier=verifier,
            K=1,
            T_max=2,
        )
    )

    first_summary = record.attempts[0].turns[0].verify.summary()
    assert "model_timeout" in first_summary
    assert "model_timeout" in seen_prompts[1]
    assert record.pass_at_k is True


def test_verifier_exception_is_recorded_as_refinement_feedback():
    seen_prompts: List[str] = []

    async def model_call(config, system, user, temperature, max_tokens):
        seen_prompts.append(user)
        return ModelTurnResponse(raw_text=_proof("theorem t : True := trivial"))

    async def verifier(code, *, timeout=120.0, extra_env=None):
        if len(seen_prompts) == 1:
            raise RuntimeError("lean crashed")
        return LeanVerifyResult(ok=True, complete=True)

    record = asyncio.run(
        prove_with_refinement(
            benchmark="proofnet",
            arm="gen0",
            problem_id="verifier-exception",
            statement="True",
            formal_prefix="theorem t : True := by",
            model_config=_DUMMY_MODEL,
            model_call=model_call,
            verifier=verifier,
            K=1,
            T_max=2,
        )
    )

    assert "lean_verify_exception" in record.attempts[0].turns[0].verify.summary()
    assert "lean_verify_exception" in seen_prompts[1]
    assert record.pass_at_k is True


# ---------- summarizer ----------


def test_summarize_proof_jsonl_computes_pass_at_k_and_turn_distribution(tmp_path: Path):
    eval_jsonl = tmp_path / "eval.jsonl"
    records = [
        {
            "benchmark": "miniF2F",
            "arm": "control",
            "problem_id": "c1",
            "model": "ModelA",
            "provider_slug": "x/y",
            "pass_at_k": True,
            "min_turns_to_success": 1,
            "total_elapsed_seconds": 1.0,
            "attempts": [],
        },
        {
            "benchmark": "miniF2F",
            "arm": "control",
            "problem_id": "c2",
            "model": "ModelA",
            "provider_slug": "x/y",
            "pass_at_k": False,
            "min_turns_to_success": None,
            "total_elapsed_seconds": 5.0,
            "attempts": [],
        },
        {
            "benchmark": "miniF2F",
            "arm": "treatment",
            "problem_id": "t1",
            "model": "ModelA",
            "provider_slug": "x/y",
            "pass_at_k": True,
            "min_turns_to_success": 2,
            "total_elapsed_seconds": 3.0,
            "attempts": [],
        },
        {
            "benchmark": "miniF2F",
            "arm": "treatment",
            "problem_id": "t2",
            "model": "ModelA",
            "provider_slug": "x/y",
            "pass_at_k": False,
            "min_turns_to_success": None,
            "total_elapsed_seconds": 7.0,
            "attempts": [],
        },
        {
            "benchmark": "miniF2F",
            "arm": "treatment",
            "problem_id": "t3",
            "model": "ModelA",
            "provider_slug": "x/y",
            "pass_at_k": False,
            "min_turns_to_success": None,
            "total_elapsed_seconds": 4.0,
            "attempts": [],
        },
    ]
    eval_jsonl.write_text("\n".join(json.dumps(r) for r in records))
    summary_json = tmp_path / "summary.json"
    payload = summarize_proof_jsonl(
        eval_jsonl, summary_json, bootstrap_iterations=100
    )

    cells = {(c["benchmark"], c["model"], c["arm"]): c for c in payload["cells"]}
    control = cells[("miniF2F", "ModelA", "control")]
    treatment = cells[("miniF2F", "ModelA", "treatment")]
    assert control["pass_at_k"] == pytest.approx(0.5)
    assert treatment["pass_at_k"] == pytest.approx(1 / 3)
    assert control["turn_distribution"][1] == 1
    assert treatment["turn_distribution"][2] == 1

    drops = {(d["benchmark"], d["model"]): d for d in payload["drops"]}
    drop_cell = drops[("miniF2F", "ModelA")]
    assert drop_cell["control_pass_at_k"] == pytest.approx(0.5)
    assert drop_cell["treatment_pass_at_k"] == pytest.approx(1 / 3)
    assert drop_cell["drop_pp"] == pytest.approx(
        (0.5 - 1 / 3) * 100, rel=1e-6
    )
