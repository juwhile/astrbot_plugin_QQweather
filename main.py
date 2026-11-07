# -*- coding: utf-8 -*-
"""AstrBot 天气插件

原理: 复刻官方天气小组件请求
  trpc.qqweather.trpc_trpc_proxy.trpc_trpc_proxy.SsoGetWidgetWeather
（capture.log 2026-11-07 重新hook实测）。官方客户端交替使用两种形态:
  形态A: 08 <varint(城市编码)> 20 01        显式指定城市
  形态B: 20 01 2A 25 <IPv6字符串>           不带城市编码, 靠IP自动定位
本项目采用【形态B】(IP自动定位)——服务端根据发起请求的 socket 出口IP
定位城市, 无需传城市编码。响应直接返回定位城市的天气数据:
城市名 / 温度 / 天气状态 / 高低温 / 湿度 / 风向 / 日出日落 / 未来预报。

发送通道: aiocqhttp send_packet action（SnowLuma/NapCat）。
暴露: LLM 工具 weather_query —— 返回本地城市(IP自动定位)的实时天气。
"""
import time

from astrbot.api.event import filter
from astrbot.api.star import Star, Context
from astrbot.api import logger

# ========== protobuf 最小编解码 ==========

def _uv(n: int) -> list:
    out = []
    x = n & 0xFFFFFFFFFFFFFFFF
    while True:
        b = x & 0x7F
        x >>= 7
        if x:
            b |= 0x80
        out.append(b)
        if not x:
            break
    return out


def _pb_varint(buf: bytes, i: int):
    v, shift = 0, 0
    while i < len(buf):
        x = buf[i]; i += 1
        v |= (x & 0x7F) << shift
        if not (x & 0x80):
            break
        shift += 7
    return v, i


def _pb_parse(buf: bytes) -> dict:
    """{field_num: [values]}, 值=bytes 或 int。仅 wire type 0/2。
    注意: tag 本身是 varint, field>=16 时占 2 字节（如 f16 的 0x82 0x01）。
    """
    f, i = {}, 0
    while i < len(buf):
        tag, i = _pb_varint(buf, i)
        fnum, wt = tag >> 3, tag & 7
        if wt == 0:
            v, i = _pb_varint(buf, i)
            f.setdefault(fnum, []).append(v)
        elif wt == 2:
            n, i = _pb_varint(buf, i)
            f.setdefault(fnum, []).append(bytes(buf[i:i + n]))
            i += n
        else:
            break
    return f


def _txt(vals) -> str:
    if not vals:
        return ""
    v = vals[0]
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace").strip()
    return str(v)


def _num(vals):
    if not vals:
        return None
    v = vals[0]
    return int(v) if not isinstance(v, bytes) else None


# ========== 请求构造（形态B: IP自动定位, 与官方实测一致） ==========
# 官方实抓: 20012A25<IPv6字符串>  不带城市编码, 服务端按发起socket出口IP定位
_IP_LOCATE_REQ = bytes.fromhex(
    "20012A25323430653A3335303A3531323A323230303A373061613A653536623A623234623A64656330")

# 天气 icon 文件名 → 中文状态词（来自官方 cdn weather-icon 目录）
_ICON_TEXT = {
    "sunny": "晴", "cloudy": "多云", "overcast": "阴", "partly_cloudy": "多云",
    "light_rain": "小雨", "moderate_rain": "中雨", "heavy_rain": "大雨",
    "rainstorm": "暴雨", "shower": "阵雨", "thundershower": "雷阵雨",
    "light_snow": "小雪", "moderate_snow": "中雪", "heavy_snow": "大雪",
    "blizzard": "暴雪", "sleet": "雨夹雪", "hail": "冰雹",
    "fog": "雾", "haze": "霾", "dust": "浮尘", "sandstorm": "沙尘暴",
    "windy": "大风", "tornado": "龙卷风", "freezing": "冻雨",
    "unknown": "未知",
}


def _icon_to_text(icon: str) -> str:
    """icon 文件名（含或不含 .png）→ 中文天气词。未识别时回退原文。"""
    name = (icon or "").replace(".png", "").replace("\\", "/").split("/")[-1]
    return _ICON_TEXT.get(name, name or "未知")


