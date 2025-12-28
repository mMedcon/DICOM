# DICOM Upload Microservice

This microservice provides a FastAPI-based REST API for uploading, processing, and managing DICOM files, with integration for any frontend (e.g., Next.js) and PostgreSQL storage.

## Features
- Upload images (converted to DICOM, anonymized, encrypted)
- Store upload and metadata in PostgreSQL
- Associate uploads with frontend users
- Retrieve user uploads and upload details
- Get upload statistics
- Background processing of batch uploads
- Comprehensive logging system

## Requirements
- Python 3.11+
- PostgreSQL database
- Redis (for batch processing with Celery)
- See `requirements.txt` for Python dependencies

## Setup Instructions

### 1. Clone the Repository
```sh
git clone <repository-url>
cd DICOM
```

### 2. Create a Virtual Environment
```sh
# On Windows
python -m venv venv
venv\Scripts\activate

# On macOS/Linux
python -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```sh
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the project root with the following variables:
```
# Database Configuration
DATABASE_URL=postgresql://username:password@localhost:5432/dicom_db
# OR individual parameters
POSTGRES_DB=dicom_db
POSTGRES_USER=username
POSTGRES_PASSWORD=password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Redis Configuration (for Celery)
REDIS_URL=redis://localhost:6379/0
```

### 5. Set Up PostgreSQL Database
Make sure PostgreSQL is running, then create the database and tables:
```sh
# Create database (if not already created)
createdb dicom_db

# Create tables
python create_tables.py
```

### 6. Set Up Redis (for batch processing)
Redis is used for background processing of batch uploads. See [Redis Setup](redis_setup.md) for detailed instructions.

## Running the Server

### Development Mode
```sh
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode
```sh
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Running with Background Processing

#### Option 1: Using Celery (recommended for production)
Start the Celery worker in a separate terminal:
```sh
# On Linux/macOS
celery -A job_queue.celery_app worker --loglevel=info

# On Windows
python celery_worker_windows.py
```

#### Option 2: Using Simple Processor (Windows-friendly alternative)
The simple processor is automatically used if Celery is not available. No additional setup is required.

## API Endpoints

### Single File Upload
### 1. Upload Image
- **POST** `/upload`
- **Headers:**
  - `X-File-Name`: Original filename (required)
  - `X-User-ID`: User ID (optional, set by your frontend)
  - `Content-Type`: image/jpeg (or other image type)
- **Body:** Raw image file bytes
- **Response:**
  - `upload_id`: Unique upload ID
  - `message`: Status message
  - `diagnosis`: ML diagnosis (mocked)
  - `confidence`: Confidence score (mocked)

### Batch Upload System
### 2. Upload Multiple Files (Batch)
- **POST** `/upload/batch`
- **Headers:**
  - `X-User-ID`: User ID (optional)
  - `Content-Type`: application/json
- **Body:** JSON with files data
```json
{
  "files": [
    {
      "filename": "scan1.jpg",
      "content": "base64-encoded-file-content"
    },
    {
      "filename": "dicom1.dcm",
      "content": "base64-encoded-file-content"
    }
  ]
}
```
- **Response:**
  - `batch_id`: Unique batch ID
  - `message`: Status message
  - `total_files`: Number of files queued
  - `status`: "queued"

### 3. Get Batch Status
- **GET** `/upload/batch/{batch_id}/status`
- **Response:**
  - `batch_id`: Batch identifier
  - `status`: "queued", "processing", "completed", "failed"
  - `total_files`: Total number of files
  - `processed_files`: Number of processed files
  - `progress_percentage`: Completion percentage

### 4. Get User's Batches
- **GET** `/user/{user_id}/batches`
- **Response:**
  - `user_id`: User identifier
  - `batches`: List of batch records
  - `count`: Number of batches

### 5. Get Files in a Batch
- **GET** `/upload/batch/{batch_id}/files`
- **Response:**
  - `batch_id`: Batch identifier
  - `files`: List of files in the batch
  - `count`: Number of files

### Single File Endpoints
### 6. Get User Uploads
- **POST** `/upload`
- **Headers:**
  - `X-File-Name`: Original filename (required)
  - `X-User-ID`: User ID (optional, set by your frontend)
  - `Content-Type`: image/jpeg (or other image type)
- **Body:** Raw image file bytes
- **Response:**
  - `upload_id`: Unique upload ID
  - `message`: Status message
  - `diagnosis`: ML diagnosis (mocked)
  - `confidence`: Confidence score (mocked)

### 2. Get User Uploads
- **GET** `/user/{user_id}/uploads`
- **Response:**
  - `user_id`: The user ID
  - `uploads`: List of upload records
  - `count`: Number of uploads


### 3. Get Upload Details
- **GET** `/upload/{upload_id}/details`
- **Response:** Upload record details

### 4. Get Preprocessed (Anonymized) DICOM File
- **GET** `/upload/{upload_id}/preprocessed-dicom`
- **Response:** Returns the anonymized DICOM file for the given upload_id as a downloadable file (MIME type: application/dicom)

### 5. Manually Save Upload to User Uploads Table
- **POST** `/save-upload`
- **Query Parameters:**
  - `user_id`: User ID
  - `upload_id`: Upload ID
- **Response:** Status message

### 6. Get Upload Statistics
- **GET** `/stats`
- **Response:**
  - `total_uploads`: Total number of uploads
  - `unique_users`: Number of unique users
  - `latest_upload`: Timestamp of latest upload
  - `earliest_upload`: Timestamp of earliest upload

### 6. Root
- **GET** `/`
- **Response:** Welcome message

## Environment Variables
See `.env` for database configuration.

## Database
See `init.sql` for schema.

## Docker
A sample `dockerfile` is provided for containerization.

---

## Logging Configuration

The application uses Python's built-in logging module to provide comprehensive logging. Logs are written to both the console and a rotating file.

### Log Files
- Logs are stored in the `logs` directory (created automatically)
- The main log file is `logs/dicom_service.log`
- Log files rotate when they reach 10MB, with a maximum of 5 backup files

### Log Levels
The application uses the following log levels:
- **DEBUG**: Detailed information, typically useful only for diagnosing problems
- **INFO**: Confirmation that things are working as expected
- **WARNING**: Indication that something unexpected happened, but the application is still working
- **ERROR**: Due to a more serious problem, the application has not been able to perform a function
- **CRITICAL**: A serious error, indicating that the application may be unable to continue running

### Customizing Logging
You can adjust the logging configuration in `main.py` by modifying the `setup_logging()` function.

## Troubleshooting

### Database Connection Issues
- Ensure PostgreSQL is running and accessible
- Verify that the database credentials in your `.env` file are correct
- Check that the database and required tables exist
- If using `DATABASE_URL`, ensure the connection string format is correct

### Redis/Celery Issues
- Ensure Redis is running and accessible
- Check the Redis connection URL in your `.env` file
- On Windows, use `celery_worker_windows.py` instead of the standard Celery command
- If Celery fails, the application will automatically fall back to the simple processor

### File Upload Issues
- Ensure the `uploads` directory exists and is writable
- Check that the `X-File-Name` header is included in upload requests
- Verify that the file content is being sent correctly in the request body
- For batch uploads, ensure the JSON payload is correctly formatted

### Logging Issues
- Ensure the `logs` directory is writable
- Check the log files for detailed error messages
- If logs are not being generated, verify the logging configuration in `main.py`

For more details, see the code and comments in `main.py` and `database.py`.
