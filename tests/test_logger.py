import logging
from utils.logger import get_logger


def test_get_logger_returns_logger_instance():
    logger = get_logger("test_module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_module"


def test_logger_can_log_without_error():
    logger = get_logger("test_module")
    logger.info("This is a test log message from the sample test suite.")
