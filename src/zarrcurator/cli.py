import argparse
from datetime import datetime
import logging
import os
from pathlib import Path

ENV_LOG_LEVEL = "ZARRCURATOR_LOG_LEVEL"
ENV_LOG_DIR = "ZARRCURATOR_LOG_DIR"
DEFAULT_LOG_LEVEL = "INFO"


def _create_timestamped_log_file():
    """Create a timestamped log file path and ensure its directory exists."""

    log_dir = Path(os.getenv(ENV_LOG_DIR) or "logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"zarrcurator_{timestamp}.log"


def configure_logging(log_level=None):
    """Configure root logging for zarrcurator CLI usage.

    Priority:
    1. CLI --log-level value
    2. ZARRCURATOR_LOG_LEVEL environment variable
    3. INFO default
    """

    resolved = (log_level or os.getenv(ENV_LOG_LEVEL) or DEFAULT_LOG_LEVEL).upper()
    valid_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}

    if resolved not in valid_levels:
        resolved = DEFAULT_LOG_LEVEL

    log_file = _create_timestamped_log_file()

    logging.basicConfig(
        level=getattr(logging, resolved),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8", delay=True),
        ],
        force=True,
    )

    logging.getLogger(__name__).debug(
        "Configured logging level=%s log_file=%s", resolved, log_file
    )
    return resolved


def main():
    parser = argparse.ArgumentParser(description="zarrcurator package CLI")
    parser.add_argument("name")
    parser.add_argument(
        "--log-level",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
        default=None,
        help=(
            "Set logging level. Defaults to env ZARRCURATOR_LOG_LEVEL or INFO."
        ),
    )
    args = parser.parse_args()

    configure_logging(args.log_level)
