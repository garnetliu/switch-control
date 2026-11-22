"""核对伤害公式 scoring.damage()：拿日志里每回合记录的实际掉血，和公式算出来的比。

用法：PYTHONPATH=src uv run python docs/打分算法探索脚本/版本19-伤害公式核对.py [日志...]
不给日志就读 logs/swsh-lair/start/ 下所有带「回合数据」的日志。

两次「回合数据」之间就是一回合。挑两种能确定来源的掉血：
- 对手打我方（A）：这一回合对手只出了一招、是进攻招式、打中了；单体招式要求我方只有一只掉血，
  范围招式我方每只掉的血都算一条。
- 我方打对手（B）：对手这回合掉的血 = 我方几只这回合打中的进攻招式之和。我方用了哪个招式看 PP 少了哪个，
  战斗文字只用来看打没打中、有没有要害。
比的是绝对血量（伤害和被打方血量无关），预测 = damage() × 被打方数据 HP ÷ 命中率（damage() 乘了命中率，
日志里的掉血都是打中了的）。
raw damage() 原样（乘了命中率），数据能力值；
(a) 数据能力值（GameData.pokemon_object：数据性格 + 个体值全 31）；
(c) 日志里实际的能力值，不算能力等级；
(b) 日志里实际的能力值，乘上回合开头的能力等级。
特性、道具都照 damage() 原样（数据里的特性、不算道具）。
环境变量 V19_DUMP 给了路径就把样本用 pickle 存下来。
"""

import ast
import glob
import os
import pickle
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, replace

from control_switch.vision.text import levenshtein
from swsh.lair.game_config import GameConfig
from swsh.lair.game_data import GameData
from swsh.pokemon import Pokemon
from swsh.scoring import Field, damage, type_multiplier

ME = "夜暮林夕"
SCREEN = 2732 / 4096  # 多打里光墙、反射壁的倍率
ALLY_SPREAD = {"bulldoze", "discharge", "earthquake", "lava-plume", "sludge-wave", "surf", "brutal-swing"}
HEAL_MOVES = {
    "drain-punch", "giga-drain", "draining-kiss", "leech-life", "horn-leech", "strength-sap", "recover",
    "roost", "synthesis", "moonlight", "morning-sun", "wish", "rest", "absorb", "mega-drain",
    "oblivion-wing", "parabolic-charge", "slack-off", "soft-boiled", "milk-drink", "shore-up",
    "life-dew", "heal-pulse", "pollen-puff", "leech-seed", "pain-split", "floral-healing",
}

data = GameData(GameConfig())
LEGENDS = set(data.boss_pokemon())


@dataclass
class Logged(Pokemon):
    """能力值换成日志里的实际值（已乘能力等级）；HP 仍用数据的，好把 damage() 换回绝对血量。"""

    override: tuple = ()

    @property
    def stats(self) -> tuple[float, ...]:
        return (super().stats[0], *self.override)


def stage_factor(stage: int) -> float:
    return (2 + stage) / 2 if stage >= 0 else 2 / (2 - stage)


def obj(name_id: str) -> Pokemon:
    return data.pokemon_object(name_id)


# 数据里的中文名和游戏里显示的不一样的
ALIASES = {"狐大盗": "猾大狐", "流氓熊猫": "霸道熊猫", "死神棺": "迭失棺"}


def zh(name_id: str) -> str:
    name = obj(name_id).name("zh-Hans")
    return ALIASES.get(name, name)


# ---------------------------------------------------------------- 解析日志

SNAP = re.compile(
    r"^(\d\d:\d\d:\d\d) \| INFO: 回合数据 (\S+) (\S+)（种类 (\d+)）：血量 (\d+)/(\d+)，能力 (\[.*?\])，"
    r"变化 (\[.*?\])，招式 (.*)$"
)
MOVE_ITEM = re.compile(r"(.+?) (\d+)/(\d+)$")


def parse_snapshot_moves(text: str) -> list[tuple[str, int, int]]:
    moves = []
    for part in text.split("、"):
        m = MOVE_ITEM.match(part.strip())
        if m:
            moves.append((m[1], int(m[2]), int(m[3])))
    return moves


