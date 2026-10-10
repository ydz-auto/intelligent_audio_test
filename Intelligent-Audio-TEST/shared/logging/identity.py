# -*- coding: utf-8 -*-
"""写入进程唯一标识（INT-81 审计问题 1 二次修复：容器多副本维度）。

活跃文件名/业务文件名的进程标识段统一为 {hostname}-{pid}：
- 同宿主多进程（多 worker、本地多服务）靠 PID 区分
- 容器多副本（compose 共享日志卷 + deploy.replicas）每个副本容器有独立
  PID namespace，服务进程即容器入口进程、PID 恒为 1 —— PID 跨容器必然
  重号；Docker 默认以短容器 ID 注入主机名，hostname 跨容器互异，与 PID
  合取后全局唯一
- hostname 做文件名安全清洗（Docker 短 ID/RFC-1123 主机名天然合法，
  此为防御性兜底），拒绝魔法拼接
"""
import os
import re
import socket

_HOSTNAME_SAFE_RE = re.compile(r'[^A-Za-z0-9._-]')


def process_hostname() -> str:
    """当前写入方主机名（容器场景即 Docker 注入的短容器 ID），文件名安全。"""
    cleaned = _HOSTNAME_SAFE_RE.sub('_', socket.gethostname()).strip('._')
    return cleaned or 'localhost'


def process_identity() -> str:
    """跨副本/跨进程唯一标识：{hostname}-{pid}。"""
    return f'{process_hostname()}-{os.getpid()}'
