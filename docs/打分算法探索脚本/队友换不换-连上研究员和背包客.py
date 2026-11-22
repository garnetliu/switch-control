"""整串连起来算：每抓一只一组、研究员一组、背包客一组，和日志里队友的变化对。"""
import ast, collections, glob, itertools, re, sys
src = open("docs/打分算法探索脚本/队友换不换-从seed算.py").read()
src = src[:src.index("zh = {}")]
exec(src)
zh = {}; runs = {}
for f in sorted(glob.glob("logs/swsh-lair/start/*.log")) + sys.argv[1:]:
    t = open(f, encoding="utf-8", errors="replace").read()
    for p in re.split(r"(?=读取到的 seed 是 \d+)", t)[1:]:
        seed = int(re.match(r"读取到的 seed 是 (\d+)", p)[1])
        boss = "tapu-bulu" if ("卡璞" in p or "tapu-bulu" in p) else "mewtwo"
        parts = p.split("队伍: [")
        teams = [[n for n, _ in ast.literal_eval("[" + x.split("]，自己的 PP")[0] + "]")] for x in parts[1:]]
        route = re.search(r"\n路线：(.*)\n", p)
        if not route or len(teams) < 2: continue
        d = D[boss]
        if boss not in zh: zh[boss] = {d.pokemon_object(n).name("zh-Hans"): n for n in d.rental_damages()}
        opp = [zh[boss].get(x.strip()) for x in route[1].split("→")]
        events = []
        def path_events(seg):
            found = sorted((m.start(), kind) for kind, pat in (("研", "研究员："), ("背", "背包客的道具"), ("果", "树果的对话")) for m in re.finditer(pat, seg))
            out = []
            for _, kind in found:
                if not out or out[-1] != kind: out.append(kind)
            return out
        for kind in path_events(parts[0]): events.append((kind, None, None))
        ok = True
        for i in range(1, len(teams)):
            if i - 1 >= len(opp) or opp[i - 1] is None: ok = False; break
            caught = opp[i - 1]; own = teams[i][0] != teams[i - 1][0]
            before, after = teams[i - 1][1:], teams[i][1:]
            kinds = path_events(parts[i])
            changed = [k for k in range(3) if before[k] != after[k]]
            taker = next((k for k in changed if after[k] == caught), None)
            sci = [k for k in changed if after[k] != caught]
            events.append(("抓", "自己" if own else taker, caught))
            for kind in kinds:
                if kind == "研": events.append(("研", sci[0] if len(sci) == 1 else None, after[sci[0]] if len(sci) == 1 else None))
                else: events.append((kind, None, None))
        if ok and events: runs.setdefault((boss, seed, tuple((e[0], e[1] == "自己") for e in events)), events)
print("局:", len(runs), "；研究员:", sum(e[0] == "研" for ev in runs.values() for e in ev), "；背包客:", sum(e[0] == "背" for ev in runs.values() for e in ev), "；树果:", sum(e[0] == "果" for ev in runs.values() for e in ev))
streams = {}; picks = {}
def get(boss, seed):
    if (boss, seed) not in streams:
        raw, names = stream(Longer(D[boss], seed), 110); streams[(boss, seed)] = raw; picks[(boss, seed)] = names
    return streams[(boss, seed)], picks[(boss, seed)]
def draw(raw, pos, top):
    mask = (1 << top.bit_length()) - 1
    while True:
        value = raw[pos] & mask; pos += 1
        if value <= top: return value, pos
def tie(raw, pos, want):
    for _ in range(60):
        w = raw[pos] & 3; pos += 1
        if w >= 1 and (w - 1) in want: return w - 1, pos
    return None, pos
def simulate(boss, seed, events, pack, berry, sci_lead, sci_pick_always, sci_extra):
    raw, names = get(boss, seed); pos = 1 if boss == "tapu-bulu" else 0; out = []
    for kind, who, name in events:
        if kind == "抓":
            _, pos = draw(raw, pos, 2)
            want = [k for k in range(3) if (raw[pos + k] & 1) == 0]; pos += 3
            got = None
            if want: got, pos = tie(raw, pos, want)
            out.append(("抓", got, None))
        elif kind == "研":
            if sci_lead: _, pos = draw(raw, pos, 2)
            want = [k for k in range(3) if (raw[pos + k] & 1) == 0]; pos += 3
            got = None
            if want: got, pos = tie(raw, pos, want)
            mon = None
            if want or sci_pick_always: mon = names[pos]; pos += 1 + sci_extra
            out.append(("研", got, mon))
        elif kind == "背": pos += pack; out.append(("背", None, None))
        else: pos += berry; out.append(("果", None, None))
    return out
