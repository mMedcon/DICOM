# Redis Configuration for DICOM Batch Processing

# Install Redis:
# Windows: Download from https://github.com/microsoftarchive/redis/releases
# Or use Docker: docker run -d -p 6379:6379 redis:alpine

# Start Redis server:
# Windows: redis-server.exe
# Docker: docker run -d -p 6379:6379 redis:alpine

# Redis will run on localhost:6379 by default
# No additional configuration needed for development

# Production settings would include:
# - Authentication
# - Persistence configuration
# - Memory limits
# - Clustering setup
