"""Test the bids module."""

import zipfile

import pytest

import simbids.utils.bids as sbids


def test_simulate_dataset_no_zip(temp_dir):
    """Test dataset creation without zipping."""
    output = sbids.simulate_dataset(temp_dir, 'multi_ses_qsiprep.yaml', 'none')

    # Check if directory structure is created correctly
    assert (output / 'simbids').exists()
    assert (output / 'simbids' / 'sub-01').exists()
    assert (output / 'simbids' / 'sub-01' / 'ses-01').exists()
    assert (output / 'simbids' / 'dataset_description.json').exists()


def test_simulate_dataset_subject_zip(temp_dir):
    """Test dataset creation with subject-level zipping."""
    output = sbids.simulate_dataset(temp_dir, 'multi_ses_qsiprep.yaml', 'subject')

    # Check if zip file is created
    zip_file = output / 'sub-01_simbids-1-0-1.zip'
    assert zip_file.exists()

    # Verify zip contents
    with zipfile.ZipFile(zip_file) as zf:
        files = zf.namelist()
        assert 'simbids/sub-01/ses-01/anat/sub-01_ses-01_T1w.nii.gz' in files
        assert 'simbids/sub-01/ses-01/anat/sub-01_ses-01_T1w.json' in files


def test_simulate_dataset_session_zip(temp_dir):
    """Test dataset creation with session-level zipping."""
    output = sbids.simulate_dataset(temp_dir, 'multi_ses_qsiprep.yaml', 'session')

    # Check if zip file is created
    zip_file = output / 'sub-01_ses-01_simbids-1-0-1.zip'
    assert zip_file.exists()

    # Verify zip contents
    with zipfile.ZipFile(zip_file) as zf:
        files = zf.namelist()
        assert 'simbids/sub-01/ses-01/anat/sub-01_ses-01_T1w.nii.gz' in files
        assert 'simbids/sub-01/ses-01/anat/sub-01_ses-01_T1w.json' in files


def test_simulate_dataset_with_filled_files(temp_dir):
    """Test dataset creation with filled files."""
    output = sbids.simulate_dataset(temp_dir, 'multi_ses_qsiprep.yaml', 'none', fill_files=True)

    # Check if nifti file exists and has content
    nifti_file = output / 'simbids' / 'sub-01' / 'ses-01' / 'anat' / 'sub-01_ses-01_T1w.nii.gz'
    assert nifti_file.exists()
    assert nifti_file.stat().st_size > 0  # File should not be empty


def test_simulate_dataset_invalid_yaml(temp_dir):
    """Test error handling for non-existent YAML file."""
    with pytest.raises(FileNotFoundError):
        sbids.simulate_dataset(temp_dir, 'nonexistent.yaml', 'none')


def test_simulate_dataset_invalid_zip_level(temp_dir):
    """Test with invalid zip level."""
    with pytest.raises(ValueError, match='Invalid zip level: invalid_level'):
        sbids.simulate_dataset(temp_dir, 'multi_ses_qsiprep.yaml', 'invalid_level')
