import logging
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "agent.log"

LOG_DIR.mkdir(
    exist_ok=True
)


logger = logging.getLogger(
    "network_agent"
)

logger.setLevel(
    logging.DEBUG
)

if not logger.handlers:

    file_handler = logging.FileHandler(
        LOG_FILE,
        encoding="utf-8"
    )

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler.setFormatter(
        formatter
    )

    logger.addHandler(
        file_handler
    )


def log_llm_request(model, messages):

    logger.debug(
        f"LLM REQUEST | model={model} | "
        f"messages={_safe_summary(messages)}"
    )


def log_llm_response(response):

    logger.debug(
        f"LLM RESPONSE | {_safe_summary(response)}"
    )


def log_tool_call(name, arguments, device_name=None):

    logger.info(
        f"TOOL CALL | name={name} | "
        f"device={device_name} | args={arguments}"
    )


def log_tool_result(name, result):

    success = result.get(
        "success"
    )

    logger.info(
        f"TOOL RESULT | name={name} | success={success} | "
        f"result={_safe_summary(result)}"
    )


def log_error(context, exc):

    logger.error(
        f"ERROR | context={context} | detail={exc}"
    )


def _safe_summary(obj, limit=2000):

    text = str(obj)

    if len(text) > limit:
        return text[:limit] + "...(truncated)"

    return text