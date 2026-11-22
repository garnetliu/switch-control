"""从每局日志里取首领战的数据：四只是谁、血量、打了几回合、首领战倒下几次、输赢。写到 /tmp/turns_data.json。"""
import ast, glob, json, re
out = []
for f in sorted(glob.glob("logs/swsh-lair/start/*.log")):
    t = open(f, encoding="utf-8", errors="replace").read()
    rep = re.search(r"第 (\d+) 轮战报：\n(胜|负)[^，]*，倒下 (\d+) 次，([\d.]+) 分钟，抓到 (\d)/4", t)
    teams = list(re.finditer(r"队伍: (\[.*?\])，自己的 PP", t))
    if not rep or len(teams) < 1: continue
    boss = "tapu-bulu" if "卡璞・哞哞" in t else "mewtwo"
    caught = int(rep[5])
    # 每场战斗开头有一行「队伍:」；打到首领 = 有 4 行
    fights = []
    for i, m in enumerate(teams):
        seg = t[m.end(): teams[i + 1].start() if i + 1 < len(teams) else len(t)]
        fights.append(dict(team=ast.literal_eval(m[1]), turns=len(re.findall(r"INFO: 用第 \d 个招式", seg)),
                           faints=len(re.findall(r"有一只倒下了", seg)), dmax="INFO: 极巨化" in seg))
    out.append(dict(file=f.split("/")[-1], boss=boss, win=rep[2] == "胜", falls=int(rep[3]), minutes=float(rep[4]), caught=caught, fights=fights))
json.dump(out, open("/tmp/turns_data.json", "w"), ensure_ascii=False)
import collections
print(len(out), collections.Counter((g["boss"], len(g["fights"])) for g in out))
b = [g for g in out if len(g["fights"]) == 4]
print("首领战回合数分布", {bs: sorted(collections.Counter(g["fights"][3]["turns"] for g in b if g["boss"] == bs).items()) for bs in ("mewtwo", "tapu-bulu")})
print("首领战自己极巨化的比例", {bs: round(sum(g["fights"][3]["dmax"] for g in b if g["boss"] == bs) / max(1, sum(1 for g in b if g["boss"] == bs)), 2) for bs in ("mewtwo", "tapu-bulu")})
print("各关自己极巨化的比例", [round(sum(g["fights"][i]["dmax"] for g in out if len(g["fights"]) > i) / sum(1 for g in out if len(g["fights"]) > i), 2) for i in range(4)])
