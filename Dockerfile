FROM python:3.12-slim

# System deps: OpenSCAD for parametric CAD, libgl for trimesh rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    openscad \
    prusa-slicer \
    xvfb \
    xauth \
    libgl1-mesa-dri \
    libegl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Shared volume for Manyfold library (read/write)
RUN mkdir -p /models

EXPOSE 3215

CMD ["python", "server.py"]
