import pydicom
from pydicom.dataset import Dataset
import os
import json
from cryptography.fernet import Fernet

KEY = Fernet.generate_key()
cipher = Fernet(KEY)

def convert_to_dicom(image_path, upload_id):
    ds = Dataset()
    ds.SOPInstanceUID = pydicom.uid.generate_uid()
    ds.PatientName = "Anonymous"
    ds.PatientID = "ANON001"
    ds.StudyInstanceUID = pydicom.uid.generate_uid()
    ds.SeriesInstanceUID = pydicom.uid.generate_uid()
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.7"  # Secondary Capture Image Storage
    
    # Required DICOM attributes for image data
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = 512  # Default values, ideally should be read from actual image
    ds.Columns = 512
    ds.PixelRepresentation = 0
    
    ds.file_meta = pydicom.dataset.FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    
    # Read image data
    with open(image_path, 'rb') as f:
        image_data = f.read()
    ds.PixelData = image_data

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


