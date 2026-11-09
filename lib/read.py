"""从截图里读出游戏信息。"""

from dataclasses import replace

import cv2
import numpy as np

from config.layout import TEAM_HP_RECTS, TEAM_SPRITE_RECTS
from lib import data, run
from lib.log import log
from tool.check_image import ImageChecker
from tool.image import crop
from typedefs.image import Rect


def read_team(
    image: ImageChecker,
    sprite_rects: tuple[Rect, ...] = TEAM_SPRITE_RECTS,
    hp_rects: tuple[Rect, ...] | None = TEAM_HP_RECTS,
) -> bool:
    """认出队伍栏里的 4 只宝可梦（自己加三个队友），记到当前这一局。

    4 个位置都认得出才记录并返回 True；有空位或认不清就返回 False，不改动这一局，
    所以可以直接用作 wait_for 的条件，一直读到队友都选好。
    sprite_rects、hp_rects: 队伍栏在不同界面上的位置不同，默认是冒险中路线图界面的。
    hp_rects 为 None 时不读血条，血量都记为满，刚开局时就是这样。
    每个成员是数据里宝可梦的副本，改血量不会影响共用的数据。
    """
    # 血条的颜色范围，范围内的像素占比就是剩余血量
    hp_lower, hp_upper = (0, 50, 0), (180, 255, 255)
    # 精灵图的匹配度低于这个值，就当这个位置还没有宝可梦或者认不清
    min_sprite_score = 0.75

    name_ids = []
    for index, sprite_rect in enumerate(sprite_rects):
        area = crop(image, sprite_rect)
        score, name_id = max(
            (_sprite_score(sprite, area), name_id) for name_id, sprite in data.pokemon_sprites()
        )
        if score < min_sprite_score:
            log(f"队伍第 {index + 1} 个还认不出，最像的是 {name_id}，匹配度 {score:.3f}", "DEBUG")
            return False
        log(f"队伍第 {index + 1} 个是 {name_id}，匹配度 {score:.3f}", "DEBUG")
        name_ids.append(name_id)

    current = run.get()
    members = []
    for index, name_id in enumerate(name_ids):
        hp = 1.0 if hp_rects is None else image.color_ratio(hp_rects[index], hp_lower, hp_upper)
        members.append(replace(data.rental_pokemon()[name_id], hp=hp))
        current.encountered.add(name_id)
    own, *teammates = members
    if current.pokemon is not None and current.pokemon.name_id != own.name_id:
        log(
            f"从精灵图认出自己的宝可梦是 {own.name_id}，"
            f"和之前选的 {current.pokemon.name_id} 不一致",
            "WARNING",
        )
    current.pokemon = own
    current.team = teammates
    log(f"队伍: {[member.name_id for member in members]}，血量 {[f'{m.hp:.0%}' for m in members]}")
    return True


def _sprite_score(sprite: np.ndarray, area: np.ndarray) -> float:
    """area 在精灵图里的最高匹配度。area 比精灵图大时没法匹配，返回 0。"""
    if area.shape[0] > sprite.shape[0] or area.shape[1] > sprite.shape[1]:
        return 0.0
    return float(cv2.matchTemplate(sprite, area, cv2.TM_CCOEFF_NORMED).max())
