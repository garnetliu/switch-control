"""测 botbase 的读写内存、截图、按键反应速度，USB 和 Wi-Fi 用同一个脚本。

用法：PYTHONPATH=src uv run python docs/实测脚本/botbase速度.py usb|wifi
Wi-Fi 读 .env 的 SWITCH_IP、SWITCH_PORT。
要求：剑盾停在极巨大冒险的大厅里自由走动的状态（按 X 会打开菜单、按 B 会关上）。
写内存是把道具口袋原样读出来再原样写回去，写完核对一遍；写之前先把道具口袋存到 run/ 里。
USB 上一次写 0x898 字节（命令约 4.4KB）会 Pipe error、usb-botbase 断开重连，所以写最多测到 0x400。
"""

import io
import os
import statistics
import sys
import time

from dotenv import load_dotenv
from PIL import Image, ImageChops, ImageStat

from control_switch.device.botbase import _UsbConnection, _WifiConnection

load_dotenv()
mode = sys.argv[1] if len(sys.argv) > 1 else "usb"
if mode == "usb":
    conn = _UsbConnection()
else:
    conn = _WifiConnection(os.environ["SWITCH_IP"], int(os.environ["SWITCH_PORT"]))

ITEMS = 0x45067A98 + 0x2F8  # 道具口袋
POUCH = 550 * 4


def timed(fn, times):
    result = []
    for _ in range(times):
        t = time.perf_counter()
        fn()
        result.append(time.perf_counter() - t)
    return result


def show(name, seconds, size=None):
    ms = [s * 1000 for s in seconds]
    line = f"{name}：中位 {statistics.median(ms):.1f} ms，最快 {min(ms):.1f}，最慢 {max(ms):.1f}"
    if size:
        line += f"，{size / statistics.median(seconds) / 1024:.0f} KB/s"
    print(line)


def peek(offset, size):
    return conn.request(f"peek {offset:#x} {size:#x}")


def screen():
    return Image.open(io.BytesIO(conn.request("pixelPeek"))).convert("L").resize((320, 180))


def differs(a, b):
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0] > 3


print(f"== {mode}")
print("读内存（peek）")
for size in (4, 0x158, 0x1000, 0x4000, 0x10000):
    show(f"  {size:#x} 字节", timed(lambda: peek(ITEMS, size), 20), size)

print("写内存（poke，原样写回道具口袋）")
original = peek(ITEMS, POUCH)
with open(f"run/道具口袋-备份-{mode}.bin", "wb") as f:
    f.write(original)
for size in (4, 0x158, 0x400):
    data = original[:size]
    show(f"  {size:#x} 字节（不等回复）", timed(lambda: conn.send(f"poke {ITEMS:#x} 0x{data.hex()}"), 20), size)
    show(f"  {size:#x} 字节 + 读 4 字节确认", timed(lambda: (conn.send(f"poke {ITEMS:#x} 0x{data.hex()}"), peek(ITEMS, 4)), 20))
assert peek(ITEMS, POUCH) == original, "道具口袋变了"
print("  写完核对：道具口袋没变")

print("截图（pixelPeek）")
show("  一张", timed(lambda: conn.request("pixelPeek"), 20))

print("按键（按 X 到画面变化）")
send_times, react_times, shots = [], [], []
for _ in range(10):
    base = screen()
    t = time.perf_counter()
    conn.send("click X")
    send_times.append(time.perf_counter() - t)
    count = 0
    while True:
        count += 1
        if differs(screen(), base):
            break
        if time.perf_counter() - t > 5:
            raise RuntimeError("按 X 5 秒画面都没变")
    react_times.append(time.perf_counter() - t)
    shots.append(count)
    time.sleep(1.0)
    conn.send("click B")
    t = time.perf_counter()
    while differs(screen(), base) and time.perf_counter() - t < 5:
        pass
    time.sleep(1.0)
show("  click 命令发出去", send_times)
show("  发出 click 到截图里看到菜单", react_times)
print(f"  每次看到变化前截了 {statistics.median(shots)} 张（中位）")
conn.close()
