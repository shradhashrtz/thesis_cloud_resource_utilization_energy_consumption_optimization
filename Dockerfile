# Use Python 3.10 as the parent image
FROM python:3.10.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy requirements first for caching dependencies
COPY requirements.txt .

# Install required dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Expose port 8000 for the Flask app and port 5000 for Prometheus metrics
EXPOSE 8000 5000

# Define environment variable for Flask app
ENV FLASK_APP=app.py
ENV PORT=8000

# Run the Flask app using Waitress
CMD ["waitress-serve", "--host=0.0.0.0", "--port=8000", "app:app"]