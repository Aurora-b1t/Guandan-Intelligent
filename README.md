# 掼蛋智能分析引擎 (Guandan Intelligent)

掼蛋游戏引擎与 AI 决策系统，支持人机对战、AI 对战和场景化 benchmark 分析。

## 功能

- **完整游戏引擎** — 掼蛋规则实现，包括牌型识别、出牌合法性判断、升级计分
- **多种 AI 智能体** — 启发式 Agent、蒙特卡洛采样 Agent、ISMCTS Agent
- **分层评分模型** — Blind / Informed / Round / Exact / Endgame 五层评分体系
- **候选枚举策略** — Full / Memory / Top-N 三种枚举器可配置
- **Web 对战界面** — Flask 驱动的 Web UI，人类玩家可对阵 3 个 AI
- **Arena 测试场** — 预设残局场景，对比不同模型表现
- **对手建模** — 基于已出牌信息推断对手手牌分布

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 Web 服务
python -m guandan.ui.web.app

# 运行测试
pytest
```

## 项目结构

```
guandan/
├── card.py              # 卡牌编码
├── combo.py             # 牌型定义与比较
├── combo_finder.py      # 从手牌枚举合法出牌候选
├── combo_parser.py      # 牌型输入解析
├── rules.py             # 出牌合法性校验
├── game_state.py        # 游戏状态
├── game.py              # 对局编排
├── table.py             # 桌面状态
├── score.py             # 计分与升级
├── deck.py              # 牌堆
├── constants.py         # 游戏常量
├── state_utils.py       # 状态操作工具
├── logging.py           # 日志
├── ai/
│   ├── agent.py         # AI Agent（Heuristic / MonteCarlo / ISMCTS）
│   ├── scorer.py        # 出牌评分入口
│   ├── hand_eval.py     # 手牌质量评估
│   ├── opponent.py      # 对手手牌推断
│   ├── player_view.py   # 玩家视角状态
│   ├── candidate_enum.py# 候选枚举器
│   ├── memory_enumerator.py
│   ├── constrained_sampler.py
│   ├── sampler.py       # 手牌采样
│   ├── registry.py      # 模型注册
│   ├── params.py        # 可配置参数
│   ├── action_log.py
│   ├── ismcts.py        # ISMCTS 搜索
│   ├── mc_decider.py    # 蒙特卡洛决策
│   └── models/
│       ├── interface.py     # 评分模型接口
│       ├── blind_scorer.py  # 盲评（不模拟）
│       ├── informed_scorer.py# 知情评分
│       ├── round_scorer.py  # 回合级评分
│       └── endgame_solver.py# 残局精确求解
├── arena/
│   └── scenarios.py     # Arena 场景库
└── ui/
    ├── interactive.py   # 交互式对局接口
    └── web/
        ├── app.py       # Flask 主应用
        ├── arena_api.py # Arena API
        ├── templates/
        │   ├── menu.html
        │   ├── game.html
        │   └── arena.html
        └── static/
            ├── style.css
            └── game.js

tests/
├── test_core.py         # 核心引擎测试
├── test_ai.py           # AI 决策测试
└── arena/
    └── scenarios.py     # 场景定义测试

config.json              # AI 模型参数配置
```

## 配置

通过 `config.json` 配置 AI 行为，包括：

- **decider** — Agent 级别参数（默认模型、时间限制等）
- **inner_model** — 各评分模型的超参（奖励/惩罚权重）
- **enumerator** — 候选枚举策略

## 技术栈

- Python 3.x
- Flask + Gunicorn（Web 服务）
- pytest（测试）

## 掼蛋规则简介

掼蛋是一种四人结对扑克游戏，使用两副牌（共 108 张）。支持多种牌型：单张、对子、三同张、顺子、连对、钢板、炸弹、同花顺、火箭等。每局升级制，先打到 A 的团队获胜。
