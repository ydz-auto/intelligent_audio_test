# -*- coding: utf-8 -*-
"""INT-399 UI 实测：播放设备页签自动健康检查恢复 + 浏览器控制台零 SEVERE。

背景：GET /playback-devices/check-status 被 GET /{device_id} 路由吞掉恒 422
（api_gateway/routes/playback_bp.py 注册顺序冲突），前端调用链
deviceFetching.ts PLAYBACK 分支 autoHealthCheck → playbackApi.checkStatus()
恒 422 → 控制台 SEVERE 链：network 422 → [API Fetch Error] → 自动健康检查失败
→ Uncaught (in promise)。修复（字面路由先于动态路由注册）后应恢复。

本用例（真实浏览器走查主流程，断言可见状态）：
1. API 造 1 个播放设备（status=online，进隔离库 playback_devices 表；
   与本卡数据卫生口径一致，teardown 软删清理，库内零残留）；
2. 打开设备管理页 → 切「播放设备管理」页签；
3. 等设备卡片渲染 + 自动健康检查跑完：状态徽章由「在线」刷新为「离线」
   （隔离栈 audio_service 无物理设备，checkStatus 返回 offline——可见状态
   断言，非仅 DOM 存在）；
4. 读浏览器 console：断言零 SEVERE（无 422 / [API Fetch Error] /
   自动健康检查失败 / Uncaught (in promise)）；
5. 直接请求网关 GET /playback-devices/check-status → 200（双层校验）。

只读语义补充：仅造数/删数，不触发任何真实播放/测试动作。
"""
import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from tests.ui.pages.base_page import BasePage
from tests.ui.utils.api_client import unique_suffix

PLAYBACK_TAB_TEXT = '播放设备管理'
DEVICE_ROUTE = '/Device'
STATUS_BADGE = '.status-badge'

# 控制台 SEVERE 判定模式（修复前实机取证链：network 422 → [API Fetch Error]
# → 自动健康检查失败 → Uncaught (in promise)）
SEVERE_PATTERNS = (
    'check-status', '422', '[API Fetch Error]', '自动健康检查失败',
    'Uncaught (in promise)', '播放设备健康检查',
)


def _find_device_card(page: BasePage, name: str):
    """按设备名定位设备卡片（`.device-card` 内的 `.device-name` 匹配）。"""
    for card in page.find_all('.device-card'):
        if not card.is_displayed():
            continue
        names = card.find_elements(By.CSS_SELECTOR, '.device-name')
        if names and name in (names[0].text or ''):
            return card
    return None


def _create_playback_device(api_client) -> dict:
    """API 造 1 个播放设备，返回 {id, name, unique_id}；失败即报错（栈未就绪暴露）。"""
    suffix = unique_suffix()
    name = f'ui399播放设备_{suffix}'
    body = {
        'name': name,
        'model': 'ui399-model',
        'device_type': 'dry',
        'sample_rate': 48000,
        'device_unique_id': f'UI399-{suffix}',
        'channel_index': 0,
        'status': 'online',
    }
    data = api_client.request('POST', '/playback-devices', body)
    dev_id = str((data.get('data') or {}).get('id'))
    assert dev_id, f'API 造播放设备失败: {str(data)[:200]}'
    return {'id': dev_id, 'name': name}


def _cleanup_playback_device(api_client, dev_id):
    """软删播放设备（进回收站语义）；尽力而为，不吞原始测试结论。"""
    try:
        api_client.request('DELETE', f'/playback-devices/{dev_id}')
    except Exception:
        pass


def _badge_offline(page: BasePage, name: str) -> bool:
    card = _find_device_card(page, name)
    if card is None:
        return False
    badges = card.find_elements(By.CSS_SELECTOR, STATUS_BADGE)
    return bool(badges and '离线' in (badges[0].text or ''))


def _severe_messages(page: BasePage) -> list:
    logs = page.driver.get_log('browser')
    return [e.get('message', '') for e in logs if e.get('level') == 'SEVERE']


def _bad_severe(messages: list) -> list:
    return [m for m in messages if any(p in m for p in SEVERE_PATTERNS)]


def test_playback_tab_health_check_console_zero_severe(page, api_client):
    """播放设备页签自动健康检查恢复 + 控制台零 SEVERE（INT-399 验收 2/3）。"""
    dev = _create_playback_device(api_client)
    try:
        # 网关直验：check-status 恢复 200（后端契约，双层校验之一）
        r = api_client.request('GET', '/playback-devices/check-status')
        items = r.get('data') or []
        assert r.get('code') == 0 and isinstance(items, list), \
            f'网关 check-status 应 200 状态数组，实际: {str(r)[:200]}'
        my = [it for it in items if str(it.get('id')) == dev['id']]
        assert my, f'健康检查结果未含本卡播放设备: {str(items)[:200]}'

        # 清空 console 缓冲（会话级 driver 复用，避免前置用例残留误判）
        page.driver.get_log('browser')

        # 打开设备管理页
        page.goto(DEVICE_ROUTE)
        page.wait_visible('.device-type-tabs', timeout=25)
        page.settle(0.4)

        # 切「播放设备管理」页签（真实点击，触发 switchDeviceType → fetchAllDevices
        # → autoHealthCheck → playbackPort.checkStatus）
        tabs = [b for b in page.find_all('.tab-btn') if PLAYBACK_TAB_TEXT in (b.text or '')]
        assert tabs, '设备管理页缺少「播放设备管理」页签'
        page.driver.execute_script('arguments[0].click();', tabs[0])

        # 等本卡设备卡片渲染 + 自动健康检查跑完：状态徽章刷新为「离线」
        WebDriverWait(page.driver, 40).until(
            lambda d: _badge_offline(page, dev['name']))
        page.settle(0.5)

        # 控制台零 SEVERE：422 / [API Fetch Error] / 自动健康检查失败 /
        # Uncaught (in promise) 全部消失
        severe = _severe_messages(page)
        bad = _bad_severe(severe)
        assert not bad, (
            f'播放设备页签控制台 SEVERE 残留（INT-399 验收 3 失败）：\n'
            + '\n'.join(bad))
    finally:
        _cleanup_playback_device(api_client, dev['id'])


def test_check_status_returns_200_from_gateway(api_client):
    """网关直验：GET /playback-devices/check-status → 200 状态数组（INT-399 验收 1）。

    与路由单测互补：走真实微服务链（网关 → device_service gRPC → 隔离库）。
    """
    r = api_client.request('GET', '/playback-devices/check-status')
    assert r.get('code') == 0 and isinstance(r.get('data'), list), \
        f'check-status 应返回成功状态数组，实际: {str(r)[:300]}'