def parse_log(path: str) -> list[dict]:
    """把日志切成一场一场的战斗，每场里是按顺序的事件：snap（5 只的回合数据）、text、own_move、dynamax。"""
    battles: list[dict] = []
    cur = None
    snap = None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        m = re.search(r"队伍道具: (.*)$", line)
        if m:
            items = [x.strip() for x in m[1].split("，")]
            continue
        m = re.search(r"队伍特性: (.*)$", line)
        if m:
            abilities = [re.sub(r"（.*?）", "", x).strip() for x in m[1].split("，")]
            continue
        m = re.search(r"INFO: 对手 (\S+)（种类 (\d+)）：特性 (\S+?)（编号 \d+），性格 (\d+)，.*?个体值 (\[.*?\])，等级 (\d+)", line)
        if m:
            cur = dict(
                path=path, opponent=m[1], opp_ability=m[3], opp_nature=int(m[4]),
                opp_ivs=ast.literal_eval(m[5]), opp_level=int(m[6]),
                items=locals().get("items", []), abilities=locals().get("abilities", []),
                events=[],
            )
            battles.append(cur)
            snap = None
            continue
        if cur is None:
            continue
        m = SNAP.match(line)
        if m:
            entry = dict(
                time=m[1], label=m[2], name=m[3], cur=int(m[5]), max=int(m[6]),
                stats=ast.literal_eval(m[7]), stages=ast.literal_eval(m[8]), moves=parse_snapshot_moves(m[9]),
            )
            if m[2] == "对手":
                snap = dict(time=m[1], slots=[entry])
                cur["events"].append(("snap", snap))
            elif snap is not None:
                snap["slots"].append(entry)
            continue
        m = re.search(r"^(\d\d:\d\d:\d\d) \| INFO: 战斗文字: (.*)$", line)
        if m:
            cur["events"].append(("text", m[2].strip(), m[1]))
            continue
        if re.search(r"INFO: 极巨化$", line):
            cur["events"].append(("dynamax",))
            continue
        if "INFO: 抓第" in line or "INFO: 队伍血量" in line:
            cur = None
    return battles


# ---------------------------------------------------------------- 一回合里的战斗文字

ACTION = re.compile(r"^(.+?)使出了\S*\s*/\s*(.+?)[！!。.]*$")


def closest(text: str, options: list[str], limit: int) -> int | None:
    if not options:
        return None
    scores = [levenshtein(text, o) for o in options]
    best = min(scores)
    if best > limit or scores.count(best) > 1:
        return None
    return scores.index(best)


class FieldTracker:
    """按战斗文字跟踪天气、场地、光墙反射壁（都按 5 回合到期，文字里有结束提示也结束）。"""

    def __init__(self):
        self.weather, self.weather_left = "clear", 0
        self.terrain, self.terrain_left = "clear", 0
        self.screens = {}  # (side, kind) -> 剩余回合

    def text(self, t: str) -> None:
        if "脚下" in t:
            for keys, v in Field.TERRAINS:
                if any(k in t for k in keys):
                    self.terrain, self.terrain_left = v, (0 if v == "clear" else 5)
                    return
        if re.search(r"日照复原|雨停|沙暴停止|冰雹停止|冰電停止", t):
            self.weather, self.weather_left = "clear", 0
        elif "照变强" in t:
            self.weather, self.weather_left = "sunlight", 5
        elif "开始下雨" in t:
            self.weather, self.weather_left = "rain", 5
        elif "开始刮沙暴" in t:
            self.weather, self.weather_left = "sandstorm", 5
        elif re.search(r"开始下冰", t):
            self.weather, self.weather_left = "hail", 5
        if "抗性提高" in t:
            side = "own" if "我方" in t else "opp" if "对手" in t else None
            kinds = []
            if "特殊" in t:
                kinds.append("special")
            if "物理" in t:
                kinds.append("physical")
            for k in kinds:
                for s in ([side] if side else ["own", "opp"]):
                    self.screens[(s, k)] = 5

    def end_turn(self) -> None:
        self.weather_left -= 1
        if self.weather_left <= 0:
            self.weather = "clear"
        self.terrain_left -= 1
        if self.terrain_left <= 0:
            self.terrain = "clear"
        self.screens = {k: v - 1 for k, v in self.screens.items() if v > 1}

    def field(self) -> Field:
        return Field(weather=self.weather, terrain=self.terrain)


# ---------------------------------------------------------------- 预测

def accuracy_divisor(move, field: Field) -> float:
    """damage() 里乘的命中率（含天气对暴风雪、打雷、暴风的修正），用来换成「打中了的伤害」。"""
    acc = move.accuracy if move.accuracy and move.accuracy > 0 else 1.0
    f = 1.0
    if field.weather == "hail" and move.name_id == "blizzard":
        f = 1 / 0.7
    elif field.weather == "rain" and move.name_id in ("thunder", "hurricane"):
        f = 1 / 0.7
    elif field.weather == "sunlight" and move.name_id in ("thunder", "hurricane"):
        f = 0.5 / 0.7
    return acc * f


