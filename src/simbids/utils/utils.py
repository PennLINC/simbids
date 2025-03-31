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
"""Utility functions for SimBIDS."""

import logging
from pathlib import Path
import yaml

LGR = logging.getLogger(__name__)


def _get_wf_name(bold_fname, prefix):
    """Derive the workflow name for supplied BOLD file.

    >>> _get_wf_name("/completely/made/up/path/sub-01_task-nback_bold.nii.gz", "template")
    'template_task_nback_wf'
    >>> _get_wf_name(
    ...     "/completely/made/up/path/sub-01_task-nback_run-01_echo-1_bold.nii.gz",
    ...     "preproc",
    ... )
    'preproc_task_nback_run_01_echo_1_wf'

    """
    from nipype.utils.filemanip import split_filename

    fname = split_filename(bold_fname)[1]
    fname_nosub = '_'.join(fname.split('_')[1:-1])
    return f'{prefix}_{fname_nosub.replace("-", "_")}_wf'


def update_dict(orig_dict, new_dict):
    """Update dictionary with values from another dictionary.

    Parameters
    ----------
    orig_dict : dict
        Original dictionary.
    new_dict : dict
        Dictionary with new values.

    Returns
    -------
    updated_dict : dict
        Updated dictionary.
    """
    updated_dict = orig_dict.copy()
    for key, value in new_dict.items():
        if (orig_dict.get(key) is not None) and (value is not None):
            print(f'Updating {key} from {orig_dict[key]} to {value}')
            updated_dict[key].update(value)
        elif value is not None:
            updated_dict[key] = value

    return updated_dict


def _sanitize_value(value):
    """Convert PaddedInt values to strings."""
    if hasattr(value, '__class__') and value.__class__.__name__ == 'PaddedInt':
        return str(value)
    return value


def _sanitize_metadata(metadata):
    """Convert PaddedInt values to strings in metadata."""
    if not isinstance(metadata, dict):
        return metadata
    return {k: _sanitize_value(v) for k, v in metadata.items()}


