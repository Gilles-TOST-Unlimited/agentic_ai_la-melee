import requests
import io
import base64
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from datetime import datetime, timedelta
from collections import Counter
from mcp.server.fastmcp import FastMCP
import mcp.types as types

# --- CONFIGURATION ---
matplotlib.use('Agg')  # Server-safe backend

mcp = FastMCP("Weather Service")
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"

# Cache for emoji images
ICON_CACHE = {}


# --- HELPER FUNCTIONS ---

def get_wmo_description(code: int) -> str:
    """Readable text for text mode."""
    if code == 0: return "Clear"
    if 1 <= code <= 3: return "Cloudy"
    if 45 <= code <= 48: return "Fog"
    if 51 <= code <= 55: return "Drizzle"
    if 56 <= code <= 57: return "Freezing Drizzle"
    if 61 <= code <= 65: return "Rain"
    if 66 <= code <= 67: return "Freezing Rain"
    if 71 <= code <= 77: return "Snow"
    if 80 <= code <= 82: return "Showers"
    if 85 <= code <= 86: return "Snow Showers"
    if 95 <= code <= 99: return "Storm"
    return "Unknown"


def get_emoji_url(code: int) -> str:
    """Maps WMO Code to Twemoji URL."""
    base = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/"

    # ☀️ Clear
    if code == 0: return base + "2600.png"
    # ⛅ Partly Cloudy
    if code == 1: return base + "26c5.png"
    # ☁️ Cloudy
    if 2 <= code <= 3: return base + "2601.png"
    # 🌫️ Fog
    if 45 <= code <= 48: return base + "1f32b.png"
    # 🌦️ Drizzle / Light Rain (Sun behind rain cloud)
    if 51 <= code <= 57: return base + "1f326.png"
    # 🌧️ Rain (Blue Cloud with drops)
    if 61 <= code <= 67: return base + "1f327.png"
    # ❄️ Snow
    if 71 <= code <= 77: return base + "2744.png"
    # ☔ Showers (Umbrella with rain) or Heavy Rain
    if 80 <= code <= 82: return base + "2614.png"
    # 🌨️ Snow Showers
    if 85 <= code <= 86: return base + "1f328.png"
    # ⛈️ Storm
    if 95 <= code <= 99: return base + "26c8.png"

    return base + "1f321.png"


def get_icon_image(code: int, zoom: float = 1.0):
    """Downloads/Caches and returns the emoji image."""
    url = get_emoji_url(code)
    if url in ICON_CACHE:
        img_data = ICON_CACHE[url]
    else:
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            img_data = io.BytesIO(r.content)
            img = plt.imread(img_data, format='png')
            ICON_CACHE[url] = img
        except Exception as e:
            print(f"Icon Error {url}: {e}")
            return None
    return OffsetImage(ICON_CACHE[url], zoom=zoom)


def resolve_weather_code(codes: list[int], label: str = "") -> int:
    """
    SMART AGGREGATION v2 (Weighted Severity):
    Distinguishes 'Drizzle' from 'Heavy Rain' so Summer doesn't look like Winter.
    """
    counts = Counter(codes)
    total = len(codes)
    if total == 0: return 0

    def count_range(min_c, max_c):
        return sum(counts[c] for c in counts if min_c <= c <= max_c)

    # --- Group Categories ---
    storm_days = count_range(95, 99)
    snow_days = count_range(71, 77) + count_range(85, 86)

    # "Real" Rain (Moderate/Heavy Rain + Showers)
    heavy_rain_days = count_range(61, 67) + count_range(80, 82)

    # "Light" Rain (Drizzle) - We count this separately!
    drizzle_days = count_range(51, 57)

    sun_days = count_range(0, 1)
    cloud_days = count_range(2, 48)

    # Percentages
    storm_pct = storm_days / total
    snow_pct = snow_days / total
    heavy_rain_pct = heavy_rain_days / total
    drizzle_pct = drizzle_days / total
    any_rain_pct = (heavy_rain_days + drizzle_days) / total

    # --- DEBUG PRINT ---
    composition = ", ".join([f"{get_wmo_description(c)} ({c}): {cnt}" for c, cnt in counts.items()])
    print(f"\n[DEBUG] Analyzing period: {label}")
    print(f"  > Composition: {composition}")
    print(
        f"  > Groups: Storm={storm_days}, Snow={snow_days}, Heavy Rain={heavy_rain_days}, Drizzle={drizzle_days}, Sun={sun_days}, Cloud={cloud_days}")
    print(f"  > Pcts: Heavy Rain={heavy_rain_pct:.0%}, Drizzle={drizzle_pct:.0%}")

    # --- LOGIC ---
    final_code = 0
    reason = ""

    # 1. Storm (Critical Event) - Low threshold
    if storm_pct >= 0.10:
        final_code = 96
        reason = "Storms detected (>10%)"

    # 2. Snow (Seasonal Indicator) - Low threshold
    elif snow_pct >= 0.10:
        final_code = 71
        reason = "Snow detected (>10%)"

    # 3. Heavy Rain (Wet Season) - Moderate threshold
    # If it rains hard >15% of the month, it's a rainy month.
    elif heavy_rain_pct >= 0.15:
        final_code = 63  # Moderate Rain icon
        reason = "Heavy Rain significant (>15%)"

    # 4. Pure Drizzle (The Summer Fix)
    # Only label as "Rain" if it drizzles MOST of the time (>50%).
    # Otherwise, it's just a cloudy/sunny month with some sprinkles.
    elif drizzle_pct >= 0.50:
        final_code = 53  # Drizzle icon
        reason = "Constant Drizzle (>50%)"

    # 5. Mixed Rain (Heavy + Drizzle combined)
    # If the total wet days are overwhelming (>50%), call it rainy
    elif any_rain_pct >= 0.50:
        final_code = 61  # Light Rain icon
        reason = "Frequent Wet Days (>50%)"

    # 6. Default: Sun vs Cloud
    elif sun_days >= cloud_days:
        final_code = 0  # Sun
        reason = "Majority Sun (Rain was minor)"
    else:
        final_code = 3  # Cloud
        reason = "Majority Cloud (Rain was minor)"

    print(f"  -> SELECTED: {get_wmo_description(final_code).upper()} ({final_code}) | Reason: {reason}")
    return final_code


