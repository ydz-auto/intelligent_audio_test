# -*- coding: utf-8 -*-
"""mock_services — 独立 mock 替身服务（INT-137）。

供实机验收、联调与回归使用，解除对真实第三方评估服务与真实 Realtime 产品的依赖：
- mock_third_party_eval  第三方评估 C 区替身（HTTP，:5099）
- mock_realtime_api      Realtime 被测产品替身（WebSocket，:5098）

红线：生产路径零引用 —— 任何生产服务不得 import 本包；不进生产 docker-compose
编排与镜像；由 run_all.py 按 MOCK_SERVICES_ENABLED=true 可选启动。
"""
