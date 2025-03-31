# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
#
# Copyright 2024 The NiPreps Developers <nipreps@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# We support and encourage derived works from this project, please read
# about our expectations at
#
#     https://www.nipreps.org/community/licensing/
#
"""Utilities to handle BIDS inputs."""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from copy import deepcopy
from importlib import resources
from pathlib import Path

import datalad.api as dlapi
import yaml


def generate_bids_skeleton(target_path, bids_config):
    """
    Converts a BIDS directory in dictionary form to a file structure.

    The BIDS configuration can either be a YAML or JSON file, or :obj:dict: object.

    Parameters
    ----------
    target_path : str
        Path to generate BIDS directory at (must not exist)
    bids_config : dict or str
        Configuration on how to create the BIDS directory.
    """

    if isinstance(bids_config, dict):
        # ensure dictionary remains unaltered
        bids_dict = deepcopy(bids_config)
    elif isinstance(bids_config, str):
        bids_config = Path(bids_config).read_text()
        try:
            bids_dict = json.loads(bids_config)
        except json.JSONDecodeError:
            bids_dict = yaml.safe_load(bids_config)

    _bids_dict = deepcopy(bids_dict)
    root = Path(target_path).absolute()
    root.mkdir(parents=True)

    desc = bids_dict.pop('dataset_description', None)
    if desc is None:
        # default description
        desc = {'Name': 'Default', 'BIDSVersion': '1.6.0'}
    to_json(root / 'dataset_description.json', desc)

    cached_subject_data = None
    for subject, sessions in bids_dict.items():
        bids_subject = subject if subject.startswith('sub-') else f'sub-{subject}'
        subj_path = root / bids_subject
        subj_path.mkdir(exist_ok=True)

        if sessions == '*':  # special case to copy previous subject data
            sessions = cached_subject_data.copy()

        if isinstance(sessions, dict):  # single session
            sessions.update({'session': None})
            sessions = [sessions]

        cached_subject_data = deepcopy(sessions)
        for session in sessions:
            ses_name = session.pop('session', None)
            if ses_name is not None:
                bids_session = ses_name if ses_name.startswith('ses-') else f'ses-{ses_name}'
                bids_prefix = f'{bids_subject}_{bids_session}'
                curr_path = subj_path / bids_session
                curr_path.mkdir(exist_ok=True)
            else:
                bids_prefix = bids_subject
                curr_path = subj_path

            # create modalities
            for modality, files in session.items():
                modality_path = curr_path / modality
                modality_path.mkdir(exist_ok=True)

                if isinstance(files, dict):  # single file / metadata combo
                    files = [files]

                for bids_file in files:
                    metadata = bids_file.pop('metadata', None)
                    extension = bids_file.pop('extension', '.nii.gz')
                    suffix = bids_file.pop('suffix')
                    entities = combine_entities(**bids_file)
                    data_file = modality_path / f'{bids_prefix}{entities}_{suffix}{extension}'
                    data_file.touch()

                    if metadata is not None:
                        out_metadata = data_file.parent / data_file.name.replace(
                            extension, '.json'
                        )
                        to_json(out_metadata, metadata)

    return _bids_dict


def to_json(filename, data):
    filename = Path(filename)
    filename.write_text(json.dumps(data))
    return filename


def combine_entities(**entities):
    return f'_{"_".join([f"{lab}-{val}" for lab, val in entities.items()])}' if entities else ''


def simulate_dataset(output_dir, yaml_file, zip_level, fill_files=False):
    """Create a mock zipped input dataset with n_subjects, each with n_sessions.

    Parameters
    ----------
    output_dir : Pathlike
        The path to the output directory.
    yaml_file : str
        The name of the YAML file to use for the BIDS skeleton.
    zip_level : {'subject', 'session', 'none'}
        The level at which to zip the dataset.
    fill_files : bool, optional
        Whether to fill the files with random data.
        Default is False.

    Returns
    -------
    input_dataset : Path
        The path containing the input dataset. Clone this dataset to
        simulate what happens in a BABS initialization.
    """
    if zip_level not in ['subject', 'session', 'none']:
        raise ValueError(f'Invalid zip level: {zip_level}')

    output_dir = Path(output_dir)
    dataset_dir = output_dir / 'simbids'

    # Load the YAML file from the package resources if it exists there,
    # otherwise load it from the local file system
    if resources.files('simbids.data').joinpath(yaml_file).exists():
        with resources.files('simbids.data').joinpath(yaml_file).open() as f:
            bids_skeleton = yaml.safe_load(f)
    elif Path(yaml_file).exists():
        with open(yaml_file) as f:
            bids_skeleton = yaml.safe_load(f)
    else:
        raise FileNotFoundError(f'YAML file {yaml_file} not found')

    # Create the qsiprep directory first
    generate_bids_skeleton(dataset_dir, bids_skeleton)

    # Loop over all files in qsiprep_dir and if they are .nii.gz, write random data to them
    if fill_files:
        for file_path in dataset_dir.rglob('*.nii.gz'):
            with open(file_path, 'wb') as f:
                f.write(os.urandom(10 * 1024 * 1024))  # 10MB of random data

    # Zip the dataset
    if zip_level == 'subject':
        for subject in dataset_dir.glob('sub-*'):
            zip_path = output_dir / f'{subject.name}_simbids-1-0-1.zip'
            with zipfile.ZipFile(zip_path, 'w') as zf:
                for file_path in subject.rglob('*'):
                    if file_path.is_file():
                        arcname = f'simbids/{subject.name}/{file_path.relative_to(subject)}'
                        zf.write(file_path, arcname)
        shutil.rmtree(dataset_dir)
    elif zip_level == 'session':
        for subject in dataset_dir.glob('sub-*'):
            for session in subject.glob('ses-*'):
                zip_path = output_dir / f'{subject.name}_{session.name}_simbids-1-0-1.zip'
                with zipfile.ZipFile(zip_path, 'w') as zf:
                    for file_path in session.rglob('*'):
                        if file_path.is_file():
                            arcname = (
                                f'simbids/{subject.name}/{session.name}/'
                                f'{file_path.relative_to(session)}'
                            )
                            zf.write(file_path, arcname)
        shutil.rmtree(dataset_dir)

    # initialize a datalad dataset in input_dataset
    dlapi.create(path=output_dir, force=True)

    # Datalad save the zip files
    msg = 'Add zip files' if zip_level != 'none' else 'Add dataset'
    dlapi.save(dataset=output_dir, message=msg)

    return output_dir
