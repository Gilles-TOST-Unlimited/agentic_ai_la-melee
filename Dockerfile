FROM python:3.10-slim

WORKDIR /app

COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 8000
EXPOSE 8000

# Run the script directly (It now contains the uvicorn logic)
CMD ["python", "weather_server.py"]