
# Use the official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.11-bookworm

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True
# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install dependencies for building dlib and pdlib
RUN apt-get update && apt-get install -y \
# Install ffmpeg
    ffmpeg \
    git \
    wget \   
    cmake \
# OpenBLAS Library - optional
    libopenblas-dev \
    liblapack-dev \
# May or may not need    
    build-essential \
    pkg-config \
    libpostproc-dev

# Clone, build, and install Dlib as a shared library
RUN git clone https://github.com/davisking/dlib.git \
    && mkdir dlib/dlib/build \
    && cd dlib/dlib/build \
    && cmake -DBUILD_SHARED_LIBS=ON .. \
    && make \
    && make install


# Install production dependencies.
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
# Timeout is set to 0 to disable the timeouts of the workers to allow Cloud Run to handle instance scaling.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app