def fetch_weather_raw(latitude: float, longitude: float, start_date: str, end_date: str):
    params = {
        "latitude": latitude, "longitude": longitude,
        "start_date": start_date, "end_date": end_date,
        "daily": ["temperature_2m_mean", "relative_humidity_2m_mean", "weathercode"],
        "timezone": "auto"
    }
    print(f"\n[DEBUG] Fetching URL: {OPEN_METEO_URL}")

    resp = requests.get(OPEN_METEO_URL, params=params)
    resp.raise_for_status()
    return resp.json()


def aggregate_data(dates, temps, humidities, codes, mode="weekly"):
    """Aggregate Daily -> Weekly or Monthly using Smart Logic."""
    agg_map = {}
    for d, t, h, c in zip(dates, temps, humidities, codes):
        if mode == "monthly":
            key = d.strftime("%Y-%m")
            date_label = d.replace(day=1)
        else:  # weekly
            iso_year, iso_week, _ = d.isocalendar()
            key = f"{iso_year}-W{iso_week}"
            date_label = d - timedelta(days=d.weekday())

        if key not in agg_map:
            agg_map[key] = {"date": date_label, "temps": [], "hums": [], "codes": []}

        agg_map[key]["temps"].append(t)
        agg_map[key]["hums"].append(h)
        agg_map[key]["codes"].append(c)

    sorted_keys = sorted(agg_map.keys())
    new_dates, new_temps, new_hums, new_codes = [], [], [], []

    for k in sorted_keys:
        item = agg_map[k]
        new_dates.append(item["date"])
        new_temps.append(sum(item["temps"]) / len(item["temps"]))
        new_hums.append(sum(item["hums"]) / len(item["hums"]))

        # Pass the key (e.g., '2024-W12') as label for debug printing
        smart_code = resolve_weather_code(item["codes"], label=k)
        new_codes.append(smart_code)

    return new_dates, new_temps, new_hums, new_codes


# --- TOOLS ---

