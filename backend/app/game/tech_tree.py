"""Tech tree prereq kontrolu."""

from __future__ import annotations

from backend.app.game.constants import TECH_PREREQUISITES, TechType


def check_research_prerequisites(
    tech_type: TechType,
    max_research_lab_level: int,
    user_tech_levels: dict[TechType, int],
) -> tuple[bool, list[str]]:
    """Tum gezegenlerdeki max research lab seviyesi ve mevcut tech seviyelerine gore prereq dogrula."""
    reqs = TECH_PREREQUISITES.get(tech_type, {})
    missing: list[str] = []

    for key, required_level in reqs.items():
        if key == "lab":
            if max_research_lab_level < required_level:
                missing.append(f"Research Lab level {required_level} required")
        else:
            tech = TechType(key)
            current = user_tech_levels.get(tech, 0)
            if current < required_level:
                missing.append(f"{tech.value} level {required_level} required")

    return len(missing) == 0, missing
