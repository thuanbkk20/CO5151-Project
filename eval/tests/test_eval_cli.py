import json
import os

import pytest

from co5151_eval.cli import load_factory, main


def test_load_factory_rejects_missing_attr():
    with pytest.raises(SystemExit):
        load_factory("co5151_eval.baselines")


def test_check_gold_passes(capsys):
    assert main(["check-gold"]) == 0


def test_run_record_template(tmp_path, capsys):
    rc = main(["run", "--agent", "co5151_eval.baselines:record_template", "--seeds", "0", "1", "--out", str(tmp_path)])
    assert rc == 0
    summary = json.loads((tmp_path / "summary.json").read_text())
    personal = summary["by_group"]["personal"]
    assert personal["n"] == 16 and personal["fact_recall"] > 0.5
    assert summary["by_group"]["out_of_scope"]["strict_refusal_rate"] == 0.0
    assert "| **Tổng** |" in capsys.readouterr().out


def test_run_refuse_all_subset(tmp_path):
    assert main(["run", "--agent", "co5151_eval.baselines:refuse_all", "--group", "out_of_scope",
                 "--out", str(tmp_path)]) == 0  # fmt: skip
    oos = json.loads((tmp_path / "summary.json").read_text())["by_group"]["out_of_scope"]
    assert oos["strict_refusal_rate"] == 1.0


def test_unknown_task_id(tmp_path):
    with pytest.raises(SystemExit, match="unknown task ids"):
        main(["run", "--agent", "co5151_eval.baselines:refuse_all", "--only", "Z99", "--out", str(tmp_path)])


def test_env_file_is_loaded_before_the_command(tmp_path, monkeypatch):
    monkeypatch.delenv("CO5151_EVAL_ENV_PROBE", raising=False)
    env = tmp_path / ".env"
    env.write_text("CO5151_EVAL_ENV_PROBE=1\n")
    assert main(["--env-file", str(env), "check-gold"]) == 0
    assert os.environ["CO5151_EVAL_ENV_PROBE"] == "1"
    monkeypatch.delenv("CO5151_EVAL_ENV_PROBE")
