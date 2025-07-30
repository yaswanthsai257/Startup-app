# Use lightweight Python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy project files
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port (Fly uses 8080)
EXPOSE 8080

# Run your app with Gunicorn (change app:app if needed)
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "app:app"]
