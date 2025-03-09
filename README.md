# NodeGo Ping 工具

一个用于自动执行 NodeGo 节点 ping 操作的多账户管理工具。

## 功能特点

- 多账户管理和轮询
- 代理支持
- 重试和速率限制处理

## 安装说明

1. 克隆仓库到本地：
```bash
git clone https://github.com/pig2048/NodeGo.git
cd NodeGo
```

2. 创建并激活虚拟环境：
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

## 配置文件

### config.json

-控制代理开关，重试次数，时间间隔


### data.txt
存放账户令牌，每行一个：
```
token1
token2
...
```

### proxies.txt
存放代理地址，每行一个：
```
http://proxy1:port1
http://proxy2:port2
...
```

## 使用方法

1. 配置文件准备：
   - 在 `data.txt` 中添加账户令牌
   - 在 `proxies.txt` 中添加代理地址
   - 根据需要修改 `config.json`

2. 运行程序：
```bash
python main.py
```

## 错误处理

程序会自动处理以下情况：
- 网络连接问题
- 代理服务器错误
- API 速率限制
- SSL 证书错误
