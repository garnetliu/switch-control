# 修改记录

## 2026-11-09

- `src/libs/game_state.py`：`clear` 的 `seed`、`boss` 改成可选参数。
- `src/shiny_steps/join.py`：`sw.game.maps.route` 改成 `sw.game.maps["route"]`。
- `src/tools/log.py`：日志文件改到 `logs/<名字>/<时间>.log`，`start` 的日志放进 `logs/start/`。
