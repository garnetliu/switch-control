"""对战相关的共用类型。"""

import logging
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class Field:
    """场上的天气和场地。"""

    # 场地变化的提示都带「脚下」；消失的提示放在前面，「脚下的青草消失了」里也有「青草」
    TERRAINS: ClassVar[tuple[tuple[tuple[str, ...], str], ...]] = (
        (("消失",), "clear"),
        (("电光",), "electric"),
        (("青草",), "grassy"),
        (("雾气",), "misty"),
        (("奇妙",), "psychic"),
    )
    WEATHERS: ClassVar[tuple[tuple[tuple[str, ...], str], ...]] = (
        (("日照复原", "雨停", "沙暴停止", "冰雹停止"), "clear"),
        (("日照变强",), "sunlight"),
        (("开始下雨",), "rain"),
        (("开始刮沙暴",), "sandstorm"),
        (("开始下冰雹",), "hail"),
    )

    # clear 晴朗无天气、sunlight 大晴天、rain 下雨、sandstorm 沙暴、hail 冰雹
    weather: str = "clear"
    # clear 无场地、electric 电气场地、grassy 青草场地、misty 薄雾场地、psychic 精神场地
    terrain: str = "clear"

    @classmethod
    def change(cls, text: str) -> tuple[str, str] | None:
        """战斗文字是不是天气、场地变化的提示：是就返回 ("terrain" 或 "weather", 变成什么)，不是返回 None。"""
        if "脚下" in text:
            table, kind = cls.TERRAINS, "terrain"
        else:
            table, kind = cls.WEATHERS, "weather"
        for keywords, value in table:
            if any(keyword in text for keyword in keywords):
                return kind, value
        return None

    def update(self, text: str) -> None:
        """按战斗文字里的提示更新天气或场地，不是提示就不变。"""
        change = self.change(text)
        if change is None:
            return
        kind, value = change
        if getattr(self, kind) != value:
            logging.info(f"{'场地' if kind == 'terrain' else '天气'}变成 {value}：{text}")
        setattr(self, kind, value)
