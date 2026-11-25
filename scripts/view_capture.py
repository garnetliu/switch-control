"""在 Mac 上开一个窗口，实时显示采集卡的画面。在窗口里按 q 关掉。

用 .env 里的 CAPTURE_DEVICE（不写是 0）。和脚本同时读同一张采集卡没问题，
macOS 允许几个程序一起读同一个摄像头。读不到画面（Switch 休眠、采集卡拔了）时隔一秒重新打开。
"""

import time

import cv2

from control_switch.settings import load_settings

# 窗口里显示的大小
WIDTH, HEIGHT = 1280, 720
# 连续读不到多少帧就重新打开采集卡
MAX_FAILS = 30


def main() -> None:
    index = load_settings().capture_device
    while True:
        video = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
        video.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        video.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        fails = 0
        while fails <= MAX_FAILS:
            ok, frame = video.read()
            if not ok or frame is None:
                fails += 1
                time.sleep(0.1)
                continue
            fails = 0
            cv2.imshow("Switch", cv2.resize(frame, (WIDTH, HEIGHT)))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                video.release()
                cv2.destroyAllWindows()
                return
        video.release()
        time.sleep(1)


if __name__ == "__main__":
    main()
