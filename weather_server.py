import requests
from mcp.server.fastmcp import FastMCP

# --- CONFIGURATION ---
# We use FastMCP for a cleaner, decorator-based implementation.
# This server will expose an SSE (Server-Sent Events) endpoint.
mcp = FastMCP("Weather Service")

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"

# --- TOOL DEFINITION ---
# The @mcp.tool() decorator automatically registers this function
# and creates the JSON schema needed for the LLM.

@mcp.tool()
def get_historical_weather(latitude: float, longitude: float, start_date: str, end_date: str) -> str:
    """
    Fetches historical weather data (temperature and humidity) for a specific location and date range.

    Args:
        latitude (float): Latitude of the location.
        longitude (float): Longitude of the location.
        start_date (str): Start date in YYYY-MM-DD format.
        end_date (str): End date in YYYY-MM-DD format.

    Returns:
        str: A formatted string containing daily mean temperature and humidity.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ["temperature_2m_mean", "relative_humidity_2m_mean"],
        "timezone": "auto"
    }

    try:
        # 1. Call the External API
        response = requests.get(OPEN_METEO_URL, params=params)
        response.raise_for_status()
        data = response.json()

        # 2. Parse the data (Logic remains the same as before)
        daily_data = data.get("daily", {})
        times = daily_data.get("time", [])
        temps = daily_data.get("temperature_2m_mean", [])
        humidities = daily_data.get("relative_humidity_2m_mean", [])

        results = []
        for t, temp, hum in zip(times, temps, humidities):
            results.append(f"Date: {t} | Temp: {temp}°C | Humidity: {hum}%")

        if not results:
            return "No data found for the given parameters."

        return "\n".join(results)

    except requests.exceptions.RequestException as e:
        return f"Error fetching weather data: {str(e)}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"


# --- SERVER ENTRY POINT ---
if __name__ == "__main__":
    import uvicorn

    print("🌤️ Starting Cloud Weather MCP Server...")

    # We create the SSE handler explicitly from the FastMCP object
    # This allows us to use uvicorn directly with full control over host/port
    starlette_app = mcp._sse_handler  # Access the underlying Starlette app

    # If the private attribute is not available (depends on version),
    # we can just use the object itself if it is an ASGI app,
    # but the safest way for FastMCP is often just to run it via uvicorn command line.
    # HOWEVER, let's try the most robust programmatic method:

    # METHOD: Run Uvicorn on the internal app
    # FastMCP instances are not directly ASGI apps, they create one.
    # The mcp.run() command usually does this for you.
    # Since arguments failed, we will use the internal method manually.

    uvicorn.run(mcp._sse_handler, host="0.0.0.0", port=8000)