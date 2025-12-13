import requests
import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
import mcp.types as types

# --- 1. CORE LOGIC (Your Weather Function) ---
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
            for t, temp, hum in zip(daily.get("time", []), daily.get("temperature_2m_mean", []), daily.get("relative_humidity_2m_mean", []))
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
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "get_historical_weather":
        result = get_weather_data(**arguments)
        return [types.TextContent(type="text", text=result)]
    raise ValueError(f"Unknown tool: {name}")

# --- 3. WEB HANDLERS (The Glue for Render) ---
sse = SseServerTransport("/messages")

async def handle_sse(request: Request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())

async def handle_messages(request: Request):
    await sse.handle_post_message(request.scope, request.receive, request._send)

# This 'app' object is what Uvicorn will run
starlette_app = Starlette(
    debug=True,
    routes=[
        Route("/sse", endpoint=handle_sse),
        Route("/messages", endpoint=handle_messages, methods=["POST"])
    ]
)