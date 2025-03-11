import os
import time
import json
import random
import signal
import requests
from urllib.parse import urlparse
import colorama
from colorama import Fore, Style
import socks
import socket
from requests.auth import HTTPProxyAuth
import backoff
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import logging
import threading
import sys
import logging.handlers


colorama.init(autoreset=True)


requests.packages.urllib3.disable_warnings()


USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'
]


RATE_LIMIT_RESET_TIME = 60  
MAX_RETRIES = 3  
RETRY_DELAY = 5  
GLOBAL_LOCK = threading.Lock()
RATE_LIMITED_TOKENS = {}  
SSL_ERROR_PROXIES = set()  

def display_banner():
    
    banner = f"""
{Fore.BLUE}════════════════════════════════════════════════════════════════
{Fore.CYAN}                    NodeGo Ping 工具
{Fore.BLUE}════════════════════════════════════════════════════════════════
{Fore.WHITE}            作者：https://x.com/snifftunes
{Fore.BLUE}════════════════════════════════════════════════════════════════
    """
    print(banner)

def get_random_ua():
    
    return random.choice(USER_AGENTS)

def create_session_with_retries():
    
    session = requests.Session()
    
    
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    
    
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=100,
        pool_maxsize=100
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    
    session.verify = False
    session.trust_env = False  
    
    
    requests.packages.urllib3.disable_warnings()
    
    return session

