# PostgreSQL Database Integration for Upload Tracking

This DICOM service includes integration with your PostgreSQL database to save upload records with user tracking.

## Database Setup

### 1. Create Database Tables

The system will create a new table `wix_uploads` to store the user-upload relationships:

```sql
CREATE TABLE public.wix_uploads (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL,
    upload_id UUID NOT NULL REFERENCES public.uploads(id),
    upload_time TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, upload_id)
);
```

### 2. Run Database Migration

Execute the table creation script:

```bash
python create_tables.py
```

This will create all necessary tables including the new `wix_uploads` table.

### 3. Configure Database Connection

Make sure your `.env` file has the correct PostgreSQL connection details:

```env
POSTGRES_DB=your_database_name
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

### 4. Update CORS Settings (Optional)

If you're integrating with a web frontend, make sure your domain is included in the CORS origins in `main.py`:

```python
origins = [
    "http://localhost:3000",  # React dev server
    "https://your-website.com"  # Your production domain
]
```

## Updated Wix Frontend Code

Here's your updated Wix Velo code that includes the user ID in the upload request:

```javascript
import wixUsers from 'wix-users';
import wixData from 'wix-data';

$w.onReady(async function () {
  $w("#promptClinicalTests").hide();
  $w("#submitButton").disable();
  $w("#uploadButton1").disable();

  const currentUser = wixUsers.currentUser;

  // Ensure user is logged in
  if (!currentUser.loggedIn) {
    $w("#promptClinicalTests").text = "Please log in to upload MRI images.";
    $w("#promptClinicalTests").show();
    return;
  }

  try {
    // Get the current user's email and ID
    const email = await currentUser.getEmail();
    const userId = currentUser.id; // Get user ID for database tracking

    // Check clinician collection for permissions
    const clinicianResults = await wixData.query("Clinicians")
      .eq("email", email)
      .eq("isVerified", true)
      .eq("disabled", false)
      .find();

    if (clinicianResults.items.length === 0) {
      $w("#promptClinicalTests").text = "Permission denied: Only verified and active clinicians can upload MRI images.";
      $w("#promptClinicalTests").show();
      return;
    }

    $w("#submitButton").enable();
    $w("#uploadButton1").enable();

  } catch (error) {
    console.error("Error checking clinician permissions:", error);
    $w("#promptClinicalTests").text = "Error verifying clinician access.";
    $w("#promptClinicalTests").show();
    return;
  }

  // Handle upload click if user is allowed
  $w("#submitButton").onClick(async () => {
    /** @type {any} */
    const file = $w("#uploadButton1").value[0];

    if (!file) {
      $w("#promptClinicalTests").text = "Please select a file before submitting.";
      $w("#promptClinicalTests").show();
      return;
    }

    $w("#promptClinicalTests").text = "Uploading, please wait...";
    $w("#promptClinicalTests").show();

    try {
      const fileUrl = file.url;
      const fetchedFile = await fetch(fileUrl);
      const arrayBuffer = await fetchedFile.arrayBuffer();
      const fileType = fetchedFile.headers.get("Content-Type") || "application/octet-stream";
      
      // Get user ID for database tracking
      const userId = wixUsers.currentUser.id;

      const response = await fetch("http://localhost:8000/upload", {
        method: "POST",
        headers: {
          "Content-Type": fileType,
          "X-File-Name": file.name,
          "X-User-ID": userId  // Add user ID header for PostgreSQL tracking
        },
        body: arrayBuffer
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Upload failed with status ${response.status}: ${errorText}`);
      }

      const result = await response.json();

      $w("#promptClinicalTests").text = result.message || "Upload successful!";
      $w("#promptClinicalTests").show();
      $w("#textBox1").value = result.diagnosis || "";
      $w("#textBox2").value = String(result.confidence || "");
      $w("#textBox3").value = result.upload_id || "";

    } catch (error) {
      console.error("Upload error:", error);
      $w("#promptClinicalTests").text = "An error occurred: " + error.message;
      $w("#promptClinicalTests").show();
    }
  });
});
```

### Changes Made:
1. **Line 19**: Added `const userId = currentUser.id;` to get the user ID
2. **Line 58**: Added `const userId = wixUsers.currentUser.id;` to get user ID before upload
3. **Line 64**: Added `"X-User-ID": userId` header to the fetch request

This ensures that every upload will be tracked with the user ID in your PostgreSQL `wix_uploads` table.

### API Endpoints

- `GET /user/{user_id}/uploads` - Get all uploads for a user
- `GET /upload/{upload_id}/details` - Get specific upload details from database
- `POST /save-upload` - Manually save upload to wix_uploads table
- `GET /stats` - Get upload statistics

## Database Structure

The wix_uploads table stores:
```sql
{
  "user_id": "user123",
  "upload_id": "uuid-generated-id", 
  "upload_time": "2025-07-21 10:30:00",
  "created_at": "2025-07-21 10:30:01"
}
```

## Error Handling

- If database save fails, the upload process continues normally
- Errors are logged but don't affect the main DICOM processing
- Check logs for database-related issues

## Testing

1. Install dependencies: `pip install -r requirements.txt`
2. Set up your PostgreSQL database and `.env` file
3. Run `python create_tables.py` to create tables
4. Test the connection with a sample upload including `X-User-ID` header
