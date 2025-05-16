# # syntax=docker/dockerfile:1

# # Comments are provided throughout this file to help you get started.
# # If you need more help, visit the Dockerfile reference guide at
# # https://docs.docker.com/go/dockerfile-reference/

# # Want to help us make this template better? Share your feedback here: https://forms.gle/ybq9Krt8jtBL3iCk7

# ARG PYTHON_VERSION=3.9.14
# FROM python:${PYTHON_VERSION}-slim as base

# # Prevents Python from writing pyc files.
# ENV PYTHONDONTWRITEBYTECODE=1

# # Keeps Python from buffering stdout and stderr to avoid situations where
# # the application crashes without emitting any logs due to buffering.
# ENV PYTHONUNBUFFERED=1

# WORKDIR /app


# RUN apt-get update && \
#     apt-get install -y --no-install-recommends \
#     build-essential \
#     cmake \
#     gcc \
#     g++ \
#     make \
#     libffi-dev \
#     libssl-dev \
#     libatlas-base-dev \
#        && apt-get clean && \
#     rm -rf /var/lib/apt/lists/*

# # Create a non-privileged user that the app will run under.
# # See https://docs.docker.com/go/dockerfile-user-best-practices/
# ARG UID=10001
# RUN adduser \
#     --disabled-password \
#     --gecos "" \
#     --home "/nonexistent" \
#     --shell "/sbin/nologin" \
#     --no-create-home \
#     --uid "${UID}" \
#     appuser

# # Download dependencies as a separate step to take advantage of Docker's caching.
# # Leverage a cache mount to /root/.cache/pip to speed up subsequent builds.
# # Leverage a bind mount to requirements.txt to avoid having to copy them into
# # into this layer.
# # RUN --mount=type=cache,id=pip-cache,target=/root/.cache/pip \
# #     pip install -r requirements.txt
# RUN --mount=type=cache,target=/root/.cache/pip,id=build-cache-pip,sharing=shared \
#     pip install -r requirements.txt


# # Switch to the non-privileged user to run the application.
# # USER appuser

# # Copy the source code into the container.
# COPY . .

# # Expose the port that the application listens on.
# EXPOSE 8000

# # Run the application.
# CMD gunicorn 'app:app' --bind=0.0.0.0:8000
# syntax=docker/dockerfile:1.4

ARG PYTHON_VERSION=3.9.14
FROM python:${PYTHON_VERSION}-slim as base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        gcc \
        g++ \
        make \
        libffi-dev \
        libssl-dev \
        libatlas-base-dev \
        libgl1-mesa-glx \ 
         libglib2.0-0 \  
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Optional: Add non-root user (can skip if not required on Railway)
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser

# Copy requirements first to leverage cache
COPY requirements.txt .

# Use BuildKit cache for pip (Railway supports it)
# RUN --mount=type=cache,target=/root/.cache/pip,id=build-cache-pip,sharing=shared \
#     pip install -r requirements.txt
RUN pip install -r requirements.txt
# Copy full project code
COPY . .

# Optional: Switch to non-root user
# USER appuser

EXPOSE 8000

# Start your app
CMD gunicorn 'app:app' --bind=0.0.0.0:8000
