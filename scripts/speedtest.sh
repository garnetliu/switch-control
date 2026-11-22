#!/bin/bash
# 用 Ookla speedtest 测封顶网速，跟手机测速 app 同一套：自动选就近电信/联通高速
# 节点、多连接打满。测速前临时关掉 macOS 系统代理（Clash Verge 那层，否则 Ookla
# 走 CFNetwork 会被导到代理节点，测出来是香港线路），测完（含 Ctrl-C 中断）自动恢复。
#
# 测出的上限取决于你用哪台机器、走哪个口：
#   - M1 的 Wi-Fi：封顶 ~600-900 Mbps（网卡物理限，测不到 2000）
#   - 2.5G 有线网卡：~2300-2400（2.5G 线速扣开销）
#   - 要到 2000+：必须有线 2.5G 以上，或 Wi-Fi 7 宽频空口
#
# 用法：scripts/speedtest.sh [-s 服务器ID]   不带参数自动选最近的
# 注意：改系统代理在部分机器上需要管理员，若报错就在前面加 sudo。

SPEEDTEST=$(command -v speedtest)
SERVER_ARG=""
[ "$1" = "-s" ] && [ -n "$2" ] && SERVER_ARG="-s $2"

LOG_DIR="$(cd "$(dirname "$0")/.." && pwd)/logs/speedtest"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date '+%Y%m%d_%H%M%S').log"

DEV=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
GW=$(route -n get default 2>/dev/null | awk '/gateway:/{print $2}')
WIFI_DEV=$(networksetup -listallhardwareports | awk '/Wi-Fi/{getline; print $2}')
SVC=$(networksetup -listnetworkserviceorder 2>/dev/null | awk -v d="$DEV" '
  /^\([0-9]+\)/{name=$0; sub(/^\([0-9]+\) /,"",name)}
  $0 ~ ("Device: " d "\\)") {print name; exit}')

# 每行独立刷进终端和日志，避免多字节字符在管道缓冲里被切断
say() { printf '%s\n' "$1" | tee -a "$LOG"; }

PROXY_RESTORED=0
restore_proxy() {
  [ "$PROXY_RESTORED" = 1 ] && return
  PROXY_RESTORED=1
  [ -z "$SVC" ] && return
  [ "$WEB" = Yes ] && networksetup -setwebproxystate "$SVC" on
  [ "$SEC" = Yes ] && networksetup -setsecurewebproxystate "$SVC" on
  [ "$SKS" = Yes ] && networksetup -setsocksfirewallproxystate "$SVC" on
}

: > "$LOG"

if [ -z "$SPEEDTEST" ]; then
  say "没装 Ookla speedtest：brew tap teamookla/speedtest && brew trust teamookla/speedtest && brew install speedtest"
  exit 1
fi

say "时间：$(date '+%Y-%m-%d %H:%M:%S')"
say "接口 $DEV  服务 ${SVC:-未知}  IP $(ipconfig getifaddr "$DEV" 2>/dev/null)  网关 $GW"
if [ "$DEV" = "$WIFI_DEV" ]; then
  say "连接方式：Wi-Fi（这台 M1 封顶约 600-900 Mbps，测不到 2000）"
  system_profiler SPAirPortDataType 2>/dev/null \
    | awk '/Current Network Information:/{f=1} f&&/Other Local/{exit} f' \
    | grep -E "PHY Mode|Channel|Signal|Transmit Rate" | sed 's/^ */  /' | tee -a "$LOG"
else
  say "连接方式：有线"
  ifconfig "$DEV" 2>/dev/null | grep media | sed 's/^[[:space:]]*/  协商速率：/' | tee -a "$LOG"
fi

# 只有确实开着系统代理才关（记录原状态，trap 保证恢复）；没开就不碰
if [ -n "$SVC" ]; then
  WEB=$(networksetup -getwebproxy "$SVC" 2>/dev/null | awk '/^Enabled/{print $2}')
  SEC=$(networksetup -getsecurewebproxy "$SVC" 2>/dev/null | awk '/^Enabled/{print $2}')
  SKS=$(networksetup -getsocksfirewallproxy "$SVC" 2>/dev/null | awk '/^Enabled/{print $2}')
  if [ "$WEB" = Yes ] || [ "$SEC" = Yes ] || [ "$SKS" = Yes ]; then
    trap restore_proxy EXIT INT TERM
    [ "$WEB" = Yes ] && networksetup -setwebproxystate "$SVC" off 2>/dev/null
    [ "$SEC" = Yes ] && networksetup -setsecurewebproxystate "$SVC" off 2>/dev/null
    [ "$SKS" = Yes ] && networksetup -setsocksfirewallproxystate "$SVC" off 2>/dev/null
    say "检测到系统代理, 已临时关闭 web=$WEB secure=$SEC socks=$SKS, 测完恢复"
  else
    say "没开系统代理，直接测"
  fi
fi
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
say "────────────────────────────────────────"

"$SPEEDTEST" --accept-license --accept-gdpr --progress=no $SERVER_ARG 2>&1 | tee -a "$LOG"

restore_proxy
say "报告已保存：$LOG"
