import requests
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP
mcp = FastMCP("Weather Service")

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"


@mcp.tool()
def get_historical_weather(latitude: float, longitude: float, start_date: str, end_date: str) -> str:
    """
    Fetches historical weather data (temperature and humidity) for a specific location and date range.
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
        response = requests.get(OPEN_METEO_URL, params=params)
        response.raise_for_status()
        data = response.json()

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

# NO entry point code needed here.
# We will launch this using Uvicorn from the Dockerfile.