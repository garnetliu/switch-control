"""对战相关的共用类型。"""

from dataclasses import dataclass


@dataclass
class Field:
    """场上的天气和场地。"""

    # clear 晴朗无天气、sunlight 大晴天、rain 下雨、sandstorm 沙暴、hail 冰雹
    weather: str = "clear"
    # clear 无场地、electric 电气场地、grassy 青草场地、misty 薄雾场地、psychic 精神场地
    terrain: str = "clear"
