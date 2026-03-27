from langchain_core.tools import tool


@tool
def get_weather(location: str):
    """查询指定城市的天气。

    示例: `location='北京'` 或 `location='bj'`。
    """
    if not location:
        return "请提供要查询的城市，例如: '北京'。"

    loc = location.lower()
    if "北京" in location or "bj" in loc:
        return "北京天气晴，25℃"

    return f"{location}目前多云，20℃"