def create_skeleton_from_bids(bids_dir, n_subjects, n_sessions):
    """Create a skeleton of the BIDS dataset.

    Given an actual BIDS dataset on the file system, this function
    will create a BIDS skeleton that mimics the structure of the actual dataset.

    The skeleton can be used by niworkflows.testing.generate_BIDS()

    Parameters
    ----------
    bids_dir : str
        Path to the BIDS dataset.
    n_subjects : int
        Number of subjects to create.
    n_sessions : int
        Number of sessions to create.

    Returns
    -------
    dict
        A dictionary containing the BIDS skeleton structure.
    """
    from bids.layout import BIDSLayout, BIDSLayoutIndexer, parse_file_entities

    # Initialize BIDS layout
    indexer = BIDSLayoutIndexer(validate=False, index_metadata=True)
    layout = BIDSLayout(bids_dir, indexer=indexer)

    # Get all subjects
    subjects = sorted(layout.get_subjects())
    if n_subjects > len(subjects):
        n_subjects = len(subjects)

    # Select first n_subjects
    selected_subjects = subjects[:n_subjects]

    # Initialize skeleton structure
    skeleton = {}

    for subject in selected_subjects:
        # Get sessions for this subject
        sessions = sorted(layout.get_sessions(subject=subject))
        if n_sessions > len(sessions):
            n_sessions = len(sessions)

        # Select first n_sessions
        selected_sessions = sessions[:n_sessions]

        if not selected_sessions:
            # No sessions case - similar to no_ses_qsiprep.yaml
            skeleton[subject] = {}

            # Get anatomical data
            anat_files = layout.get(
                subject=subject,
                datatype='anat',
                suffix=['T1w', 'T2w'],
                extension=['.nii.gz', '.nii'],
            )
            if anat_files:
                skeleton[subject]['anat'] = []
                for anat_file in anat_files:
                    anat_sidecar = _sanitize_metadata(anat_file.get_metadata())
                    entities = parse_file_entities(Path(anat_file).name)
                    anat_entry = {
                        'suffix': _sanitize_value(entities.get('suffix', 'T1w')),
                        'metadata': anat_sidecar,
                    }
                    # Add all entities except subject and session
                    for key, value in entities.items():
                        if key not in ['subject', 'session', 'suffix']:
                            anat_entry[key] = _sanitize_value(value)
                    skeleton[subject]['anat'].append(anat_entry)

            # Get DWI data
            dwi_files = layout.get(
                subject=subject,
                datatype='dwi',
                suffix='dwi',
                extension=['.nii.gz', '.nii'],
            )
            if dwi_files:
                skeleton[subject]['dwi'] = []
                for dwi_file in dwi_files:
                    dwi_sidecar = _sanitize_metadata(dwi_file.get_metadata())
                    entities = parse_file_entities(Path(dwi_file).name)
                    dwi_entry = {'suffix': 'dwi', 'metadata': dwi_sidecar}
                    # Add all entities except subject and session
                    for key, value in entities.items():
                        if key not in ['subject', 'session', 'suffix']:
                            dwi_entry[key] = _sanitize_value(value)
                    skeleton[subject]['dwi'].append(dwi_entry)

            # Get functional data
            func_files = layout.get(subject=subject, datatype='func', suffix='bold')
            if func_files:
                skeleton[subject]['func'] = []
                for func_file in func_files:
                    func_sidecar = _sanitize_metadata(func_file.get_metadata())
                    entities = parse_file_entities(Path(func_file).name)
                    func_entry = {'suffix': 'bold', 'metadata': func_sidecar}
                    # Add all entities except subject and session
                    for key, value in entities.items():
                        if key not in ['subject', 'session', 'suffix']:
                            func_entry[key] = _sanitize_value(value)
                    skeleton[subject]['func'].append(func_entry)
        else:
            # With sessions case - similar to multi_ses_qsiprep.yaml
            skeleton[subject] = []
            for session in selected_sessions:
                session_data = {'session': _sanitize_value(session)}

                # Get anatomical data for this session
                anat_files = layout.get(
                    subject=subject, session=session, datatype='anat', suffix=['T1w', 'T2w']
                )
                if anat_files:
                    session_data['anat'] = []
                    for anat_file in anat_files:
                        anat_sidecar = _sanitize_metadata(anat_file.get_metadata())
                        entities = parse_file_entities(Path(anat_file).name)
                        anat_entry = {
                            'suffix': _sanitize_value(entities.get('suffix', 'T1w')),
                            'metadata': anat_sidecar,
                        }
                        # Add all entities except subject and session
                        for key, value in entities.items():
                            if key not in ['subject', 'session', 'suffix']:
                                anat_entry[key] = _sanitize_value(value)
                        session_data['anat'].append(anat_entry)

                # Get DWI data for this session
                dwi_files = layout.get(
                    subject=subject, session=session, datatype='dwi', suffix='dwi'
                )
                if dwi_files:
                    session_data['dwi'] = []
                    for dwi_file in dwi_files:
                        dwi_sidecar = _sanitize_metadata(dwi_file.get_metadata())
                        entities = parse_file_entities(Path(dwi_file).name)
                        dwi_entry = {'suffix': 'dwi', 'metadata': dwi_sidecar}
                        # Add all entities except subject and session
                        for key, value in entities.items():
                            if key not in ['subject', 'session', 'suffix']:
                                dwi_entry[key] = _sanitize_value(value)
                        session_data['dwi'].append(dwi_entry)

                # Get functional data for this session
                func_files = layout.get(
                    subject=subject, session=session, datatype='func', suffix='bold'
                )
                if func_files:
                    session_data['func'] = []
                    for func_file in func_files:
                        func_sidecar = _sanitize_metadata(func_file.get_metadata())
                        entities = parse_file_entities(Path(func_file).name)
                        func_entry = {'suffix': 'bold', 'metadata': func_sidecar}
                        # Add all entities except subject and session
                        for key, value in entities.items():
                            if key not in ['subject', 'session', 'suffix']:
                                func_entry[key] = _sanitize_value(value)
                        session_data['func'].append(func_entry)

                skeleton[subject].append(session_data)

    return skeleton


class BIDSDumper(yaml.Dumper):
    """Custom YAML dumper that handles BIDS objects."""

    def represent_str(self, data):
        return self.represent_scalar('tag:yaml.org,2002:str', str(data), style='"')

    def ignore_aliases(self, data):
        return True

    def represent_object(self, data):
        return self.represent_str(str(data))


# Register the custom dumpers
BIDSDumper.add_representer(str, BIDSDumper.represent_str)
BIDSDumper.add_representer(object, BIDSDumper.represent_object)


def _convert_to_serializable(obj):
    """Convert BIDS objects to basic Python types for YAML serialization."""
    if hasattr(obj, 'get_metadata'):
        return obj.get_metadata()
    if isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_convert_to_serializable(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _convert_to_serializable(v) for k, v in obj.items()}
    return str(obj)
