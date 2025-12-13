# Use a lightweight Python version
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Copy all files from your computer to the container
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 8000 (Standard for FastMCP)
EXPOSE 8000

# Command to run the server
# Note: We simply run the python script. FastMCP handles the rest.
CMD ["python", "weather_server.py"]
