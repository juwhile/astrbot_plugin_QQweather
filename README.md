[README.md](https://github.com/user-attachments/files/34509477/README.md)
# astrbot_plugin_weather

**AstrBot 天气查询插件** —— 复刻腾讯 QQ 官方天气小组件协议，查询当前城市天气与 7 天预报。

> 不调用任何第三方天气 API，直接复刻 QQ 客户端自带的 `SsoGetWidgetWeather` 官方接口，逐字节对齐官方抓包。

## 🎯 为什么稳定

- **腾讯官方数据源** —— QQ 客户端自带的天气小组件天天在调，腾讯自己依赖，不会无故下线
- **固定 5 字节请求**  —— 零参数、零变量，不会拼错，兼容性最强
- **纯只读、零副作用** —— 不加好友、不进群、不改状态，不触发风控
- **公共数据** —— 与好友/群/权限无关，服务器不会拒绝

> 依赖：登录的 QQ 在线 + AstrBot/NapCat 运行 + 腾讯不改接口。三点缺一不可。

## ✨ 功能

发送 `天气`，返回：

```
江南·南宁天气：空气优 27℃（最低21℃）
风力: 3-4级
湿度: 97%
风向: 东南风
日出 06:54 / 日落 18:06
更新: 11-07 07:26
未来: 25℃/18℃ 小雨  27℃/21℃ 小雨  28℃/17℃ 小雨  23℃/13℃ 阴  22℃/13℃ 晴  24℃/14℃ 晴  25℃/17℃ 多云
```

天气状态词由官方 CDN 图标文件名（`sunny.png` / `light_rain.png` / `overcast.png` 等）映射得到。

## 📦 安装

```bash
cp -r astrbot_plugin_weather /path/to/AstrBot/data/plugins/
sudo systemctl restart astrbot.service
```

或通过 AstrBot 管理面板上传 zip。

## 🚀 使用

```
天气
```

注册了 LLM 工具 `weather_query`，可让大模型直接调用查询天气。

## ⚙️ 环境要求

- AstrBot（支持 `send_packet` action 的适配器，如 `aiocqhttp` / NapCat / SnowLuma）
- 已登录的 QQ 账号（借用登录会话向腾讯请求）

## 📁 文件结构

```
astrbot_plugin_weather/
├── main.py          # 插件主体：协议构造 / 响应解析 / 命令与 LLM 工具
├── metadata.yaml    # 插件元信息
└── README.md        # 本文件
```

## ⚠️ 免责声明

仅用于技术学习与研究。数据来自腾讯 QQ 官方协议，不存储、不转发任何用户数据，纯只读查询。请勿用于商业用途或违反腾讯服务条款。

## 📄 License

MIT
