import collections

src = open("docs/打分算法探索脚本/队友换不换-连上研究员和背包客.py").read()
src = src[: src.index("res = []\nfor pack, berry")]

exec(src)


def simulate3(boss, seed, events, pack_rule):
    raw, names = get(boss, seed)
    pos = 1 if boss == "tapu-bulu" else 0
    out = []
    for kind, who, name in events:
        if kind == "抓":
            _, pos = draw(raw, pos, 2)
            want = [k for k in range(3) if (raw[pos + k] & 1) == 0]
            pos += 3
            got = None
            if want:
                got, pos = tie(raw, pos, want)
            out.append((got, None))
        elif kind == "研":
            want = [k for k in range(3) if (raw[pos + k] & 1) == 0]
            pos += 3
            got = mon = None
            if want:
                got, pos = tie(raw, pos, want)
                mon = names[pos]
                pos += 1
            out.append((got, mon))
        elif kind == "背":
            if pack_rule == "三个队友各抽一个 0～4":
                for _ in range(3):
                    _, pos = draw(raw, pos, 4)
            elif pack_rule == "三个队友各抽一个 0～4，不能重复":
                taken = []
                while len(taken) < 3:
                    value, pos = draw(raw, pos, 4)
                    if value not in taken:
                        taken.append(value)
            elif pack_rule == "四个人各抽一个 0～4":
                for _ in range(4):
                    _, pos = draw(raw, pos, 4)
            elif isinstance(pack_rule, int):
                pos += pack_rule
            out.append((None, None))
        else:
            out.append((None, None))
    return out


for rule in (
    "三个队友各抽一个 0～4",
    "三个队友各抽一个 0～4，不能重复",
    "四个人各抽一个 0～4",
    4,
    0,
):
    stat = collections.Counter()
    for (boss, seed, sig), events in runs.items():
        sim = simulate3(boss, seed, events, rule)
        after = False
        for (kind, who, name), (got, mon) in zip(events, sim):
            tag = "背包客之后" if after else "背包客之前"
            if kind == "背":
                after = True
            if kind == "抓" and who != "自己":
                stat[tag + "抓总"] += 1
                stat[tag + "抓对"] += got == who
            if kind == "研" and name is not None:
                stat[tag + "研总"] += 1
                stat[tag + "研对"] += mon == name
    print(
        f"背包客: {rule if isinstance(rule, str) else f'固定占 {rule} 个'} → 之前: 抓 {stat['背包客之前抓对']}/{stat['背包客之前抓总']}，研究员 {stat['背包客之前研对']}/{stat['背包客之前研总']}；之后: 抓 {stat['背包客之后抓对']}/{stat['背包客之后抓总']}，研究员 {stat['背包客之后研对']}/{stat['背包客之后研总']}"
    )