def logged(base: Pokemon, entry: dict, crit_role: str | None = None, use_stages: bool = True) -> Logged:
    stages = list(entry["stages"][:5]) if use_stages else [0] * 5
    if crit_role == "attacker":
        stages = [max(s, 0) for s in stages]
    elif crit_role == "defender":
        stages = [min(s, 0) for s in stages]
    override = tuple(entry["stats"][i] * stage_factor(stages[i]) for i in range(4)) + (entry["stats"][4],)
    fields = {k: getattr(base, k) for k in base.__dataclass_fields__}
    return Logged(**fields, override=override)


def predict(att: Pokemon, index: int, dfd: Pokemon, field: Field, spread: bool) -> float:
    """打中了的平均伤害，绝对血量。"""
    move = att.max_moves[index] if att.dynamax else att.moves[index]
    value = damage(att, index, dfd, field, spread)
    return value * dfd.stats[0] / accuracy_divisor(move, field)


def predict_pair(att_name, att_entry, dyn, index, dfd_name, dfd_entry, field, spread, crit):
    a_att = replace(obj(att_name), dynamax=dyn)
    a_dfd = replace(obj(dfd_name), dynamax=False)
    pa = predict(a_att, index, a_dfd, field, spread)
    # damage() 原样（乘了命中率），换成绝对血量
    raw = damage(a_att, index, a_dfd, field, spread) * a_dfd.stats[0]
    b_att = replace(logged(obj(att_name), att_entry, "attacker" if crit else None), dynamax=dyn)
    b_dfd = logged(obj(dfd_name), dfd_entry, "defender" if crit else None)
    pb = predict(b_att, index, b_dfd, field, spread)
    c_att = replace(logged(obj(att_name), att_entry, use_stages=False), dynamax=dyn)
    c_dfd = logged(obj(dfd_name), dfd_entry, use_stages=False)
    pc = predict(c_att, index, c_dfd, field, spread)
    if crit:
        pb *= 1.5
    return pa, pb, pc, raw


# ---------------------------------------------------------------- 主流程

