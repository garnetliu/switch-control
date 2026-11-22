"""control_switch.log：终端和文件日志。"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from control_switch.log import init_log, new_log

SessionFactory = Callable[..., Any]


def file_handlers(root: logging.Logger) -> list[logging.FileHandler]:
    return [h for h in root.handlers if isinstance(h, logging.FileHandler)]


def test_new_log_creates_log_file_under_log_dir_name_directory(
    make_session: SessionFactory, clean_root_logger: logging.Logger
) -> None:
    """new_log 在 config.log_dir/名字/ 下建出一个 .log 文件。"""
    sw = make_session([b""])
    new_log(sw, "脚本甲")
    files = list((sw.config.log_dir / "脚本甲").glob("*.log"))
    assert len(files) == 1


def test_init_log_twice_keeps_one_file_handler_and_one_file(
    make_session: SessionFactory, clean_root_logger: logging.Logger
) -> None:
    """init_log 连着调两次：根 logger 上只有一个 FileHandler，只建了一个 .log 文件。"""
    sw = make_session([b""])
    init_log(sw, "脚本甲")
    init_log(sw, "脚本甲")
    assert len(file_handlers(clean_root_logger)) == 1
    assert len(list(Path(sw.config.log_dir).rglob("*.log"))) == 1


def test_new_log_with_two_names_switches_to_second_file_and_closes_first(
    make_session: SessionFactory, clean_root_logger: logging.Logger
) -> None:
    """new_log 先后传两个名字：只剩第二个文件的 FileHandler，第一个已关掉，之后的日志只进第二个文件。"""
    sw = make_session([b""])
    new_log(sw, "甲")
    first = file_handlers(clean_root_logger)[0]
    new_log(sw, "乙")
    remaining = file_handlers(clean_root_logger)
    assert len(remaining) == 1
    assert Path(remaining[0].baseFilename).parent == sw.config.log_dir / "乙"
    assert first not in clean_root_logger.handlers
    assert first.stream is None
    logging.info("只写进第二个文件")
    first_file = next((sw.config.log_dir / "甲").glob("*.log"))
    second_file = next((sw.config.log_dir / "乙").glob("*.log"))
    assert "只写进第二个文件" not in first_file.read_text(encoding="utf-8")
    assert "只写进第二个文件" in second_file.read_text(encoding="utf-8")


def test_root_logging_info_is_written_to_the_file(
    make_session: SessionFactory, clean_root_logger: logging.Logger
) -> None:
    """logging.info 的内容写进了日志文件。"""
    sw = make_session([b""])
    new_log(sw, "脚本甲")
    logging.info("根日志的一条消息")
    content = next((sw.config.log_dir / "脚本甲").glob("*.log")).read_text(encoding="utf-8")
    assert "INFO: 根日志的一条消息" in content


def test_other_logger_records_are_not_written_to_the_file(
    make_session: SessionFactory, clean_root_logger: logging.Logger
) -> None:
    """logging.getLogger("别的名字").warning 的内容没有写进日志文件（第三方库的日志被挡掉）。"""
    sw = make_session([b""])
    new_log(sw, "脚本甲")
    logging.getLogger("别的名字").warning("第三方库的一条消息")
    logging.info("根日志的一条消息")
    content = next((sw.config.log_dir / "脚本甲").glob("*.log")).read_text(encoding="utf-8")
    assert "第三方库的一条消息" not in content
    assert "根日志的一条消息" in content


def terminal_handlers(root: logging.Logger) -> list[logging.Handler]:
    return [
        h
        for h in root.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
    ]


def test_init_log_adds_one_terminal_handler_and_only_root_records_reach_it(
    make_session: SessionFactory,
    clean_root_logger: logging.Logger,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """根 logger 上没有终端 handler 时，init_log 加上一个，调两次也只有一个；终端只输出根日志。

    pytest 在测试开始后才往根 logger 上加自己的终端 handler，所以这里在测试里清空一次。
    """
    clean_root_logger.handlers.clear()
    sw = make_session([b""])
    init_log(sw, "脚本甲")
    init_log(sw, "脚本甲")
    assert len(terminal_handlers(clean_root_logger)) == 1
    logging.info("根日志给终端")
    logging.getLogger("别的名字").warning("第三方库给终端")
    err = capsys.readouterr().err
    assert "INFO: 根日志给终端" in err
    assert "第三方库给终端" not in err
