# DICOM Upload Microservice

This microservice provides a FastAPI-based REST API for uploading, processing, and managing DICOM files, with integration for any frontend (e.g., Next.js) and PostgreSQL storage.

## Features
- Upload images (converted to DICOM, anonymized, encrypted)
- Store upload and metadata in PostgreSQL
- Associate uploads with frontend users
- Retrieve user uploads and upload details
- Get upload statistics

## Requirements
- Python 3.11+
- PostgreSQL database
- See `requirements.txt` for Python dependencies

## Running the Server

```sh
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

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

For more details, see the code and comments in `main.py` and `database.py`.
