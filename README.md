# astrbot_plugin_weather

AstrBot 天气查询插件 —— 复刻 QQ 官方天气小组件协议，自动定位并查询本地城市实时天气与未来预报。

## ✨ 功能

- **自动定位**：服务端根据发起请求的出口 IP 自动定位城市，无需指定城市
- **实时天气**：城市名、天气状态、当前温度、最低温度
- **详细指标**：湿度、风向、风力等级
- **日出日落**：当日日出/日落时间
- **数据更新时间**
- **未来 7 天预报**：最高/最低温 + 中文天气词

## 🚀 原理（复刻官方协议）

直接复用 QQ 客户端自带的天气小组件接口，不走第三方公开天气 API：

- **命令**：`trpc.qqweather.trpc_trpc_proxy.trpc_trpc_proxy.SsoGetWidgetWeather`
- **请求（形态B）**：`20012A25...dec0`（带 IPv6，不带城市编码）
- **定位机制**：服务端按发起请求的 socket 出口 IP 自动定位城市（实测：北京→北京、上海→上海、南宁→南宁）
- **响应**：纯 protobuf，直接解析出全部天气字段

> 官方客户端还会用形态A（显式城市编码 `08<编码>2001`）查询指定城市；本项目采用形态B自动定位，零参数。

## 📦 安装

1. 下载插件目录到 `AstrBot/data/plugins/astrbot_plugin_weather/`
2. 重启 AstrBot

## 🎮 使用

**命令**：

```
天气
```

**LLM 工具**（AI 对话自动调用）：

```python
@filter.llm_tool(name="weather_query")
async def weather_tool(self, event):
    """查询本地城市(IP自动定位)的实时天气。"""
```

## 🔧 环境要求

- AstrBot（支持 `send_packet` 的适配器，如 NapCat/SnowLuma）
- QQ 账号在线

## 📄 文件结构

```
astrbot_plugin_weather/
├── main.py          # 插件主体
├── metadata.yaml    # 插件元信息
└── README.md        # 说明文档
```

## 🛡️ 免责声明

仅供学习研究使用，纯只读查询，不修改任何数据。请勿用于商业用途。

## 📜 License

MIT
