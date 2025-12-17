import requests
import uvicorn
import io
import base64
import matplotlib
import matplotlib.pyplot as plt
from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types

# Set non-interactive backend for server environments to prevent GUI errors
matplotlib.use('Agg')

# --- 1. CORE LOGIC ---

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"


def get_wmo_description(code: int) -> str:
    """Helper to convert WMO weather codes to text."""
    if code == 0: return "Clear"
    if 1 <= code <= 3: return "Cloudy"
    if 45 <= code <= 48: return "Fog"
    if 51 <= code <= 67: return "Rain"
    if 71 <= code <= 77: return "Snow"
    if 80 <= code <= 82: return "Showers"
    if 95 <= code <= 99: return "Storm"
    return "Unknown"


def fetch_weather_raw(latitude: float, longitude: float, start_date: str, end_date: str):
    """Fetches raw JSON data from Open-Meteo."""
    params = {
        "latitude": latitude, "longitude": longitude,
        "start_date": start_date, "end_date": end_date,
        "daily": ["temperature_2m_mean", "relative_humidity_2m_mean", "weathercode"],
        "timezone": "auto"
    }
    resp = requests.get(OPEN_METEO_URL, params=params)
    resp.raise_for_status()
    return resp.json()


def get_weather_text(latitude: float, longitude: float, start_date: str, end_date: str) -> str:
    """Returns a text summary (Old Tool Logic)."""
    try:
        data = fetch_weather_raw(latitude, longitude, start_date, end_date)
        daily = data.get("daily", {})

        results = []
        for t, temp, hum, code in zip(
                daily.get("time", []),
                daily.get("temperature_2m_mean", []),
                daily.get("relative_humidity_2m_mean", []),
                daily.get("weathercode", [])
        ):
            condition = get_wmo_description(code)
            results.append(f"Date: {t} | Temp: {temp}°C | Humidity: {hum}% | Cond: {condition}")

        return "\n".join(results) if results else "No data found."
    except Exception as e:
        return f"Error: {str(e)}"


def generate_chart_image(latitude: float, longitude: float, start_date: str, end_date: str) -> str:
    """Generates a chart and returns it as a base64 encoded string."""
    try:
        data = fetch_weather_raw(latitude, longitude, start_date, end_date)
        daily = data.get("daily", {})

        dates = daily.get("time", [])
        temps = daily.get("temperature_2m_mean", [])
        humidities = daily.get("relative_humidity_2m_mean", [])
        codes = daily.get("weathercode", [])

        if not dates:
            return None

        # --- PLOTTING LOGIC ---
        # Use a modern dark style
        plt.style.use('dark_background')
        fig, ax1 = plt.subplots(figsize=(10, 6))

        # Bar Chart for Temperature
        color_temp = '#ff7f0e'  # Orange
        bars = ax1.bar(dates, temps, color=color_temp, alpha=0.7, label='Temperature (°C)')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Temperature (°C)', color=color_temp)
        ax1.tick_params(axis='y', labelcolor=color_temp)
        plt.xticks(rotation=45)

        # Line Chart for Humidity (Dual Axis)
        ax2 = ax1.twinx()
        color_hum = '#1f77b4'  # Cyan/Blue
        ax2.plot(dates, humidities, color=color_hum, marker='o', linewidth=2, label='Humidity (%)')
        ax2.set_ylabel('Humidity (%)', color=color_hum)
        ax2.tick_params(axis='y', labelcolor=color_hum)
        ax2.set_ylim(0, 100)

        # Add Weather Annotations on top of bars
        for bar, code in zip(bars, codes):
            yval = bar.get_height()
            label = get_wmo_description(code)
            ax1.text(bar.get_x() + bar.get_width() / 2, yval + 1,
                     label, ha='center', va='bottom', fontsize=8, color='white', rotation=90)

        plt.title(f"Weather Dashboard: {start_date} to {end_date}")
        plt.tight_layout()

        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plt.close(fig)
        buf.seek(0)

        # Convert to Base64
        image_base64 = base64.b64encode(buf.read()).decode('utf-8')
        return image_base64

    except Exception as e:
        print(f"Plotting Error: {e}")
        return None


# --- 2. MCP SERVER SETUP ---
server = Server("weather-server")


# TOOL 1: Text Data
@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_historical_weather",
            description="Fetch historical weather (temp/humidity) as text.",
            inputSchema={
                "type": "object",
                "properties": {
                    "latitude": {"type": "number"}, "longitude": {"type": "number"},
                    "start_date": {"type": "string"}, "end_date": {"type": "string"}
                },
                "required": ["latitude", "longitude", "start_date", "end_date"]
            }
        ),
        types.Tool(
            name="get_weather_visualization",
            description="Generate a visual bar chart dashboard (PNG image) for weather data.",
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
    if not arguments:
        raise ValueError("Missing arguments")

    if name == "get_historical_weather":
        result = get_weather_text(**arguments)
        return [types.TextContent(type="text", text=result)]

    if name == "get_weather_visualization":
        base64_image = generate_chart_image(**arguments)
        if base64_image:
            return [
                types.ImageContent(
                    type="image",
                    data=base64_image,
                    mimeType="image/png"
                )
            ]
        else:
            return [types.TextContent(type="text", text="Failed to generate image.")]

    raise ValueError(f"Unknown tool: {name}")


# --- 3. PURE ASGI DISPATCHER ---
sse = SseServerTransport("/messages")


async def starlette_app(scope, receive, send):
    """Unified ASGI application."""
    if scope["type"] != "http": return

    path = scope["path"]
    method = scope["method"]

    if path == "/sse" and method == "GET":
        async with sse.connect_sse(scope, receive, send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())
        return

    if (path == "/messages" or path == "/sse/messages") and method == "POST":
        await sse.handle_post_message(scope, receive, send)
        return

    await send({'type': 'http.response.start', 'status': 404, 'headers': [(b'content-type', b'text/plain')]})
    await send({'type': 'http.response.body', 'body': b'Not Found'})


if __name__ == "__main__":
    # Local testing convenience
    uvicorn.run(starlette_app, host="0.0.0.0", port=8000)