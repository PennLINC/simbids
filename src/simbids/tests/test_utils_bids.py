"""Test the bids module."""

import pytest

import simbids.utils.bids as sbids


def test_simulate_dataset(tmp_path):
    """Test dataset creation without zipping."""
    output = sbids.simulate_dataset(tmp_path, 'multi_ses_qsiprep.yaml')

    # Check if directory structure is created correctly
    assert (output / 'simbids').exists()
    assert (output / 'simbids' / 'sub-01').exists()
    assert (output / 'simbids' / 'sub-01' / 'ses-01').exists()
    assert (output / 'simbids' / 'dataset_description.json').exists()


def test_simulate_dataset_with_filled_files(tmp_path):
    """Test dataset creation with filled files."""
    output = sbids.simulate_dataset(tmp_path, 'multi_ses_qsiprep.yaml', fill_files=True)

    # Check if nifti file exists and has content
    nifti_file = output / 'simbids' / 'sub-01' / 'ses-01' / 'anat' / 'sub-01_ses-01_T1w.nii.gz'
    assert nifti_file.exists()
    assert nifti_file.stat().st_size > 0  # File should not be empty


def test_simulate_dataset_invalid_yaml(tmp_path):
    """Test error handling for non-existent YAML file."""
    with pytest.raises(FileNotFoundError):
        sbids.simulate_dataset(tmp_path, 'nonexistent.yaml')
