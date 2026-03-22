"""Markdown output for metrics script (N/A vs zero wording)."""

from scripts.generate_contextlens_metrics import render_project_metrics_markdown


def test_render_llm_judge_denominator_zero_shows_not_available():
    md = render_project_metrics_markdown({"llm_judge_call_rate": None})
    assert "llm_judge_call_rate: not available" in md


def test_render_llm_judge_honest_zero_prints_zero():
    md = render_project_metrics_markdown({"llm_judge_call_rate": 0.0})
    assert "- llm_judge_call_rate (all evaluation rows): 0" in md


def test_render_failure_section_na_when_bucket_has_no_rows():
    md = render_project_metrics_markdown(
        {
            "evaluation_rows_llm": 0,
            "failure_type_counts_llm": {},
        }
    )
    assert "N/A — no evaluation rows in this slice" in md