def _decode_weather(data: bytes) -> dict:
    """解析 SsoGetWidgetWeather 响应（capture1.log line 246 实测）:
    顶层 f1 = 城市对象 {
      f1=区名(江南), f2=市名(南宁), f5=温度"25", f6=最低温"21",
      f8={f2=天气状态"空气优"}, f9=日出"06:54", f10=日落"18:06",
      f12=更新时间戳, f13=天气词"多云", f14=湿度"86", f15=风向"东风",
      f16=风力等级"3-4级",
      顶层 f3 = 未来预报[{f1=高, f2=低, f3=icon URL, f4=code}]
    }
    """
    out = {"ok": False, "err": None}
    try:
        top = _pb_parse(data)
        city_raw = top.get(1, [b""])[0]
        c = _pb_parse(city_raw)
        out["city"] = _txt(c.get(2)) or _txt(c.get(1))
        out["district"] = _txt(c.get(1))
        out["temp"] = _txt(c.get(5))
        out["low"] = _txt(c.get(6))
        cond_raw = c.get(8, [b""])[0]
        out["cond"] = (_txt(_pb_parse(cond_raw).get(2))
                       if isinstance(cond_raw, bytes) else "")
        out["sunrise"] = _txt(c.get(9))
        out["sunset"] = _txt(c.get(10))
        out["wind_level"] = _txt(c.get(16))
        out["humid"] = _txt(c.get(14))
        out["wind"] = _txt(c.get(15))
        out["word"] = _txt(c.get(13))
        out["update_ts"] = _num(c.get(12))
        out["future"] = []
        # 未来预报在顶层 f3 (0x1A), 每条 {f1=高, f2=低, f3=icon URL, f4=code}
        for f3 in top.get(3, []):
            if isinstance(f3, bytes):
                ff = _pb_parse(f3)
                h = _txt(ff.get(1))
                l = _txt(ff.get(2))
                icon = ""
                if ff.get(3) and isinstance(ff[3][0], bytes):
                    icon = ff[3][0].decode("utf-8", "replace")
                if h or l:
                    out["future"].append(
                        f"{h}℃/{l}℃ {_icon_to_text(icon)}")
        out["ok"] = bool(out["city"] or out["cond"])
    except Exception as e:
        out["err"] = str(e)
    return out


def _fmt_weather(d: dict) -> str:
    if d.get("err"):
        return f"天气解析失败: {d['err']}"
    if not d.get("ok"):
        return "天气响应未解析出数据"
    city = d.get("city") or "?"
    district = d.get("district")
    if district and district != city:
        city = f"{district}·{city}"
    temp = d.get("temp")
    low = d.get("low")
    cond = d.get("cond") or d.get("word") or "?"
    if temp is not None:
        if low is not None:
            lines = [f"{city}天气：{cond} {temp}℃（最低{low}℃）"]
        else:
            lines = [f"{city}天气：{cond} {temp}℃"]
    else:
        lines = [f"{city}天气：{cond}"]
    if d.get("wind_level"):
        lines.append(f"风力: {d['wind_level']}")
    if d.get("humid"):
        lines.append(f"湿度: {d['humid']}%")
    if d.get("wind"):
        lines.append(f"风向: {d['wind']}")
    if d.get("sunrise") or d.get("sunset"):
        lines.append(f"日出 {d.get('sunrise','?')} / 日落 {d.get('sunset','?')}")
    if d.get("update_ts"):
        try:
            u = time.strftime("%m-%d %H:%M", time.localtime(int(d["update_ts"])))
            lines.append(f"更新: {u}")
        except Exception:
            pass
    if d.get("future"):
        lines.append("未来: " + "  ".join(d["future"][:5]))
    return "\n".join(lines)


# ========== 插件本体 ==========

class WeatherPlugin(Star):

    def __init__(self, context: Context):
        super().__init__(context)

    async def _send_weather(self) -> bytes:
        """发送形态B(IP自动定位)请求, 返回响应 bytes。"""
        client = self.context.get_platform("aiocqhttp").get_client()
        resp = await client.call_action(
            "send_packet",
            cmd="trpc.qqweather.trpc_trpc_proxy.trpc_trpc_proxy.SsoGetWidgetWeather",
            data=_IP_LOCATE_REQ.hex(), rsp=True)
        data = resp.get("data", resp) if isinstance(resp, dict) else resp
        hex_body = ""
        if isinstance(data, str):
            hex_body = data
        elif isinstance(data, dict):
            hex_body = data.get("data", "") or data.get("responseData", "") or ""
        return bytes.fromhex(hex_body) if hex_body else b""

    @filter.llm_tool(name="weather_query")
    async def weather_tool(self, event):
        """查询本地城市(IP自动定位)的实时天气。

        返回: 城市名、天气状态、当前温度、最低温度、湿度、风向、风力、
        日出/日落时间、数据更新时间、未来几天预报（高低温+天气词）。
        由服务端根据发起请求的出口 IP 自动定位城市, 无需指定城市。
        """
        try:
            r = await self._send_weather()
        except Exception as e:
            return f"天气查询失败: {e}"
        if not r:
            return "天气查询无响应"
        d = _decode_weather(r)
        if d.get("err"):
            return f"天气解析失败: {d['err']}"
        logger.info(f"[TOOL] weather city={d.get('city')} temp={d.get('temp')} "
                    f"cond={d.get('cond')} hex={r.hex()[:200]}")
        return _fmt_weather(d)

    @filter.command("天气")
    async def weather_cmd(self, event):
        """查询本地城市(IP自动定位)的实时天气。用法: 天气"""
        try:
            r = await self._send_weather()
        except Exception as e:
            yield event.plain_result(f"天气查询失败: {e}")
            return
        if not r:
            yield event.plain_result("天气查询无响应（send_packet 可能未返回数据）")
            return
        d = _decode_weather(r)
        if d.get("err"):
            yield event.plain_result(f"天气解析失败: {d['err']}")
            return
        logger.info(f"[CMD] 天气 city={d.get('city')} temp={d.get('temp')} "
                    f"cond={d.get('cond')} hex={r.hex()[:200]}")
        yield event.plain_result(_fmt_weather(d))
