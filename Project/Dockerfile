# Use Python 3.10 as the parent image
FROM python:3.10.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 8000 for the application
EXPOSE 8000

# Define environment variable
ENV PORT=8000

# Run the application using waitress
CMD ["python", "-m", "waitress", "--port=8000", "app:app"]
