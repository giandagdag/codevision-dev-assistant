import logging

from da_logging import get_logger


def test_get_logger_uses_the_given_name():
    logger = get_logger("da_test_name")

    assert logger.name == "da_test_name"
    assert logger.level == logging.INFO


def test_get_logger_twice_does_not_add_a_second_handler():
    first = get_logger("da_test_twice")
    second = get_logger("da_test_twice")

    assert first is second
    assert len(second.handlers) == 1


def test_messages_reach_the_log(caplog):
    logger = get_logger("da_test_message")

    with caplog.at_level(logging.INFO, logger="da_test_message"):
        logger.info("hello from the test")

    assert "hello from the test" in caplog.text