class NodeGoPinger:
    
    def __init__(self, token, proxy_url=None):
        self.api_base_url = 'https://nodego.ai/api'
        self.bearer_token = token
        self.proxy_url = proxy_url
        self.proxy = self._setup_proxy(proxy_url)
        self.last_ping_timestamp = 0
        self.session = create_session_with_retries()
        self.jitter = random.uniform(0.5, 1.5)
        
        
        config = load_config()
        self.ssl_verify = False  
        
        
        self.session.verify = False
        self.session.trust_env = False
    
    def _setup_proxy(self, proxy_url):
        
        if not proxy_url:
            return None
        
        try:
            proxies = {}
            
            
            if proxy_url.startswith(('socks4://', 'socks5://')):
                parsed = urlparse(proxy_url)
                protocol = proxy_url.split('://')[0]
                port = parsed.port or (1080 if protocol == 'socks5' else 1080)
                
                
                proxies = {
                    'http': proxy_url,
                    'https': proxy_url
                }
                return proxies
            
            
            elif proxy_url.startswith(('http://', 'https://')):
                proxies = {
                    'http': proxy_url,
                    'https': proxy_url
                }
            else:
                
                http_url = f"http://{proxy_url}"
                proxies = {
                    'http': http_url,
                    'https': http_url
                }
            
            return proxies
        
        except Exception as e:
            print(f"{Fore.RED}⚠️ 无效的代理URL:{Style.RESET_ALL} {e}")
            return None

    def make_request(self, method, endpoint, data=None):
        url = f"{self.api_base_url}{endpoint}"
        
        headers = {
            'Authorization': f"Bearer {self.bearer_token}",
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'User-Agent': get_random_ua()
        }
        
        with GLOBAL_LOCK:
            if self.bearer_token in RATE_LIMITED_TOKENS:
                reset_time = RATE_LIMITED_TOKENS[self.bearer_token]
                if time.time() < reset_time:
                    wait_time = int(reset_time - time.time())
                    print(f"{Fore.YELLOW}⏳ 令牌 {self.bearer_token[:10]}... 正在等待速率限制重置，还需 {wait_time} 秒")
                    time.sleep(1)
                    raise Exception("令牌仍在速率限制中")
                else:
                    del RATE_LIMITED_TOKENS[self.bearer_token]
        
        if self.proxy_url and self.proxy_url in SSL_ERROR_PROXIES:
            print(f"{Fore.YELLOW}🔒 代理 {self.proxy_url} 之前有SSL错误，跳过...")
            raise Exception("代理SSL错误")
        
        time.sleep(random.uniform(0.5, 2.0) * self.jitter)
        
        for attempt in range(MAX_RETRIES):
            try:
                response = None
                request_kwargs = {
                    'headers': headers,
                    'proxies': self.proxy,
                    'timeout': 30,
                    'verify': False,  
                    'allow_redirects': True
                }
                
                if method.upper() == 'GET':
                    response = self.session.get(url, **request_kwargs)
                elif method.upper() == 'POST':
                    request_kwargs['json'] = data
                    response = self.session.post(url, **request_kwargs)
                
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', RATE_LIMIT_RESET_TIME))
                    reset_time = time.time() + retry_after
                    
                    with GLOBAL_LOCK:
                        RATE_LIMITED_TOKENS[self.bearer_token] = reset_time
                    
                    print(f"{Fore.YELLOW}⏱️ 检测到速率限制，将在 {retry_after} 秒后重试")
                    raise Exception(f"429 速率限制 - 将在 {retry_after} 秒后重试")
                
                response.raise_for_status()
                return response
            
            except requests.exceptions.SSLError as e:
                if self.proxy_url:
                    with GLOBAL_LOCK:
                        SSL_ERROR_PROXIES.add(self.proxy_url)
                
                print(f"{Fore.RED}🔒 SSL错误 (尝试 {attempt+1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    sleep_time = RETRY_DELAY * (attempt + 1) * self.jitter
                    print(f"{Fore.YELLOW}⏳ 等待 {sleep_time:.1f} 秒后重试...")
                    time.sleep(sleep_time)
                else:
                    raise Exception(f"SSL错误: {e}")
            
            except Exception as e:
                print(f"{Fore.RED}❌ 请求错误 (尝试 {attempt+1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    sleep_time = RETRY_DELAY * (attempt + 1) * self.jitter
                    print(f"{Fore.YELLOW}⏳ 等待 {sleep_time:.1f} 秒后重试...")
                    time.sleep(sleep_time)
                else:
                    raise e

    def ping(self):
        
        try:
            current_time = time.time() * 1000
            
            
            if current_time - self.last_ping_timestamp < 3000:
                sleep_time = (3000 - (current_time - self.last_ping_timestamp)) / 1000
                time.sleep(sleep_time)
            
            response = self.make_request('POST', '/user/nodes/ping', {'type': 'extension'})
            
            self.last_ping_timestamp = time.time() * 1000
            
            current_time_str = time.strftime('%H:%M:%S')
            print(f"{Fore.GREEN}>> [{current_time_str}] PING 执行完成")
            print(f"{Fore.GREEN}>> 结果: 响应码: {response.status_code}, 消息: 成功")
            
            return response.json()
        
        except Exception as e:
            print(f"{Fore.RED}>> [错误] {e}")
            return None

def load_config():
    
    default_config = {
        "use_proxy": True,
        "retry_settings": {
            "max_retries": 3,
            "retry_delay": 5,
            "rate_limit_reset_time": 60
        },
        "timing": {
            "min_interval": 180,
            "max_interval": 300,
            "account_delay": {
                "min": 1.0,
                "max": 3.0
            }
        },
        "auto_restart": {
            "enabled": True,
            "hours": 1,  
            "clear_error_caches": True,
            "min_success_rate": 0.3,  
            "min_cycles": 2  
        },
        "output": {
            "show_proxy_info": True,
            "show_detailed_errors": True,
            "color_output": True
        },
        "logging": {
            "enabled": True,
            "level": "INFO",
            "rotate_size": 10485760,  
            "backup_count": 5
        },
        "ssl_settings": {
            "verify": False,
            "disable_warnings": True
        }
    }

    try:
        if os.path.exists('config.json'):
            with open('config.json', 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                
                def update_config(default, user):
                    for key, value in default.items():
                        if key not in user:
                            user[key] = value
                        elif isinstance(value, dict) and isinstance(user[key], dict):
                            update_config(value, user[key])
                update_config(default_config, user_config)
                return user_config
        else:
            
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            print(f"{Fore.GREEN}>> 已创建默认配置文件 config.json")
            return default_config
    except Exception as e:
        print(f"{Fore.RED}>> 配置文件操作失败: {e}")
        return default_config

def setup_logging(config):
    
    if not config.get("logging", {}).get("enabled", True):
        return

    if not os.path.exists('logs'):
        os.makedirs('logs')

    log_filename = f"logs/nodego_ping_{time.strftime('%Y%m%d_%H%M%S')}.log"
    
   
    file_handler = logging.handlers.RotatingFileHandler(
        log_filename,
        maxBytes=config["logging"]["rotate_size"],
        backupCount=config["logging"]["backup_count"],
        encoding='utf-8'
    )
    
    
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    
    
    root_logger = logging.getLogger()
    root_logger.setLevel(config["logging"]["level"])
    root_logger.addHandler(file_handler)
    
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

def restart_program():
    
    logging.info("准备重启程序...")
    print(f"\n{Fore.YELLOW}>> 程序即将重启...")
    
    
    logging.shutdown()
    
    
    time.sleep(2)
    
    try:
        python = sys.executable
        os.execl(python, python, *sys.argv)
    except Exception as e:
        logging.error(f"重启失败: {e}")
        print(f"{Fore.RED}>> 重启失败: {e}")
        sys.exit(1)

class MultiAccountPinger:
    
    def __init__(self):
        self.config = load_config()
        self.accounts = self._load_accounts()
        self.is_running = True
        self.success_count = 0
        self.failure_count = 0
        self.run_count = 0  
        self.start_time = time.time()   
        
        
        global MAX_RETRIES, RETRY_DELAY, RATE_LIMIT_RESET_TIME
        MAX_RETRIES = self.config["retry_settings"]["max_retries"]
        RETRY_DELAY = self.config["retry_settings"]["retry_delay"]
        RATE_LIMIT_RESET_TIME = self.config["retry_settings"]["rate_limit_reset_time"]
    
    def _load_accounts(self):
        
        try:
           
            with open('data.txt', 'r', encoding='utf-8') as f:
                account_data = [line.strip() for line in f if line.strip()]
            
            
            proxy_data = []
            if self.config["use_proxy"]:
                if os.path.exists('proxies.txt'):
                    with open('proxies.txt', 'r', encoding='utf-8') as f:
                        proxy_data = [line.strip() for line in f if line.strip()]
                
                
                if len(proxy_data) < len(account_data):
                    print(f"{Fore.RED}>> 警告: 代理数量({len(proxy_data)})少于账户数量({len(account_data)})")
                    return []
            
            
            accounts = []
            for i, token in enumerate(account_data):
                account = {
                    'token': token.strip(),
                    'primary_proxy': proxy_data[i] if proxy_data else None,
                }
                accounts.append(account)
            
            print(f"{Fore.GREEN}>> 成功加载 {len(accounts)} 个账户" + 
                  (f"和对应代理" if self.config["use_proxy"] else ""))
            return accounts
        
        except Exception as e:
            print(f"{Fore.RED}>> 读取账户数据错误: {e}")
            exit(1)
    
    def process_ping(self, account):
        
        proxy = account['primary_proxy']
        index = self.accounts.index(account) + 1
        
        print(f"\n{Fore.CYAN}>> 正在使用第 {index} 个账户的令牌 (代理: {proxy})")
        
        
        with GLOBAL_LOCK:
            if account['token'] in RATE_LIMITED_TOKENS:
                reset_time = RATE_LIMITED_TOKENS[account['token']]
                if time.time() < reset_time:
                    wait_time = int(reset_time - time.time())
                    print(f"{Fore.YELLOW}>> 此令牌处于速率限制中，跳过。将在 {wait_time} 秒后重试")
                    return False
                else:
                    del RATE_LIMITED_TOKENS[account['token']]
        
        pinger = NodeGoPinger(account['token'], proxy)
        
        try:
            result = pinger.ping()
            if result:
                current_time = time.strftime('%H:%M:%S')
                print(f"{Fore.GREEN}>> [{current_time}] PING 执行完成")
                print(f"{Fore.GREEN}>> 结果: 响应码: {result.get('statusCode', 200)}, 消息: {result.get('message', '成功ping')}")
                return True
            return False
        
        except Exception as e:
            print(f"{Fore.RED}>> 执行失败: {str(e)}")
            return False
    
    def random_delay(self, success_ratio=None):
        
        min_interval = self.config["timing"]["min_interval"] * 1000
        max_interval = self.config["timing"]["max_interval"] * 1000
        
        if success_ratio is None:
            return random.randint(min_interval, max_interval)
        
        
        if success_ratio > 0.8:
            return random.randint(int(min_interval * 0.8), int(max_interval * 0.8))
        elif success_ratio < 0.4:
            return random.randint(int(min_interval * 1.2), int(max_interval * 1.2))
        else:
            return random.randint(min_interval, max_interval)
    
    def check_restart_needed(self):
        
        
        if not self.config.get("auto_restart", {}).get("enabled", False):
            return False

        
        restart_config = self.config["auto_restart"]
        restart_hours = restart_config.get("hours", 1)
        min_success_rate = restart_config.get("min_success_rate", 0.3)
        min_cycles = restart_config.get("min_cycles", 2)

        
        run_time = (time.time() - self.start_time) / 3600

        
        if run_time >= restart_hours:
            logging.info(f"触发定时重启: 已运行 {run_time:.2f} 小时")
            return True

        
        if self.run_count >= min_cycles:
            total_requests = self.success_count + self.failure_count
            if total_requests > 0:
                success_rate = self.success_count / total_requests
                if success_rate < min_success_rate:
                    logging.warning(f"触发低成功率重启: 当前成功率 {success_rate:.1%}")
                    return True

        return False

    def run_pinger(self):
        display_banner()
        
        def signal_handler(sig, frame):
            print(f"\n{Fore.YELLOW}>> 正在安全停止程序...")
            self.is_running = False
            time.sleep(1)
            exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        
        print(f"\n{Fore.CYAN}>> 程序启动完成，开始执行...")
        
        
        if self.config.get("auto_restart", {}).get("enabled", False):
            restart_hours = self.config["auto_restart"]["hours"]
            next_restart_time = time.strftime('%Y-%m-%d %H:%M:%S', 
                time.localtime(self.start_time + restart_hours * 3600))
            print(f"{Fore.YELLOW}>> 已启用自动重启，预计重启时间: {next_restart_time}")

        while self.is_running:
            current_time = time.strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n{Fore.WHITE}═══════════ 当前时间: {current_time} ═══════════")
            
           
            if self.check_restart_needed():
                print(f"\n{Fore.YELLOW}>> 准备执行自动重启...")
                
                
                if self.config["auto_restart"].get("clear_error_caches", True):
                    with GLOBAL_LOCK:
                        SSL_ERROR_PROXIES.clear()
                        RATE_LIMITED_TOKENS.clear()
                    print(f"{Fore.GREEN}>> 已清除错误缓存")
                    logging.info("已清除错误缓存")
                
                restart_program()
                break
            
            cycle_success = 0
            cycle_total = 0
            
            
            for index, account in enumerate(self.accounts, 1):
                if not self.is_running:
                    break
                
                print(f"\n{Fore.CYAN}>> 正在处理第 {index}/{len(self.accounts)} 个账户")
                
                
                delay = random.uniform(
                    self.config["timing"]["account_delay"]["min"],
                    self.config["timing"]["account_delay"]["max"]
                )
                time.sleep(delay)
                
                result = self.process_ping(account)
                cycle_total += 1
                if result:
                    cycle_success += 1
                    self.success_count += 1
                else:
                    print(f"{Fore.RED}>> 第 {index} 个账户处理失败")
                    self.failure_count += 1
            
            
            self.run_count += 1
            
            
            success_ratio = cycle_success / cycle_total if cycle_total > 0 else 0
            print(f"\n{Fore.CYAN}═══════════ 本轮统计 ═══════════")
            print(f"{Fore.WHITE}>> 成功: {cycle_success}/{cycle_total} ({success_ratio:.1%})")
            
            
            total_success_ratio = self.success_count / (self.success_count + self.failure_count) if (self.success_count + self.failure_count) > 0 else 0
            print(f"{Fore.WHITE}>> 总计: 成功 {self.success_count}，失败 {self.failure_count}，成功率 {total_success_ratio:.1%}")
            
            
            run_time_hours = (time.time() - self.start_time) / 3600
            print(f"{Fore.WHITE}>> 已运行时间: {run_time_hours:.2f} 小时")
            
            if self.config.get("auto_restart", {}).get("enabled", False):
                restart_hours = self.config["auto_restart"]["hours"]
                remaining_hours = restart_hours - run_time_hours
                if remaining_hours > 0:
                    print(f"{Fore.WHITE}>> 距离自动重启还有: {remaining_hours:.2f} 小时")

            if self.is_running:
                delay_ms = self.random_delay(success_ratio)
                delay_sec = round(delay_ms / 1000)
                
                next_run = time.strftime('%H:%M:%S', time.localtime(time.time() + delay_sec))
                print(f"\n{Fore.MAGENTA}>> 等待间隔: {delay_sec} 秒")
                print(f"{Fore.WHITE}>> 下次执行时间: {next_run}")
                print(f"{Fore.BLUE}════════════════════════════════════════════════════")
                
                
                sleep_chunks = min(30, delay_sec)
                for _ in range(int(delay_sec / sleep_chunks)):
                    if not self.is_running:
                        break
                    time.sleep(sleep_chunks)
                
                remaining = delay_sec % sleep_chunks
                if remaining > 0 and self.is_running:
                    time.sleep(remaining)


if __name__ == "__main__":
    try:
        
        config = load_config()
        
        
        setup_logging(config)
        
        
        logging.info("程序启动")
        logging.info(f"Python版本: {sys.version}")
        logging.info(f"操作系统: {sys.platform}")
        
        
        multi_pinger = MultiAccountPinger()
        multi_pinger.run_pinger()
    
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}程序被用户中断")
        logging.info("程序被用户中断")
    except Exception as e:
        print(f"{Fore.RED}程序异常: {e}")
        logging.error(f"程序异常: {e}", exc_info=True)
    finally:
        logging.info("程序退出")
