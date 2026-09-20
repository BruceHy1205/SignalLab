import json
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from signal_contracts.research_job import (
    Budget,
    ResearchJobSpec,
    RunnerTarget,
    RunnerTargetType,
    resolve_key_ref,
)
from signal_contracts.runner_events import (
    CompletionReport,
    CompletionStatus,
    RunnerEvent,
    RunnerEventType,
    sign_payload,
    verify_signature,
)
from signal_contracts.strategy_package import (
    FactorSpec,
    StrategyManifest,
)


def make_manifest_dict() -> dict:
    return {
        "package_id": str(uuid.uuid4()),
        "producer": "alphaagent@0.1",
        "created_at": datetime.now(UTC).isoformat(),
        "data_snapshot": "qlib_cn_20260718",
        "universe": "csi300",
        "backtest_start": "2023-01-01",
        "backtest_end": "2026-06-30",
        "metrics_summary": {"ic": 0.05, "arr": 0.14, "mdd": -0.07},
        "signal_protocol": "qlib_expression",
        "factors": [{"name": "mom20", "expression": "Ref($close, 20)/$close - 1"}],
    }


class TestStrategyPackage:
    def test_roundtrip(self):
        m = StrategyManifest.model_validate(make_manifest_dict())
        again = StrategyManifest.model_validate_json(m.model_dump_json())
        assert again == m

    def test_factor_requires_exactly_one_impl(self):
        with pytest.raises(ValidationError):
            FactorSpec(name="x")
        with pytest.raises(ValidationError):
            FactorSpec(name="x", expression="$close", code_file="f.py")

    def test_mdd_must_be_non_positive(self):
        d = make_manifest_dict()
        d["metrics_summary"]["mdd"] = 0.07
        with pytest.raises(ValidationError):
            StrategyManifest.model_validate(d)

    def test_empty_factors_rejected(self):
        d = make_manifest_dict()
        d["factors"] = []
        with pytest.raises(ValidationError):
            StrategyManifest.model_validate(d)


class TestResearchJob:
    def make_spec_dict(self) -> dict:
        return {
            "job_id": str(uuid.uuid4()),
            "producer": "rdagent",
            "scenario": "fin_factor",
            "runner_target": {"type": "local_docker"},
            "llm": {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "api_key_ref": "env:DEEPSEEK_KEY",
            },
            "budget": {"max_loops": 20, "max_hours": 12, "max_llm_cost_usd": 15},
            "data_snapshot": "qlib_cn_20260718",
            "callback": {
                "base_url": "http://localhost:8000/api/research/jobs/x",
                "hmac_key_ref": "env:RUNNER_CALLBACK_SECRET",
            },
            "artifact_upload": {"type": "http_put", "url": "http://localhost:8000/upload"},
        }

    def test_roundtrip(self):
        spec = ResearchJobSpec.model_validate(self.make_spec_dict())
        assert ResearchJobSpec.model_validate_json(spec.model_dump_json()) == spec

    def test_remote_ssh_requires_host_user(self):
        with pytest.raises(ValidationError):
            RunnerTarget(type=RunnerTargetType.REMOTE_SSH)

    def test_key_ref_must_be_env_form(self):
        d = self.make_spec_dict()
        d["llm"]["api_key_ref"] = "sk-plaintext-secret"  # 禁止明文
        with pytest.raises(ValidationError):
            ResearchJobSpec.model_validate(d)

    def test_budget_bounds(self):
        with pytest.raises(ValidationError):
            Budget(max_loops=0, max_hours=1, max_llm_cost_usd=1)

    def test_resolve_key_ref(self, monkeypatch):
        monkeypatch.setenv("MY_SECRET", "v123")
        assert resolve_key_ref("env:MY_SECRET") == "v123"
        with pytest.raises(KeyError):
            resolve_key_ref("env:NOT_SET_VAR_XYZ")
        with pytest.raises(ValueError):
            resolve_key_ref("plain-secret")


class TestRunnerEvents:
    def test_event_roundtrip(self):
        e = RunnerEvent(
            job_id=uuid.uuid4(),
            type=RunnerEventType.LOOP_DONE,
            ts=datetime.now(UTC),
            seq=3,
            loop=3,
            best_ic=0.041,
            llm_cost_usd=3.2,
        )
        assert RunnerEvent.model_validate_json(e.model_dump_json()) == e

    def test_completion_roundtrip(self):
        r = CompletionReport(
            job_id=uuid.uuid4(), status=CompletionStatus.SUCCEEDED, package_id=uuid.uuid4()
        )
        assert CompletionReport.model_validate_json(r.model_dump_json()) == r

    def test_hmac_sign_verify(self):
        body = json.dumps({"a": 1}).encode()
        sig = sign_payload("secret", body)
        assert verify_signature("secret", body, sig)
        assert not verify_signature("wrong", body, sig)
        assert not verify_signature("secret", b"tampered", sig)
