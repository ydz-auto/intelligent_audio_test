import random
import logging
from backend.utils.web.log_handler import log_and_emit

class LoadBalancer:
    def _log(self, level, content, task_id=None, test_case_id=None, api_id=None, category='execution', module='LoadBalancer', **kwargs):
        """统一日志记录方法"""
        log_and_emit(
            level=level,
            module=module,
            content=content,
            category=category,
            source='backend',
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs
        )

    def __init__(self):
        self.url_status = {}
    
    def select_best_endpoint(self, endpoints):
        """
        选择最优的API端点，基于优先级和健康分数
        支持字典和对象两种输入格式
        """
        if not endpoints:
            self._log(
                level='warning',
                content='没有可用的API端点',
                category='system'
            )
            return None
        
        # 获取端点属性的辅助函数，同时支持字典和对象，添加异常处理防止DetachedInstanceError
        def get_endpoint_property(ep, prop, default=None):
            if isinstance(ep, dict):
                return ep.get(prop, default)
            else:
                # 对于对象，使用 getattr，并添加异常处理
                try:
                    # 支持不同的属性名映射
                    prop_map = {
                        'endpoint': getattr(ep, 'url', getattr(ep, 'endpoint', default)),
                        'priority': getattr(ep, 'priority', default),
                        'health_score': getattr(ep, 'health_score', default)
                    }
                    return prop_map.get(prop, getattr(ep, prop, default))
                except Exception as e:
                    # 捕获DetachedInstanceError等异常，返回默认值
                    self._log(
                        level='warning',
                        content=f'获取端点属性失败: {str(e)}，返回默认值 {default}',
                        category='system'
                    )
                    return default
        
        # 记录所有可用端点信息
        endpoint_info = []
        for i, ep in enumerate(endpoints):
            endpoint_url = get_endpoint_property(ep, 'endpoint', '')
            priority = get_endpoint_property(ep, 'priority', 0)
            health_score = get_endpoint_property(ep, 'health_score', 100)
            endpoint_info.append(f'{i+1}. {endpoint_url} (优先级: {priority}, 健康分数: {health_score})')
        
        self._log(
            level='debug',
            content=f'可用端点列表: {" | ".join(endpoint_info)}',
            category='system'
        )
        
        best = endpoints[0]
        for ep in endpoints[1:]:
            ep_priority = get_endpoint_property(ep, 'priority', 0)
            best_priority = get_endpoint_property(best, 'priority', 0)
            
            if ep_priority > best_priority:
                ep_url = get_endpoint_property(ep, 'endpoint', '')
                best_url = get_endpoint_property(best, 'endpoint', '')
                self._log(
                    level='debug',
                    content=f'更新最优端点: {ep_url} (优先级: {ep_priority} > {best_priority})',
                    category='system'
                )
                best = ep
            elif ep_priority == best_priority:
                ep_health = get_endpoint_property(ep, 'health_score', 100)
                best_health = get_endpoint_property(best, 'health_score', 100)
                if ep_health > best_health:
                    ep_url = get_endpoint_property(ep, 'endpoint', '')
                    best_url = get_endpoint_property(best, 'endpoint', '')
                    self._log(
                        level='debug',
                        content=f'更新最优端点: {ep_url} (健康分数: {ep_health} > {best_health}, 优先级相同)',
                        category='system'
                    )
                    best = ep
        
        best_url = get_endpoint_property(best, 'endpoint', '')
        best_priority = get_endpoint_property(best, 'priority', 0)
        best_health = get_endpoint_property(best, 'health_score', 100)
        
        self._log(
            level='info',
            content=f'选择最优端点: {best_url} (优先级: {best_priority}, 健康分数: {best_health})',
            category='system'
        )
        return best
    
    def update_endpoint_health(self, endpoint_id, success, latency):
        """
        更新API端点的健康状态
        注意：由于端点现在是JSON字段的一部分，此方法不再实际更新数据库
        """
        self._log(
            level='debug',
            content=f'端点健康度更新已废弃，不再支持通过ID更新单个端点健康状态',
            category='system'
        )
        # 由于端点现在是JSON字段的一部分，我们无法直接通过endpoint_id更新
        # 此方法现在仅用于日志记录，不执行实际更新操作
    
    def initialize_url_status(self, base_urls):
        """
        初始化URL状态跟踪
        """
        self.url_status = {}
        for url in base_urls:
            self.url_status[url] = {
                'available': True,
                'concurrent': 0
            }
        self._log(
            level='info',
            content=f'初始化URL状态跟踪: {len(base_urls)} 个URL',
            category='system'
        )
    
    def set_url_availability(self, url, available):
        """
        设置URL的可用性状态
        """
        if url in self.url_status:
            old_available = self.url_status[url]['available']
            self.url_status[url]['available'] = available
            if old_available != available:
                status = '可用' if available else '不可用'
                self._log(
                    level='warning' if not available else 'info',
                    content=f'更新URL可用性: {url} → {status}',
                    category='system'
                )
    
    def select_base_url(self):
        """
        选择一个负载最低的可用URL
        """
        self._log(
            level='debug',
            content=f'开始选择基础URL | 当前URL状态: {self.url_status}',
            category='system'
        )
        
        # 1. 过滤出可用的URL
        available_urls = [url for url, status in self.url_status.items() if status['available']]
        
        if not available_urls:
            # 如果没有可用URL，使用所有URL
            available_urls = list(self.url_status.keys())
            self._log(
                level='warning',
                content=f'没有可用URL，使用所有URL | 总URL数: {len(available_urls)}',
                category='system'
            )
        else:
            self._log(
                level='debug',
                content=f'可用URL列表: {" | ".join(available_urls)} | 可用URL数: {len(available_urls)}',
                category='system'
            )
        
        # 记录所有URL的并发情况
        url_concurrent_info = []
        for url in available_urls:
            concurrent = self.url_status[url]['concurrent']
            available = self.url_status[url]['available']
            url_concurrent_info.append(f'{url} (并发: {concurrent}, 可用: {available})')
        
        self._log(
            level='debug',
            content=f'URL并发情况: {" | ".join(url_concurrent_info)}',
            category='system'
        )
        
        # 2. 根据并发数排序，选择并发数最少的URL
        # 如果并发数相同，随机选择
        min_concurrent = min(self.url_status[url]['concurrent'] for url in available_urls)
        candidate_urls = [url for url in available_urls if self.url_status[url]['concurrent'] == min_concurrent]
        
        self._log(
            level='debug',
            content=f'候选URL列表: {" | ".join(candidate_urls)} | 最小并发数: {min_concurrent}',
            category='system'
        )
        
        selected_url = random.choice(candidate_urls)
        old_concurrent = self.url_status[selected_url]['concurrent']
        # 增加并发数计数
        self.url_status[selected_url]['concurrent'] += 1
        new_concurrent = self.url_status[selected_url]['concurrent']
        
        self._log(
            level='info',
            content=f'基础URL选择完成: {selected_url} | 并发数: {old_concurrent} → {new_concurrent} | 可用URL数: {len(available_urls)} | 候选URL数: {len(candidate_urls)}',
            category='system'
        )
        return selected_url
    
    def release_base_url(self, url):
        """
        释放URL的并发数计数
        """
        self._log(
            level='debug',
            content=f'开始释放URL: {url} | 当前状态: {self.url_status.get(url)}',
            category='system'
        )
        
        if url in self.url_status:
            old_concurrent = self.url_status[url]['concurrent']
            new_concurrent = max(0, old_concurrent - 1)
            self.url_status[url]['concurrent'] = new_concurrent
            
            # 检查并发数是否归0
            if new_concurrent == 0:
                self._log(
                    level='info',
                    content=f'URL并发数归0: {url} | 并发数: {old_concurrent} → {new_concurrent}',
                    category='system'
                )
            else:
                self._log(
                    level='debug',
                    content=f'URL释放完成: {url} | 并发数: {old_concurrent} → {new_concurrent} | 当前URL状态: {self.url_status.get(url)}',
                    category='system'
                )
        else:
            self._log(
                level='warning',
                content=f'尝试释放未知URL: {url} | 不在跟踪列表中',
                category='system'
            )
    
    def get_url_status(self):
        """
        获取当前URL状态
        """
        self._log(
            level='debug',
            content='获取当前URL状态',
            category='system'
        )
        return self.url_status
    
    def get_available_urls(self):
        """
        获取可用的URL列表
        """
        available_urls = [url for url, status in self.url_status.items() if status['available']]
        self._log(
            level='debug',
            content=f'获取可用URL列表: {available_urls}',
            category='system'
        )
        return available_urls
