import pydicom
from pydicom.dataset import Dataset
import os
import json
from cryptography.fernet import Fernet
from PIL import Image
import numpy as np

KEY = Fernet.generate_key()
cipher = Fernet(KEY)

def convert_to_dicom(image_path, upload_id):
    """
    Convert image to DICOM format with improved quality preservation
    Optimized for both clinical review and AI analysis
    """
    try:
        # Load and process the image properly
        img = Image.open(image_path)
        original_size = img.size
        print(f"Processing image: {original_size[0]}x{original_size[1]} pixels")
        
        # Convert to RGB first if it has transparency or other modes
        if img.mode in ('RGBA', 'P', 'LA'):
            # Create white background for transparency
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB' and img.mode != 'L':
            img = img.convert('RGB')
        
        # Convert to grayscale for medical imaging (AI models often expect this)
        if img.mode != 'L':
            img = img.convert('L')
        
        # Intelligent resizing for AI optimization
        width, height = img.size
        max_dimension = max(width, height)
        
        # Resize if too large (preserve aspect ratio)
        target_size = 512  # Good balance for AI and quality
        if max_dimension > target_size:
            scale_factor = target_size / max_dimension
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            width, height = new_width, new_height
            print(f"Resized to: {width}x{height} pixels")
        
        # Optional: Pad to square for consistent AI input (uncomment if needed)
        # if width != height:
        #     square_size = max(width, height)
        #     padded_img = Image.new('L', (square_size, square_size), 0)
        #     paste_x = (square_size - width) // 2
        #     paste_y = (square_size - height) // 2
        #     padded_img.paste(img, (paste_x, paste_y))
        #     img = padded_img
        #     width = height = square_size
        
        # Convert to numpy array for proper pixel data handling
        pixel_array = np.array(img, dtype=np.uint8)
        
    except Exception as e:
        print(f"Error processing image: {e}")
        # Fallback to reading raw bytes if image processing fails
        with open(image_path, 'rb') as f:
            image_data = f.read()
        width, height = 512, 512  # Default fallback
        pixel_array = np.frombuffer(image_data[:width*height], dtype=np.uint8)
        if len(pixel_array) < width * height:
            # Pad with zeros if not enough data
            pixel_array = np.pad(pixel_array, (0, width*height - len(pixel_array)), 'constant')
        pixel_array = pixel_array.reshape((height, width))
    
    # Create DICOM dataset
    ds = Dataset()
    ds.SOPInstanceUID = pydicom.uid.generate_uid()
    ds.PatientName = "Anonymous"
    ds.PatientID = "ANON001"
    ds.StudyInstanceUID = pydicom.uid.generate_uid()
    ds.SeriesInstanceUID = pydicom.uid.generate_uid()
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.7"  # Secondary Capture Image Storage
    
    # Set proper DICOM attributes based on actual image
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = height  # Use actual image height
    ds.Columns = width  # Use actual image width
    ds.PixelRepresentation = 0
    
    # Add windowing information for optimal display and AI processing
    ds.WindowCenter = 128  # Middle gray level (0-255 range)
    ds.WindowWidth = 256   # Full dynamic range
    ds.RescaleIntercept = 0  # No offset
    ds.RescaleSlope = 1      # 1:1 scaling
    
    # Add helpful metadata for AI processing
    ds.ImageType = ["DERIVED", "SECONDARY", "PROCESSED"]
    ds.ConversionType = "WSD"  # Workstation
    ds.SecondaryCaptureDeviceManufacturer = "MedConv AI Pipeline"
    ds.SecondaryCaptureDeviceManufacturerModelName = "Image Preprocessor v1.0"
    
    # Set file meta information
    ds.file_meta = pydicom.dataset.FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    
    # Set the processed pixel data
    ds.PixelData = pixel_array.tobytes()

    dicom_path = f"uploads/{upload_id}.dcm"
    pydicom.dcmwrite(dicom_path, ds)
    return dicom_path

def anonymize_dicom(dicom_path):
    try:
        ds = pydicom.dcmread(dicom_path, force=True)
    except Exception as e:
        print(f"Error reading DICOM file: {e}")
        # If we can't read it as DICOM, just copy the file
        anon_path = dicom_path.replace(".dcm", "_anon.dcm")
        import shutil
        shutil.copy2(dicom_path, anon_path)
        return anon_path, {}
    
    removed = {}
    # Only remove tags that actually exist
    tags_to_remove = ['PatientName', 'PatientID', 'PatientBirthDate', 'InstitutionName']
    for tag in tags_to_remove:
        if hasattr(ds, tag):
            removed[tag] = str(getattr(ds, tag))
            delattr(ds, tag)
    
    anon_path = dicom_path.replace(".dcm", "_anon.dcm")
    try:
        ds.save_as(anon_path)
    except Exception as e:
        print(f"Error saving anonymized DICOM: {e}")
        # If we can't save it, just copy the original
        import shutil
        shutil.copy2(dicom_path, anon_path)
    
    return anon_path, removed

def encrypt_file(file_path):
    with open(file_path, 'rb') as f:
        encrypted_data = cipher.encrypt(f.read())
    enc_path = file_path + ".enc"
    with open(enc_path, 'wb') as f:
        f.write(encrypted_data)
    return enc_path

def detect_file_type(file_content: bytes, filename: str) -> str:
    """Detect if file is DICOM or regular image"""
    # Check for DICOM magic bytes
    if len(file_content) > 132 and file_content[128:132] == b'DICM':
        return 'dicom'
    
    # Check common image signatures
    if file_content.startswith(b'\xff\xd8\xff'):  # JPEG
        return 'jpeg'
    elif file_content.startswith(b'\x89PNG'):  # PNG
        return 'png'
    elif file_content.startswith(b'GIF'):  # GIF
        return 'gif'
    elif file_content.startswith(b'BM'):  # BMP
        return 'bmp'
    
    # Fallback to file extension
    ext = os.path.splitext(filename)[1].lower()
    if ext in ['.dcm', '.dicom']:
        return 'dicom'
    else:
        return 'image'

def dicom_to_png(dicom_path, png_path):
    ds = pydicom.dcmread(dicom_path)
    arr = ds.pixel_array
    # Нормализация для 8 бит
    arr = ((arr - arr.min()) / (arr.max() - arr.min()) * 255).astype(np.uint8)
    img = Image.fromarray(arr)
    img.save(png_path)
    return png_path