def main(paths: list[str]) -> None:
    samples_a: list[dict] = []
    samples_b: list[dict] = []
    stat_rows: list[tuple] = []  # (名字, 是否首领, 数据能力值, 实际能力值)
    hp_rows: list[tuple] = []  # (对手, 首领?, 战斗最大血量, 数据 HP)
    censored: list[dict] = []
    drop_reasons = Counter()
    effect_check = Counter()

    for path in paths:
        for battle in parse_log(path):
            opp_name = battle["opponent"]
            try:
                obj(opp_name)
            except KeyError:
                continue
            snaps = [e[1] for e in battle["events"] if e[0] == "snap" and len(e[1]["slots"]) == 5]
            if not snaps:
                continue
            is_boss = opp_name in LEGENDS
            first = snaps[0]["slots"]
            hp_rows.append((opp_name, is_boss, first[0]["max"], obj(opp_name).stats[0]))
            for entry in first:
                stat_rows.append((entry["name"], entry["label"] == "对手", obj(entry["name"]).stats[1:], entry["stats"]))
            # 我方每只不极巨化的最大血量：整场里见到的最小值
            normal_max = defaultdict(lambda: 10**9)
            for s in snaps:
                for i, e in enumerate(s["slots"]):
                    normal_max[(i, e["name"])] = min(normal_max[(i, e["name"])], e["max"])

            tracker = FieldTracker()
            sticky = Counter()  # 这一场里出现过、之后一直排除的情况
            status_names: set[str] = set()
            # 按 snap 切回合
            idx = [k for k, e in enumerate(battle["events"]) if e[0] == "snap" and len(e[1]["slots"]) == 5]
            # 第一次回合数据之前的文字（出场时特性带来的天气、场地）
            for e in battle["events"][: idx[0]]:
                if e[0] == "text":
                    tracker.text(e[1])
            for n, k0 in enumerate(idx):
                s0 = battle["events"][k0][1]
                k1 = idx[n + 1] if n + 1 < len(idx) else None
                events = battle["events"][k0 + 1 : k1] if k1 else battle["events"][k0 + 1 :]
                texts = [e[1] for e in events if e[0] == "text"]
                # 最后一回合没有下一次回合数据：只看倒下的（掉血下限）
                last = k1 is None
                s1 = s0 if last else battle["events"][k1][1]
                slots0, slots1 = s0["slots"], s1["slots"]
                names = [e["name"] for e in slots0]
                if [e["name"] for e in slots1] != names:
                    drop_reasons["两次回合数据之间换了宝可梦"] += 1
                    tracker.end_turn()
                    continue
                zh_names = [zh(x) for x in names]

                # 我方每只这回合用的招式：PP 少了的那个
                used = {}
                for i in range(1, 5):
                    m0, m1 = slots0[i]["moves"], slots1[i]["moves"]
                    if len(m0) != len(m1):
                        continue
                    dec = [j for j in range(len(m0)) if m1[j][1] < m0[j][1]]
                    if len(dec) == 1:
                        used[i] = dec[0]
                    elif len(dec) > 1:
                        used[i] = None
                # 切出每个出手动作
                actions = []
                pre_texts = []
                previous = None
                for t in texts:
                    m = ACTION.match(t)
                    key = re.sub(r"[！!。.\s]", "", t)
                    if m and key == previous:
                        continue  # 同一句识别了两次
                    previous = key
                    if m:
                        actor, move_text = m[1], m[2]
                        ours = "的" in actor
                        short = actor.split("的")[-1] if ours else actor
                        limit = max(1, len(short) // 3)
                        if not ours:
                            slot = 0 if levenshtein(short, zh_names[0]) <= limit else None
                        elif actor.startswith(ME):
                            slot = 1
                        else:
                            scores = {i: levenshtein(short, zh_names[i]) for i in (2, 3, 4)}
                            best = min(scores.values())
                            cands = [i for i, v in scores.items() if v == best and v <= limit]
                            if len(cands) > 1:
                                # 同种的两只：看谁这回合用了这个招式
                                def matches(i):
                                    if used.get(i) is None:
                                        return False
                                    me = obj(names[i])
                                    return any(levenshtein(mv.name("zh-Hans"), move_text.rstrip("！!")) <= 1
                                               for mv in (me.moves[used[i]], me.max_moves[used[i]]))
                                cands = [i for i in cands if matches(i)]
                            slot = cands[0] if len(cands) == 1 else None
                        actions.append(dict(slot=slot, move_text=move_text, after=[], field=None,
                                            screens=dict(tracker.screens), before=list(pre_texts)))
                        actions[-1]["field"] = tracker.field()
                    elif actions:
                        actions[-1]["after"].append(t)
                    tracker.text(t)
                    pre_texts.append(t)
                    if re.search(r"被灼伤|中毒|剧毒", t):
                        status_names.add(t.split("/")[0].split("的")[-1].strip())
                    if "替身" in t:
                        sticky["替身"] += 1
                tracker.end_turn()

                all_text = "\n".join(texts)
                turn_flags = set()
                if re.search(r"混乱", all_text):
                    turn_flags.add("混乱")
                if re.search(r"回复|恢复|吃剩|吸取|体力是全满", all_text):
                    turn_flags.add("回血")
                if re.search(r"反作用|宝珠|头盔|伤害", all_text):
                    turn_flags.add("反伤")
                if re.search(r"袭击了宝可梦们", all_text):
                    turn_flags.add("天气扣血")
                if "吸收了光" in all_text:
                    turn_flags.add("蓄力")
                if sticky["替身"]:
                    turn_flags.add("替身")
                if "帮助" in all_text:
                    turn_flags.add("帮助")
                weather_dmg = any(a["field"].weather in ("sandstorm", "hail") for a in actions) or tracker.weather in ("sandstorm", "hail")
                if weather_dmg:
                    turn_flags.add("沙暴冰雹")

                own_dyn = {}
                for i in range(1, 5):
                    nm = normal_max[(i, names[i])]
                    own_dyn[i] = slots0[i]["max"] > 1.5 * nm or slots1[i]["max"] > 1.5 * nm
                our_actions = [a for a in actions if a["slot"] not in (0,)]
                opp_actions = [a for a in actions if a["slot"] == 0]

                def outcome(a):
                    after = "\n".join(a["after"])
                    return dict(
                        miss="没有击中" in after or "没有效果" in after or "失败" in after or "躲开" in after,
                        crit="要害" in after,
                        multi=bool(re.search(r"击中了\s*\d+\s*次", after)),
                        super="效果绝佳" in after,
                        weak="效果不好" in after,
                        mid_stage=any(re.search(r"提高了|降低了|消除了", t) for t in a["before"]),
                    )

                # ---------- A：对手打我方
                if len(opp_actions) == 1 and opp_actions[0]["slot"] == 0:
                    a = opp_actions[0]
                    o = outcome(a)
                    opp = obj(opp_name)
                    is_max = a["move_text"].startswith("极巨") or a["move_text"].startswith("超极巨")
                    pool = opp.max_moves if is_max else opp.moves
                    cand = [j for j, mv in enumerate(pool) if levenshtein(mv.name("zh-Hans"), a["move_text"]) <= 1]
                    if not cand:
                        drop_reasons["A: 对手招式没认出来"] += 1
                    elif len({pool[j].power for j in cand}) > 1:
                        drop_reasons["A: 极巨招式对应几个威力不同的招式"] += 1
                    elif pool[cand[0]].base_power <= 0:
                        pass
                    elif o["miss"]:
                        drop_reasons["A: 没打中/失败"] += 1
                    else:
                        j = cand[0]
                        move = pool[j]
                        drops = {}
                        unknown = False
                        fainted = set()
                        for i in range(1, 5):
                            if slots0[i]["max"] != slots1[i]["max"]:
                                unknown = True
                                continue
                            drops[i] = slots0[i]["cur"] - slots1[i]["cur"]
                        for t in texts:
                            if "倒下" in t:
                                for i in range(1, 5):
                                    if zh_names[i] in t:
                                        fainted.add(i)
                        hit = [i for i, d in drops.items() if d > 0]
                        # 我方自己的范围招式会打到队友
                        ally_spread = any(
                            used.get(i) is not None and obj(names[i]).moves[used[i]].name_id in ALLY_SPREAD and not own_dyn[i]
                            for i in range(1, 5)
                        )
                        healers = {i for i in range(1, 5) if used.get(i) is not None and obj(names[i]).moves[used[i]].name_id in HEAL_MOVES}
                        spread = move.is_spread and not is_max
                        flags = set(turn_flags)
                        if ally_spread:
                            flags.add("我方范围招式")
                        bad = flags & {"混乱", "反伤", "天气扣血", "沙暴冰雹", "替身", "我方范围招式"}
                        if unknown and not fainted:
                            drop_reasons["A: 有一只极巨化开始/结束"] += 1
                        elif bad:
                            drop_reasons["A: " + "、".join(sorted(bad))] += 1
                        else:
                            targets = []
                            if fainted:
                                for i in fainted:
                                    targets.append((i, True))
                            elif spread:
                                targets = [(i, False) for i in hit]
                            elif len(hit) == 1:
                                targets = [(hit[0], False)]
                            elif not last:
                                drop_reasons[f"A: 单体招式但我方 {len(hit)} 只掉血"] += 1
                            for i, dead in targets:
                                if i in healers or (flags & {"回血"} and len(hit) > 1):
                                    drop_reasons["A: 被打的那只回了血"] += 1
                                    continue
                                if any(zh_names[i] in s for s in status_names):
                                    drop_reasons["A: 被打的那只有灼伤/中毒"] += 1
                                    continue
                                if not dead and slots1[i]["cur"] == 0:
                                    dead = True
                                f = a["field"]
                                pa, pb, pc, raw = predict_pair(opp_name, slots0[0], is_max, j, names[i], slots0[i], f, spread, o["crit"])
                                if a["screens"].get(("own", move.category)):
                                    flags_s = True
                                else:
                                    flags_s = False
                                eff = type_multiplier(move.type_id, obj(names[i]).type_ids)
                                effect_check[(eff > 1, eff < 1, o["super"], o["weak"])] += 1
                                rec = dict(
                                    kind="A", path=battle["path"], time=s0["time"], attacker=opp_name, defender=names[i],
                                    move=move.name_id, move_zh=move.name("zh-Hans"), category=move.category,
                                    is_max=is_max, spread=spread and len(hit) > 1, crit=o["crit"], multi=o["multi"],
                                    mid_stage=o["mid_stage"], screen=flags_s, weather=f.weather, terrain=f.terrain,
                                    actual=slots0[i]["cur"] - slots1[i]["cur"] if not dead else slots0[i]["cur"],
                                    pa=pa, pb=pb, pc=pc, raw=raw, dead=dead, boss=is_boss, cf=move.correction_factor,
                                    def_ability=battle["abilities"][i - 1] if len(battle["abilities"]) == 4 else "?",
                                    att_ability=battle["opp_ability"],
                                    item=battle["items"][i - 1] if len(battle["items"]) == 4 else "?",
                                    stages_att=slots0[0]["stages"], stages_def=slots0[i]["stages"],
                                    flags=flags, frac_a=damage(replace(obj(opp_name), dynamax=is_max), j, replace(obj(names[i]), dynamax=False), f, spread) / accuracy_divisor(move, f),
                                    dmax=slots0[i]["max"], own_dyn=own_dyn[i], data_hp=obj(names[i]).stats[0],
                                )
                                (censored if dead else samples_a).append(rec)
                elif len(opp_actions) > 1:
                    drop_reasons["A: 对手一回合出手两次以上"] += 1

                # ---------- B：我方打对手
                if last:
                    continue
                if slots0[0]["max"] != slots1[0]["max"]:
                    drop_reasons["B: 对手最大血量变了"] += 1
                    continue
                actual = slots0[0]["cur"] - slots1[0]["cur"]
                opp_heal = any(obj(opp_name).moves[j].name_id in HEAL_MOVES for a in opp_actions
                               for j, mv in enumerate(obj(opp_name).moves) if levenshtein(mv.name("zh-Hans"), a["move_text"]) <= 1)
                if opp_heal:
                    drop_reasons["B: 对手用了回血招式"] += 1
                    continue
                if any(zh(opp_name) in s for s in status_names):
                    drop_reasons["B: 对手灼伤/中毒"] += 1
                    continue
                bad = turn_flags & {"天气扣血", "沙暴冰雹", "替身", "蓄力", "混乱", "反伤"}
                if bad:
                    drop_reasons["B: " + "、".join(sorted(bad))] += 1
                    continue
                if any(v is None for v in used.values()):
                    drop_reasons["B: 一只少了两个招式的 PP"] += 1
                    continue
                parts = []
                ok = True
                by_slot = defaultdict(list)
                for a in our_actions:
                    by_slot[a["slot"]].append(a)
                if any(a["slot"] is None for a in our_actions):
                    drop_reasons["B: 我方出手的宝可梦没认出来"] += 1
                    continue
                if set(by_slot) != set(used):
                    drop_reasons["B: PP 和战斗文字对不上"] += 1
                    continue
                any_crit = any_multi = any_mid = any_cf = any_spread = False
                any_screen = False
                maxes = []
                for i, j in used.items():
                    acts = by_slot[i]
                    if len(acts) != 1:
                        ok = False
                        break
                    a = acts[0]
                    o = outcome(a)
                    dyn = own_dyn[i] or a["move_text"].startswith("极巨") or a["move_text"].startswith("超极巨")
                    me = obj(names[i])
                    move = me.max_moves[j] if dyn else me.moves[j]
                    if levenshtein(move.name("zh-Hans"), a["move_text"]) > 1:
                        ok = False
                        drop_reasons["B: 招式名和 PP 对不上"] += 1
                        break
                    base_move = me.moves[j]
                    if move.base_power <= 0 or o["miss"]:
                        continue
                    if base_move.name_id in ALLY_SPREAD and not dyn:
                        any_spread = True
                    if base_move.name_id in HEAL_MOVES:
                        pass
                    f = a["field"]
                    pa, pb, pc, raw = predict_pair(names[i], slots0[i], dyn, j, opp_name, slots0[0], f, base_move.name_id in ALLY_SPREAD and not dyn, o["crit"])
                    any_crit |= o["crit"]
                    any_multi |= o["multi"]
                    any_mid |= o["mid_stage"]
                    any_cf |= move.correction_factor != 1
                    any_screen |= bool(a["screens"].get(("opp", move.category)))
                    maxes.append(dyn)
                    eff = type_multiplier(move.type_id, obj(opp_name).type_ids)
                    effect_check[(eff > 1, eff < 1, o["super"], o["weak"])] += 1
                    parts.append(dict(slot=i, name=names[i], move=move.name_id, move_zh=move.name("zh-Hans"), category=move.category,
                                      is_max=dyn, crit=o["crit"], pa=pa, pb=pb, pc=pc, raw=raw,
                                      item=battle["items"][i - 1] if len(battle["items"]) == 4 else "?",
                                      ability=battle["abilities"][i - 1] if len(battle["abilities"]) == 4 else "?",
                                      weather=f.weather, terrain=f.terrain, type=move.type_id))
                if not ok:
                    drop_reasons["B: 一只出手两次/对不上"] += 1
                    continue
                if not parts:
                    continue
                if actual == 0 and sum(p["pa"] for p in parts) > 0:
                    drop_reasons["B: 有进攻但对手没掉血（守住之类）"] += 1
                    continue
                samples_b.append(dict(
                    kind="B", path=battle["path"], time=s0["time"], defender=opp_name, boss=is_boss, actual=actual,
                    pa=sum(p["pa"] for p in parts), pb=sum(p["pb"] for p in parts), pc=sum(p["pc"] for p in parts), raw=sum(p["raw"] for p in parts), parts=parts,
                    crit=any_crit, multi=any_multi, mid_stage=any_mid, cf=any_cf, ally_spread=any_spread,
                    screen=any_screen, flags=turn_flags, def_ability=battle["opp_ability"],
                ))

    report(samples_a, samples_b, censored, stat_rows, hp_rows, drop_reasons, effect_check)


# ---------------------------------------------------------------- 输出

LOW, HIGH = 0.85 / 0.925, 1 / 0.925


def summary(values: list[float]) -> str:
    if not values:
        return "n=0"
    v = sorted(values)
    q = statistics.quantiles(v, n=4) if len(v) >= 2 else [v[0]] * 3
    inside = sum(LOW - 0.005 <= x <= HIGH + 0.005 for x in v) / len(v)
    return f"n={len(v)} 中位 {statistics.median(v):.3f} 四分位 {q[0]:.3f}～{q[2]:.3f} 在0.92～1.08 {inside:.0%}"


def table(title: str, rows: list[dict], key, which=("raw", "pa", "pc", "pb")) -> None:
    print(f"\n## {title}")
    groups = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    for g in sorted(groups, key=lambda x: (-len(groups[x]), str(x))):
        rs = groups[g]
        line = f"  {g!s:<28}"
        for w in which:
            line += f" | {w}: " + summary([r["actual"] / r[w] for r in rs if r[w] > 0])
        print(line)


def clean_a(r):
    return not (r["crit"] or r["multi"] or r["mid_stage"] or r["screen"] or r["cf"] != 1 or "帮助" in r["flags"] or "回血" in r["flags"])


def clean_b(r):
    return not (r["crit"] or r["multi"] or r["mid_stage"] or r["screen"] or r["cf"] or r["ally_spread"] or "帮助" in r["flags"])


def report(A, B, censored, stat_rows, hp_rows, drop_reasons, effect_check):
    print("# 样本数")
    print(f"A 对手打我方 {len(A)} 条（另有倒下的 {len(censored)} 条只算下限）；B 我方打对手 {len(B)} 回合")
    print("\n# 排除的原因")
    for k, v in drop_reasons.most_common():
        print(f"  {v:5d} {k}")

    print("\n# 能力值：数据（个体值 31、数据性格）÷ 日志实际，[攻 防 特攻 特防 速]")
    for side in (True, False):
        ratios = [[d / a for d, a in zip(data_s, act)] for name, opp, data_s, act in stat_rows if opp == side]
        if ratios:
            cols = list(zip(*ratios))
            print(f"  {'对手' if side else '我方'} n={len(ratios)}: " + "  ".join(
                f"中位 {statistics.median(c):.3f} [{min(c):.2f},{max(c):.2f}] 相同 {sum(abs(x - 1) < 1e-9 for x in c) / len(c):.0%}" for c in cols))

    print("\n# 对手血量倍数：战斗最大血量 ÷ 数据 HP（个体值 31）")
    for boss in (False, True):
        rs = [m / h for _, b, m, h in hp_rows if b == boss]
        if rs:
            print(f"  {'首领' if boss else '路上'} n={len(rs)} 中位 {statistics.median(rs):.3f} 范围 {min(rs):.3f}～{max(rs):.3f}（代码用 {4.18 if boss else 3.8}）")

    print("\n# 相克核对（预测倍率>1, <1, 文字效果绝佳, 文字效果不好）")
    for k, v in sorted(effect_check.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    for name, rows, clean in (("A 对手打我方", A, clean_a), ("B 我方打对手", B, clean_b)):
        print(f"\n\n######## {name}")
        table("全部", rows, lambda r: "全部")
        cl = [r for r in rows if clean(r)]
        table("干净样本（无要害/多段/回合中途能力变化/墙/修正系数/帮助）", cl, lambda r: "干净")
        table("按会心", rows, lambda r: "要害" if r["crit"] else "无要害")
        if name.startswith("A"):
            table("干净 按物理/特殊", cl, lambda r: r["category"])
            table("干净 按极巨招式", cl, lambda r: "极巨招式" if r["is_max"] else "普通招式")
            table("干净 按范围（多只掉血）", cl, lambda r: "范围" if r["spread"] else "单体")
            table("干净 按首领", cl, lambda r: "首领" if r["boss"] else "路上")
            table("干净 按天气", cl, lambda r: r["weather"])
            table("干净 按场地", cl, lambda r: r["terrain"])
            table("干净 按被打方特性", cl, lambda r: r["def_ability"])
            table("干净 按被打方道具", cl, lambda r: r["item"])
            table("干净 按攻击方特性", cl, lambda r: r["att_ability"])
            table("干净 按招式", cl, lambda r: r["move_zh"])
            table("全部 按墙", rows, lambda r: "墙" if r["screen"] else "无墙")
            table("全部 按回合中途能力变化", rows, lambda r: "中途变化" if r["mid_stage"] else "无")
            table("全部 按被打方能力等级（防/特防）", rows, lambda r: tuple(r["stages_def"][1:4:2]) if any(r["stages_def"][1:4:2]) else "没变")
            table("全部 按攻击方能力等级（攻/特攻）", rows, lambda r: tuple(r["stages_att"][0:3:2]) if any(r["stages_att"][0:3:2]) else "没变")
            print("\n## A 按比例：(掉血/战斗最大血量) ÷ (预测/数据 HP ÷ 极巨倍数)，干净样本；raw 是 damage() 原样，pa 是去掉命中率")
            for w in ("raw", "pa"):
                v = [(r["actual"] / r["dmax"]) / (r[w] / r["data_hp"] / (1.9 if r["own_dyn"] else 1)) for r in cl if r[w] > 0]
                print(f"  {w}: " + summary(v))
        else:
            def single(r, f):
                return f(r["parts"][0]) if len(r["parts"]) == 1 else "多只"
            table("干净 按出手只数", cl, lambda r: len(r["parts"]))
            table("干净 只有一只出手 按物理/特殊", cl, lambda r: single(r, lambda p: p["category"]))
            table("干净 按含不含极巨招式", cl, lambda r: "含极巨" if any(p["is_max"] for p in r["parts"]) else "普通")
            table("干净 按首领", cl, lambda r: "首领" if r["boss"] else "路上")
            table("干净 按对手特性", cl, lambda r: r["def_ability"])
            table("干净 只有一只出手 按道具", cl, lambda r: single(r, lambda p: p["item"]))
            table("干净 只有一只出手 按特性", cl, lambda r: single(r, lambda p: p["ability"]))
            table("干净 只有一只出手 按天气", cl, lambda r: single(r, lambda p: p["weather"]))
            table("干净 只有一只出手 按场地", cl, lambda r: single(r, lambda p: p["terrain"]))
            table("干净 只有一只出手 按招式", cl, lambda r: single(r, lambda p: p["move_zh"]))
            table("全部 按墙", rows, lambda r: "墙" if r["screen"] else "无墙")
            table("全部 按帮助", rows, lambda r: "帮助" if "帮助" in r["flags"] else "无")
            table("全部 按回合中途能力变化", rows, lambda r: "中途变化" if r["mid_stage"] else "无")
            table("全部 按多段", rows, lambda r: "多段" if r["multi"] else "无")

    print("\n\n######## 倒下的（实际掉血是下限 = 回合开头剩余血量）")
    print(f"  n={len(censored)}；实际下限 ÷ 预测(b) 的中位 {statistics.median([r['actual'] / r['pb'] for r in censored]) if censored else 0:.3f}")
    for r in censored:
        if "20261121-202446" in r["path"] and r["attacker"] == "absol":
            print(f"  阿勃梭鲁那例 {r['time']} {r['move_zh']} → {r['defender']}：剩余 {r['actual']}，"
                  f"(a) {r['pa']:.1f}（damage() 原样 {r['frac_a'] * accuracy_dummy(r):.3f}，去掉命中率 {r['frac_a']:.3f}），"
                  f"(b) {r['pb']:.1f}（{r['pb'] / r['data_hp']:.3f}），被打方变化 {r['stages_def']}，攻击方变化 {r['stages_att']}，天气 {r['weather']}")

    dump = os.environ.get("V19_DUMP")  # 给了路径就把样本存下来，方便再分析
    if dump:
        with open(dump, "wb") as fh:
            pickle.dump(dict(A=A, B=B, censored=censored), fh)


def accuracy_dummy(r):
    move = next(m for m in obj(r["attacker"]).moves + obj(r["attacker"]).max_moves if m.name_id == r["move"])
    return move.accuracy


if __name__ == "__main__":
    files = sys.argv[1:] or sorted(
        p for p in glob.glob("logs/swsh-lair/start/*.log") if "回合数据" in open(p, encoding="utf-8", errors="replace").read()
    )
    main(files)
