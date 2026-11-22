"""测试：研究员那里选「不指定」打一整局，看开头第一次抽数的上限是多少、随机到的是哪只神兽。只打一局就退出。
刷闪程序停着的时候才能跑。日志照常写在 logs/swsh-lair/start/ 里，本脚本的发现用「不指定测试」开头。"""
import logging, sys
from dotenv import load_dotenv

load_dotenv("/Users/garnet/projects/control-switch/.env")
from control_switch.log import init_log
from scripts import load_script

script = load_script("swsh/lair")
join = sys.modules["swsh.lair.steps.join"]

def select_boss(sw, target):
    """菜单是 Lair note 里的神兽，最后一项是「不指定」；选最后一项。名字先用第一项占位，真正的首领后面从内存读。"""
    species = [int.from_bytes(sw.peek(address, 2), "little") for address in sw.config.addresses.lair_notes]
    by_id = {boss.id_num: name_id for name_id, boss in sw.data.boss_pokemon().items()}
    menu = [by_id[number] for number in species if number in by_id]
    logging.warning(f"不指定测试：Lair note {species}，菜单里的神兽 {menu}，选第 {len(menu) + 1} 项「不指定」")
    return menu[0], len(menu)

def read_boss(sw):
    by_id = {boss.id_num: name_id for name_id, boss in sw.data.boss_pokemon().items()}
    try:
        raw = sw.pointer_peek(list(sw.config.addresses.boss_pointer), sw.pkhex.PK8_SIZE)
        record = sw.pkhex.parse_pk8_batch([raw])[0]
    except Exception as error:
        logging.warning(f"不指定测试：首领没从内存读出来：{error!r}")
        return None
    logging.warning(f"不指定测试：内存里的首领 species={record['species']} form={record['form']} 校验={record['checksumValid']}")
    return by_id.get(record["species"]) if record["checksumValid"] else None

original_starter = join._select_starter
def select_starter(sw, boss):
    real = None
    logging.warning(f"不指定测试：这一局的首领按 {real or boss} 算" + ("" if real else "（没读出来，用占位的）"))
    return original_starter(sw, real or boss)

original_matching = join._matching_lair
def matching(sw, seed, shown):
    """配置里的上限对不上就换别的上限试，记下是哪个对上的。"""
    for top in (22, 23, 21, 24, 25):
        sw.config.lair_first_draw_top = top
        try:
            lair = original_matching(sw, seed, shown)
        except RuntimeError:
            continue
        logging.warning(f"不指定测试：seed {seed}，界面上的三只 {shown}，开头抽数的上限 {top} 对上了")
        return lair
    raise RuntimeError(f"不指定测试：seed {seed} 界面上的三只 {shown}，上限 21 到 25 都对不上")

join._select_boss = select_boss
join._select_starter = select_starter
join._matching_lair = matching
sw = script.connect()
init_log(sw, "start")
step = script.START
try:
    while step in script.STEPS:
        sw.step = step
        following = script.STEPS[step](sw)
        if step == "select_pokemon":
            logging.warning("不指定测试：这一局打完了，退出")
            break
        step = following
finally:
    sw.close()
