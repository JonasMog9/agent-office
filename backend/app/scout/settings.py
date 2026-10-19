"""The Scout's settings from the environment, as the scan's types."""

from app.config import get_settings
from app.scout.screen import Rules
from app.scout.sources import NETWORKS


def rules() -> Rules:
    return Rules(min_volume_h24=get_settings().scout_min_volume_usd)


def chains() -> list[str]:
    wanted = [c.strip().lower() for c in get_settings().scout_chains.split(",")]
    return [c for c in wanted if c in NETWORKS]
