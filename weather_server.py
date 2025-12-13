import requests
import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types

# --- 1. CORE LOGIC (Weather Function) ---
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

# --- 3. PURE ASGI DISPATCHER (The Fix) ---
# Instead of Starlette Routes, we define one function that handles everything.
# This prevents 307 Redirects and Path Stripping issues.

sse = SseServerTransport("/messages") # Tells the client to post to /messages

async def starlette_app(scope, receive, send):
    """
    A unified ASGI application that routes requests manually.
    """
    if scope["type"] != "http":
        # Handle lifespan/other events gracefully
        return

    path = scope["path"]
    method = scope["method"]

    # 1. Handle the SSE Stream (GET /sse)
    if path == "/sse" and method == "GET":
        async with sse.connect_sse(scope, receive, send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())
        return

    # 2. Handle Message Posts (POST /messages)
    # We also check /sse/messages to catch any clients that got redirected previously.
    if (path == "/messages" or path == "/sse/messages") and method == "POST":
        await sse.handle_post_message(scope, receive, send)
        return

    # 3. Handle 404 Not Found
    # If the request matches nothing above, return 404.
    await send({
        'type': 'http.response.start',
        'status': 404,
        'headers': [(b'content-type', b'text/plain')],
    })
    await send({
        'type': 'http.response.body',
        'body': b'Not Found - Use /sse for connection',
    })