res = []
for pack, berry, sci_lead, always, extra in itertools.product(range(0, 9), range(0, 3), (False, True), (False, True), (0, 1)):
    stat = collections.Counter()
    for (boss, seed, sig), events in runs.items():
        sim = simulate(boss, seed, events, pack, berry, sci_lead, always, extra); good = True
        for (kind, who, name), (_, got, mon) in zip(events, sim):
            if kind == "抓" and who != "自己":
                stat["抓总"] += 1; stat["抓对"] += got == who
            if kind == "研" and name is not None:
                stat["研总"] += 1; stat["研对"] += (mon == name); stat["研人对"] += (got == who)
    res.append((stat["研对"] + stat["抓对"], pack, berry, sci_lead, always, extra, dict(stat)))
for score, pack, berry, sci_lead, always, extra, stat in sorted(res, key=lambda r: -r[0])[:8]:
    print(f"背包客占 {pack} 个，树果占 {berry} 个，研究员开头{'有' if sci_lead else '没有'} 0～2 的抽数，没人想要时{'也' if always else '不'}抽那只，抽完多占 {extra} 个 → 抓到的给谁 {stat.get('抓对',0)}/{stat.get('抓总',0)}，研究员给哪只 {stat.get('研对',0)}/{stat.get('研总',0)}，换的是哪个队友 {stat.get('研人对',0)}/{stat.get('研总',0)}")

print("\n=== 背包客到底占几个：只有一个背包客、它之前全对的局，看占几个能让它后面的都对上 ===")
def simulate2(boss, seed, events, pack_k):
    raw, names = get(boss, seed); pos = 1 if boss == "tapu-bulu" else 0; out = []; pack_pos = None
    for kind, who, name in events:
        if kind == "抓":
            _, pos = draw(raw, pos, 2); want = [k for k in range(3) if (raw[pos + k] & 1) == 0]; pos += 3
            got = None
            if want: got, pos = tie(raw, pos, want)
            out.append(got)
        elif kind == "研":
            want = [k for k in range(3) if (raw[pos + k] & 1) == 0]; pos += 3
            got = None; mon = None
            if want: got, pos = tie(raw, pos, want); mon = names[pos]; pos += 1
            out.append(mon)
        elif kind == "背": pack_pos = pos; pos += pack_k; out.append(None)
        else: out.append(None)
    return out, pack_pos
tally = collections.Counter(); detail = []
for (boss, seed, sig), events in runs.items():
    kinds = [e[0] for e in events]
    if kinds.count("背") != 1: continue
    at = kinds.index("背")
    def check(sim, lo, hi):
        n = ok = 0
        for (kind, who, name), got in list(zip(events, sim))[lo:hi]:
            if kind == "抓" and who != "自己": n += 1; ok += got == who
            if kind == "研" and name is not None: n += 1; ok += got == name
        return n, ok
    sim0, _ = simulate2(boss, seed, events, 0)
    n_before, ok_before = check(sim0, 0, at)
    if ok_before != n_before: continue
    fits = []
    for k in range(0, 13):
        sim, pack_pos = simulate2(boss, seed, events, k); n, ok = check(sim, at + 1, len(events))
        if n and ok == n: fits.append(k)
    n_after = check(sim0, at + 1, len(events))[0]
    if n_after >= 1:
        raw, _ = get(boss, seed); _, pack_pos = simulate2(boss, seed, events, 0)
        detail.append((n_after, fits, [raw[pack_pos + j] & 7 for j in range(8)]))
        for k in fits: tally[k] += 1
print("可用的局:", len(detail), "；各种占法能对上的局数:", sorted(tally.items()))
for n_after, fits, low in sorted(detail, key=lambda x: -x[0])[:14]: print(f"   后面能验证 {n_after} 件，对得上的占法 {fits}，背包客开始处 8 个随机数的低 3 位 {low}")
