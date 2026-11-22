# Use the official Python image from the Docker Hub as the base image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container and install dependencies
COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir -m venv /venv && \\./.venv/bin/pip install -r pyproject.toml

# Copy the rest of the application code into the container
COPY . .

# Expose port 8000 to allow the app to run on that port
EXPOSE 8000

# Run the FastAPI app using Uvicorn
CMD ["./.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]