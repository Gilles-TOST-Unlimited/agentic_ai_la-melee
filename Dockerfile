FROM python:3.10-slim

WORKDIR /app

COPY . /app

# Ensure requirements.txt includes: mcp, mistralai, requests, uvicorn
RUN pip install --no-cache-dir -r requirements.txt

# Tell Render we are using port 8000
EXPOSE 8000

# COMMAND EXPLANATION:
# 1. "uvicorn" : The production web server.
# 2. "weather_server:mcp._sse_handler" : Look in weather_server.py, find the 'mcp' object, and grab its web handler.
# 3. "--host 0.0.0.0" : The critical fix that makes it work on Render.
CMD ["uvicorn", "weather_server:mcp._sse_handler", "--host", "0.0.0.0", "--port", "8000"]