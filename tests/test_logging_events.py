import logging
from claude_agent_toolkit.logging import set_logging, get_logger, LogLevel
from claude_agent_toolkit.system.observability import event_bus, LogEvent

def test_logging_forward_events():
    captured = []
    event_bus.subscribe("log", lambda ev: captured.append(ev))
    set_logging(LogLevel.INFO, show_level=True, forward_events=True)
    logger = get_logger("test")
    logger.info("hello world")
    # flush
    logging.shutdown()
    log_events = [e for e in captured if isinstance(e, LogEvent) and "hello world" in e.message]
    assert log_events, "LogEvent not captured"