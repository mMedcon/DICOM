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
    ds.file_meta = pydicom.dataset.FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = pydicom.uid.generate_uid()
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.PixelData = open(image_path, 'rb').read()

    dicom_path = f"uploads/{upload_id}.dcm"
    pydicom.dcmwrite(dicom_path, ds)
    return dicom_path

def anonymize_dicom(dicom_path):
    ds = pydicom.dcmread(dicom_path)
    removed = {}
    for tag in ['PatientName', 'PatientID', 'PatientBirthDate', 'InstitutionName']:
        if tag in ds:
            removed[tag] = str(ds.get(tag))
            del ds[tag]
    anon_path = dicom_path.replace(".dcm", "_anon.dcm")
    ds.save_as(anon_path)
    return anon_path, removed

def encrypt_file(file_path):
    with open(file_path, 'rb') as f:
        encrypted_data = cipher.encrypt(f.read())
    enc_path = file_path + ".enc"
    with open(enc_path, 'wb') as f:
        f.write(encrypted_data)
    return enc_path


