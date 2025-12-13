import requests
import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Mount
import mcp.types as types


# --- 1. CORE LOGIC ---
def get_weather_data(latitude: float, longitude: float, start_date: str, end_date: str) -> str:
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": latitude, "longitude": longitude,
        "start_date": start_date, "end_date": end_date,
        "daily": ["temperature_2m_mean", "relative_humidity_2m_mean"],
        "timezone": "auto"
    }
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        results = [
            f"Date: {t} | Temp: {temp}°C | Humidity: {hum}%"
            for t, temp, hum in
            zip(daily.get("time", []), daily.get("temperature_2m_mean", []), daily.get("relative_humidity_2m_mean", []))
        ]
        return "\n".join(results) if results else "No data found."
    except Exception as e:
        return f"Error: {str(e)}"


# --- 2. MCP SERVER SETUP ---
server = Server("weather-server")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_historical_weather",
            description="Fetch historical weather (temp/humidity) for a location/date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"}, "longitude": {"type": "number"},
                    "start_date": {"type": "string"}, "end_date": {"type": "string"}
                },
                "required": ["latitude", "longitude", "start_date", "end_date"]
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[
    types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "get_historical_weather":
        result = get_weather_data(**arguments)
        return [types.TextContent(type="text", text=result)]
    raise ValueError(f"Unknown tool: {name}")


# --- 3. WEB HANDLERS ---
sse = SseServerTransport("/messages")


async def handle_sse(scope, receive, send):
    async with sse.connect_sse(scope, receive, send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


async def handle_messages(scope, receive, send):
    await sse.handle_post_message(scope, receive, send)


# --- 4. STARLETTE APP (FIXED ROUTING) ---
starlette_app = Starlette(
    debug=True,
    routes=[
        # CRITICAL FIX: Order Matters!
        # 1. Catch the specific POST path first.
        #    Because the client got redirected to /sse/, it posts to /sse/messages.
        Mount("/sse/messages", app=handle_messages),

        # 2. Catch the standard POST path (for standard clients).
        Mount("/messages", app=handle_messages),

        # 3. Catch the Stream path last.
        #    Mount("/sse") matches everything starting with /sse, so it must be last.
        Mount("/sse", app=handle_sse),
    ]
)