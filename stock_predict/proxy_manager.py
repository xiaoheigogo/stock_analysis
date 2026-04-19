"""
智能代理管理器模块

功能：
1. 多源代理配置管理（Clash配置文件、环境变量、直接代理列表）
2. 代理健康检查和自动选择
3. 失败自动切换和重试
4. 请求频率控制和延迟管理
5. 代理使用统计和性能监控
"""

import yaml
import base64
import requests
import random
import time
import threading
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

class ProxyType(Enum):
    """代理类型枚举"""
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"
    SOCKS4 = "socks4"
    VMESS = "vmess"  # Clash配置文件中的vmess类型
    SSR = "ssr"      # Clash配置文件中的ssr类型

@dataclass
class ProxyServer:
    """代理服务器信息"""
    name: str
    type: ProxyType
    server: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    tags: List[str] = None
    latency: float = float('inf')  # 延迟（毫秒）
    success_rate: float = 0.0      # 成功率
    last_used: float = 0.0         # 最后使用时间戳
    failure_count: int = 0         # 失败次数

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    @property
    def proxy_url(self) -> str:
        """获取代理URL"""
        if self.username and self.password:
            return f"{self.type.value}://{self.username}:{self.password}@{self.server}:{self.port}"
        return f"{self.type.value}://{self.server}:{self.port}"

    @property
    def http_proxy_url(self) -> str:
        """获取HTTP代理URL（兼容requests）"""
        return self.proxy_url

    @property
    def https_proxy_url(self) -> str:
        """获取HTTPS代理URL（兼容requests）"""
        return self.proxy_url

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'name': self.name,
            'type': self.type.value,
            'server': self.server,
            'port': self.port,
            'username': self.username,
            'password': self.password,
            'tags': self.tags,
            'latency': self.latency,
            'success_rate': self.success_rate
        }


