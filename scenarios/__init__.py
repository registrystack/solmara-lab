#!/usr/bin/env python3
"""Guided scenario surface for Solmara Lab."""

from __future__ import annotations

from typing import Any

from . import child_benefit, citizen, farmer_voucher, pension_survivor


SCENARIOS = [child_benefit, pension_survivor, farmer_voucher, citizen]
STORY_BY_ID = {module.SCENARIO_ID: module for module in SCENARIOS}


def all_stories() -> list[dict[str, Any]]:
    return [module.story() for module in SCENARIOS]


def scenario_payload(config: dict[str, Any], scenario_id: str | None = None, lab_mode: str = "hosted") -> dict[str, Any]:
    if scenario_id:
        module = STORY_BY_ID.get(scenario_id)
        if not module:
            return {"error": "unknown_scenario", "scenario_id": scenario_id}
        story = module.story()
        return {
            "story": {
                **story,
                "steps": [{**step, "request_preview": module.preview_step(config, step["id"])} for step in story.get("steps", [])],
            },
            "lab_mode": lab_mode,
            "runnable": True,
        }
    return {
        "lab_mode": lab_mode,
        "default_scenario_id": child_benefit.SCENARIO_ID,
        "scenarios": [
            {
                "id": story["id"],
                "title": story["short_title"],
                "full_title": story["title"],
                "proves": story["proves"],
                "domain": story.get("domain", ""),
                "availability": story.get("availability", "hosted"),
                "steps": len(story.get("steps", [])),
                "runnable": True,
            }
            for story in all_stories()
        ],
    }


def run_scenario_step(config: dict[str, Any], scenario_id: str, step_id: str, lab_mode: str = "hosted") -> dict[str, Any]:
    module = STORY_BY_ID.get(scenario_id)
    if not module:
        return {
            "step_id": step_id,
            "friendly": {"title": "Unknown scenario.", "message": "This scenario is not configured.", "status": "needs_attention", "facts": []},
            "request_source": {},
            "response_source": {},
        }
    return module.run_step(config, step_id)
