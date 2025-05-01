FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    xvfb \
    libglib2.0-0 \
    libnss3 \
    libfontconfig1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxtst6 \
    libxrandr2 \
    libxss1 \
    libpango-1.0-0 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libnspr4 \
    apt-transport-https \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome version 114 directly from mirror
RUN wget -q https://mirror.cs.uchicago.edu/google-chrome/pool/main/g/google-chrome-stable/google-chrome-stable_114.0.5735.90-1_amd64.deb \
    && apt-get update \
    && apt-get install -y ./google-chrome-stable_114.0.5735.90-1_amd64.deb \
    && rm google-chrome-stable_114.0.5735.90-1_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

# Verify Chrome version
RUN google-chrome --version

# Install ChromeDriver version 114
RUN wget -q https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip \
    && unzip chromedriver_linux64.zip \
    && mv chromedriver /usr/bin/chromedriver \
    && chmod +x /usr/bin/chromedriver \
    && rm chromedriver_linux64.zip

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Copy Streamlit configuration
COPY .streamlit /app/.streamlit

# Expose the port Streamlit runs on
EXPOSE 8080

# Set environment variables for Chrome
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1

# Command to run the application
CMD bash -c 'streamlit run review_analysis_app.py --server.port=${PORT:-8080} --server.address=0.0.0.0'