@mcp.tool()
def get_historical_weather(latitude: float, longitude: float, start_date: str, end_date: str) -> str:
    """Text-based weather."""
    try:
        data = fetch_weather_raw(latitude, longitude, start_date, end_date)
        daily = data.get("daily", {})
        results = []
        for t, temp, hum, code in zip(daily.get("time", []), daily.get("temperature_2m_mean", []),
                                      daily.get("relative_humidity_2m_mean", []), daily.get("weathercode", [])):
            results.append(f"Date: {t} | Temp: {temp}°C | Humidity: {hum}% | Cond: {get_wmo_description(code)}")
        return "\n".join(results) if results else "No data."
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def get_weather_visualization(latitude: float, longitude: float, start_date: str, end_date: str) -> list[
    types.TextContent | types.ImageContent]:
    """
    Generates a modern, white-theme weather chart with Twemoji icons.
    """
    try:
        print(f"\n[DEBUG] --- Starting Visualization Request ---")
        data = fetch_weather_raw(latitude, longitude, start_date, end_date)
        daily = data.get("daily", {})

        # 1. Parse Data
        raw_dates = [datetime.strptime(d, "%Y-%m-%d") for d in daily.get("time", [])]
        raw_temps = [float(x) for x in daily.get("temperature_2m_mean", [])]
        raw_hums = [float(x) for x in daily.get("relative_humidity_2m_mean", [])]
        raw_codes = daily.get("weathercode", [])

        if not raw_dates:
            print("[DEBUG] No data received from API.")
            return [types.TextContent(type="text", text="No data.")]

        days_count = len(raw_dates)
        print(f"[DEBUG] Retrieved {days_count} days of data.")

        # 2. Adaptive Logic
        if days_count <= 60:
            print("[DEBUG] Mode: Daily View")
            # For daily view, we simulate aggregation debug just for logging purposes
            for d, c in zip(raw_dates, raw_codes):
                pass  # Too verbose to log every day

            dates, temps, humidities, codes = raw_dates, raw_temps, raw_hums, raw_codes
            title_period = "Daily View"
            date_fmt = mdates.DateFormatter("%d %b")
            bar_width = max(0.6, min(0.9, 30 / days_count))
            icon_zoom = 0.35
        elif days_count <= 365:
            print("[DEBUG] Mode: Weekly Aggregation")
            dates, temps, humidities, codes = aggregate_data(raw_dates, raw_temps, raw_hums, raw_codes, mode="weekly")
            title_period = "Weekly Averages"
            date_fmt = mdates.DateFormatter("%d %b")
            bar_width = 5.0
            icon_zoom = 0.32
        else:
            print("[DEBUG] Mode: Monthly Aggregation")
            dates, temps, humidities, codes = aggregate_data(raw_dates, raw_temps, raw_hums, raw_codes, mode="monthly")
            title_period = "Monthly Averages"
            date_fmt = mdates.DateFormatter("%b\n%Y")
            bar_width = 25.0
            icon_zoom = 0.28

        # 3. Setup Plot
        try:
            plt.style.use('seaborn-v0_8-whitegrid')
        except:
            plt.style.use('bmh')  # Fallback style

        fig_width = max(12, min(24, len(dates) * 0.7))
        fig, ax1 = plt.subplots(figsize=(fig_width, 9))

        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)
        ax1.spines['left'].set_visible(False)
        ax1.spines['bottom'].set_color('#DDDDDD')

        # --- Temperature (Bars) ---
        color_temp = '#FF9F43'
        ax1.bar(dates, temps, width=bar_width, color=color_temp, alpha=0.85, label='Temp Avg (°C)', zorder=2)
        ax1.set_ylabel('Temperature (°C)', color=color_temp, fontsize=13, weight='bold', labelpad=10)
        ax1.tick_params(axis='y', colors=color_temp, labelsize=11)
        ax1.grid(axis='y', linestyle='-', color='#F0F0F0', linewidth=1.2, zorder=0)
        ax1.grid(axis='x', visible=False)

        # --- Humidity (Line) ---
        ax2 = ax1.twinx()
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)
        ax2.spines['left'].set_visible(False)
        ax2.spines['bottom'].set_visible(False)

        color_hum = '#0ABDE3'
        ax2.plot(dates, humidities, color=color_hum, linewidth=4, alpha=0.3, zorder=3)  # Shadow
        ax2.plot(dates, humidities, color=color_hum, linewidth=3, marker='o', markersize=0, label='Humidity Avg (%)',
                 zorder=4)
        ax2.set_ylabel('Humidity (%)', color=color_hum, fontsize=13, weight='bold', labelpad=10)
        ax2.tick_params(axis='y', colors=color_hum, labelsize=11)
        ax2.set_ylim(0, 125)

        # --- ICONS ---
        y_max = ax1.get_ylim()[1]
        offset = y_max * 0.05

        print("[DEBUG] Generating Plot Icons...")
        for d, t, code in zip(dates, temps, codes):
            imagebox = get_icon_image(code, zoom=icon_zoom)
            if imagebox:
                pos_y = max(t, 0) + offset
                ab = AnnotationBbox(imagebox, (mdates.date2num(d), pos_y),
                                    frameon=False, box_alignment=(0.5, 0))
                ax1.add_artist(ab)

        # --- Formatting ---
        ax1.xaxis.set_major_formatter(date_fmt)
        ax1.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=len(dates) + 2))
        plt.xticks(rotation=0, ha='center', fontsize=11, weight='medium')

        plt.title(f"Weather Analytics: {title_period}\n{start_date} to {end_date}", fontsize=18, color='#333333',
                  pad=30, weight='bold')

        # Legend
        dummy_icon = matplotlib.lines.Line2D([], [], color='white', marker='o', markerfacecolor='#FFD700',
                                             markeredgecolor='#FFA500', markersize=10, label='Weather Condition')
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2 + [dummy_icon], labels1 + labels2 + ['Condition'],
                   loc='upper center', bbox_to_anchor=(0.5, -0.08),
                   fancybox=True, shadow=False, ncol=3, frameon=False, fontsize=12)

        plt.tight_layout()
        print("[DEBUG] Chart Generated Successfully. Encoding...")

        # --- Export ---
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode("utf-8")

        return [types.ImageContent(type="image", data=img_base64, mimeType="image/png")]

    except Exception as e:
        import traceback
        traceback.print_exc()
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]


if __name__ == "__main__":
    print("🌤️ Starting Smart-Weather MCP Server...")
    mcp.run(transport="sse")