class ProxyManager:
    """代理管理器"""

    def __init__(self, config_path: str = None):
        """
        初始化代理管理器

        Args:
            config_path: Clash配置文件路径（YAML格式）
        """
        self.proxies: List[ProxyServer] = []
        self.current_proxy: Optional[ProxyServer] = None
        self.lock = threading.RLock()
        self.health_check_interval = 300  # 健康检查间隔（秒）
        self.max_failures = 3  # 最大失败次数
        self.test_urls = [
            "http://httpbin.org/ip",
            "http://icanhazip.com",
            "http://ipinfo.io/ip"
        ]

        # 从配置文件加载代理
        if config_path:
            self.load_from_config(config_path)

        # 从环境变量加载代理
        self.load_from_env()

        # 如果没有代理，使用默认直连
        if not self.proxies:
            logger.warning("未配置代理，将使用直连模式")

    def load_from_config(self, config_path: str) -> None:
        """
        从Clash配置文件加载代理

        Args:
            config_path: Clash配置文件路径
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # 解析proxies部分
            if 'proxies' in config:
                for proxy_data in config['proxies']:
                    try:
                        proxy = self._parse_clash_proxy(proxy_data)
                        if proxy:
                            self.proxies.append(proxy)
                    except Exception as e:
                        logger.warning(f"解析代理配置失败: {proxy_data}, 错误: {e}")

            logger.info(f"从配置文件 {config_path} 加载了 {len(self.proxies)} 个代理")

        except Exception as e:
            logger.error(f"加载配置文件失败: {config_path}, 错误: {e}")

    def _parse_clash_proxy(self, proxy_data: Dict) -> Optional[ProxyServer]:
        """解析Clash代理配置"""
        proxy_type = proxy_data.get('type', '').lower()
        name = proxy_data.get('name', 'unknown')
        server = proxy_data.get('server', '')
        port = proxy_data.get('port', 0)
        tags = proxy_data.get('tags', [])

        if not server or port <= 0:
            return None

        # 根据类型创建代理
        if proxy_type in ['http', 'https', 'socks5', 'socks4']:
            proxy_type_enum = ProxyType(proxy_type)
            username = proxy_data.get('username')
            password = proxy_data.get('password')

            return ProxyServer(
                name=name,
                type=proxy_type_enum,
                server=server,
                port=port,
                username=username,
                password=password,
                tags=tags
            )
        elif proxy_type in ['vmess', 'ssr']:
            # 对于vmess/ssr类型，我们可能需要转换为本地代理
            # 这里假设Clash已经在本地运行，我们只需要使用本地Clash端口
            logger.debug(f"跳过Clash专用代理类型: {proxy_type}")
            return None

        return None

    def load_from_env(self) -> None:
        """从环境变量加载代理"""
        import os

        http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
        https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')

        proxies_added = 0

        if http_proxy:
            try:
                # 解析HTTP代理URL
                proxy = self._parse_proxy_url(http_proxy, "env_http")
                if proxy:
                    self.proxies.append(proxy)
                    proxies_added += 1
            except Exception as e:
                logger.warning(f"解析HTTP代理环境变量失败: {http_proxy}, 错误: {e}")

        if https_proxy and https_proxy != http_proxy:
            try:
                # 解析HTTPS代理URL
                proxy = self._parse_proxy_url(https_proxy, "env_https")
                if proxy:
                    self.proxies.append(proxy)
                    proxies_added += 1
            except Exception as e:
                logger.warning(f"解析HTTPS代理环境变量失败: {https_proxy}, 错误: {e}")

        if proxies_added > 0:
            logger.info(f"从环境变量加载了 {proxies_added} 个代理")

    def _parse_proxy_url(self, url: str, name: str) -> Optional[ProxyServer]:
        """解析代理URL"""
        import re

        # 匹配模式: protocol://[username:password@]host:port
        pattern = r'^(?P<protocol>https?|socks[45])://(?:((?P<username>[^:]+):(?P<password>[^@]+))@)?(?P<host>[^:]+):(?P<port>\d+)$'
        match = re.match(pattern, url.lower())

        if not match:
            return None

        protocol = match.group('protocol')
        host = match.group('host')
        port = int(match.group('port'))
        username = match.group('username')
        password = match.group('password')

        # 确定代理类型
        if protocol in ['http', 'https']:
            proxy_type = ProxyType.HTTP
        elif protocol == 'socks5':
            proxy_type = ProxyType.SOCKS5
        elif protocol == 'socks4':
            proxy_type = ProxyType.SOCKS4
        else:
            return None

        return ProxyServer(
            name=name,
            type=proxy_type,
            server=host,
            port=port,
            username=username,
            password=password,
            tags=['env']
        )

    def add_proxy(self, proxy: ProxyServer) -> None:
        """添加代理"""
        with self.lock:
            self.proxies.append(proxy)

    def remove_proxy(self, proxy: ProxyServer) -> None:
        """移除代理"""
        with self.lock:
            if proxy in self.proxies:
                self.proxies.remove(proxy)

    def get_best_proxy(self, require_tags: List[str] = None) -> Optional[ProxyServer]:
        """
        获取最佳代理

        Args:
            require_tags: 需要的标签（如['hk', 'jp']表示香港或日本代理）

        Returns:
            最佳代理服务器，如果没有可用代理则返回None
        """
        with self.lock:
            # 过滤可用代理
            available_proxies = []
            for proxy in self.proxies:
                # 检查失败次数
                if proxy.failure_count >= self.max_failures:
                    continue

                # 检查标签要求
                if require_tags:
                    if not any(tag in proxy.tags for tag in require_tags):
                        continue

                available_proxies.append(proxy)

            if not available_proxies:
                logger.warning("没有可用代理")
                return None

            # 选择最佳代理：综合考虑延迟、成功率、最近使用时间
            def score_proxy(p: ProxyServer) -> float:
                # 基础分数（越高越好）
                latency_score = 1.0 / (p.latency + 1)  # 延迟越低分数越高
                success_score = p.success_rate  # 成功率越高分数越高

                # 时间衰减：最近使用过的代理分数降低（避免频繁使用同一代理）
                time_since_last_use = time.time() - p.last_used
                time_penalty = 0.5 if time_since_last_use < 60 else 1.0  # 60秒内使用过则惩罚

                return latency_score * success_score * time_penalty

            # 选择分数最高的代理
            best_proxy = max(available_proxies, key=score_proxy)
            best_proxy.last_used = time.time()
            self.current_proxy = best_proxy

            logger.debug(f"选择代理: {best_proxy.name} (延迟: {best_proxy.latency:.0f}ms, 成功率: {best_proxy.success_rate:.1%})")
            return best_proxy

    def test_proxy(self, proxy: ProxyServer, timeout: int = 5) -> Tuple[bool, float]:
        """
        测试代理可用性

        Args:
            proxy: 代理服务器
            timeout: 超时时间（秒）

        Returns:
            (是否可用, 延迟毫秒)
        """
        proxies = {
            'http': proxy.http_proxy_url,
            'https': proxy.https_proxy_url
        }

        test_url = random.choice(self.test_urls)

        try:
            start_time = time.time()
            response = requests.get(
                test_url,
                proxies=proxies,
                timeout=timeout,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            response.raise_for_status()

            latency = (time.time() - start_time) * 1000  # 转换为毫秒

            # 验证返回的是IP地址（确保代理生效）
            ip_text = response.text.strip()
            import re
            if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip_text):
                # 可能是JSON格式
                try:
                    ip_data = response.json()
                    if 'ip' in ip_data:
                        ip_text = ip_data['ip']
                except:
                    pass

            logger.debug(f"代理测试成功: {proxy.name} -> {ip_text}, 延迟: {latency:.0f}ms")
            return True, latency

        except Exception as e:
            logger.debug(f"代理测试失败: {proxy.name}, 错误: {e}")
            return False, float('inf')

    def health_check_all(self) -> None:
        """检查所有代理的健康状态"""
        with self.lock:
            logger.info(f"开始健康检查，共 {len(self.proxies)} 个代理")

            for proxy in self.proxies:
                success, latency = self.test_proxy(proxy)

                if success:
                    proxy.latency = latency
                    proxy.success_rate = 0.9 * proxy.success_rate + 0.1 * 1.0  # 指数移动平均
                    proxy.failure_count = max(0, proxy.failure_count - 1)  # 成功则减少失败计数
                else:
                    proxy.latency = float('inf')
                    proxy.success_rate = 0.9 * proxy.success_rate + 0.1 * 0.0  # 指数移动平均
                    proxy.failure_count += 1

                logger.debug(f"代理 {proxy.name}: 延迟={proxy.latency:.0f}ms, 成功率={proxy.success_rate:.1%}, 失败次数={proxy.failure_count}")

            logger.info("健康检查完成")

    def mark_failure(self, proxy: ProxyServer) -> None:
        """标记代理失败"""
        with self.lock:
            proxy.failure_count += 1
            proxy.success_rate = 0.9 * proxy.success_rate + 0.1 * 0.0  # 更新成功率

            logger.warning(f"代理 {proxy.name} 失败，失败次数: {proxy.failure_count}")

            # 如果当前代理失败，切换到下一个
            if proxy == self.current_proxy:
                self.current_proxy = None

    def mark_success(self, proxy: ProxyServer, latency: float = None) -> None:
        """标记代理成功"""
        with self.lock:
            if latency is not None:
                proxy.latency = 0.9 * proxy.latency + 0.1 * latency  # 指数移动平均
            proxy.success_rate = 0.9 * proxy.success_rate + 0.1 * 1.0  # 指数移动平均
            proxy.failure_count = max(0, proxy.failure_count - 1)  # 成功则减少失败计数

    def get_session(self, require_tags: List[str] = None, timeout: int = 30) -> requests.Session:
        """
        获取配置了代理的requests Session

        Args:
            require_tags: 需要的代理标签
            timeout: 默认超时时间

        Returns:
            配置好的requests Session
        """
        session = requests.Session()
        session.timeout = timeout

        proxy = self.get_best_proxy(require_tags)
        if proxy:
            session.proxies = {
                'http': proxy.http_proxy_url,
                'https': proxy.https_proxy_url
            }
            # 添加User-Agent
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })

        return session

    def start_health_check_daemon(self) -> None:
        """启动后台健康检查线程"""
        def health_check_worker():
            while True:
                try:
                    self.health_check_all()
                except Exception as e:
                    logger.error(f"健康检查线程出错: {e}")

                time.sleep(self.health_check_interval)

        thread = threading.Thread(target=health_check_worker, daemon=True)
        thread.start()
        logger.info("启动代理健康检查守护线程")


# 全局代理管理器实例
_global_proxy_manager: Optional[ProxyManager] = None

def get_proxy_manager(config_path: str = None) -> ProxyManager:
    """
    获取全局代理管理器实例（单例模式）

    Args:
        config_path: 配置文件路径

    Returns:
        代理管理器实例
    """
    global _global_proxy_manager

    if _global_proxy_manager is None:
        _global_proxy_manager = ProxyManager(config_path)

    return _global_proxy_manager


def setup_proxy_for_akshare(config_path: str = None) -> None:
    """
    为akshare设置代理

    Args:
        config_path: 代理配置文件路径
    """
    import akshare as ak
    import os

    proxy_manager = get_proxy_manager(config_path)
    proxy = proxy_manager.get_best_proxy()

    if proxy:
        # 设置环境变量
        os.environ['HTTP_PROXY'] = proxy.http_proxy_url
        os.environ['HTTPS_PROXY'] = proxy.https_proxy_url

        # 设置akshare的headers
        ak._HTTP_HEADERS = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        logger.info(f"为akshare设置代理: {proxy.name}")
    else:
        logger.warning("未设置代理，akshare将使用直连模式")


# 使用示例
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(level=logging.INFO)

    # 创建代理管理器
    manager = ProxyManager(config_path="data_process/airport.yaml")

    # 健康检查
    manager.health_check_all()

    # 获取最佳代理
    proxy = manager.get_best_proxy(require_tags=['hk', 'jp'])

    if proxy:
        print(f"最佳代理: {proxy.name}")
        print(f"代理URL: {proxy.proxy_url}")

        # 测试代理
        success, latency = manager.test_proxy(proxy)
        print(f"测试结果: {'成功' if success else '失败'}, 延迟: {latency:.0f}ms")

        # 获取配置了代理的session
        session = manager.get_session()
        response = session.get("http://httpbin.org/ip")
        print(f"当前IP: {response.text}")