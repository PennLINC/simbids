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
from collections import defaultdict
from copy import deepcopy
from importlib import resources
from pathlib import Path

import datalad.api as dlapi
import yaml
from bids.layout import BIDSLayout, Query
from niworkflows.utils.spaces import SpatialReferences

from simbids.data import load as load_data


def write_derivative_description(input_dir, output_dir):
    """Write dataset_description.json file for derivatives.

    Parameters
    ----------
    input_dir : :obj:`str`
        Path to the primary input dataset being ingested.
        This may be a raw BIDS dataset (in the case of raw+derivatives workflows)
        or a preprocessing derivatives dataset (in the case of derivatives-only workflows).
    output_dir : :obj:`str`
        Path to the output xcp-d dataset.
    dataset_links : :obj:`dict`, optional
        Dictionary of dataset links to include in the dataset description.
    """

    DOWNLOAD_URL = 'https://github.com/nipreps/simbids/archive/0.1.0.tar.gz'

    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    orig_dset_description = os.path.join(input_dir, 'dataset_description.json')
    if not os.path.isfile(orig_dset_description):
        raise FileNotFoundError(f'Dataset description does not exist: {orig_dset_description}')

    with open(orig_dset_description) as fobj:
        desc = json.load(fobj)

    # Update dataset description
    desc['Name'] = 'fMRIPost-AROMA- ICA-AROMA Postprocessing Outputs'
    desc['BIDSVersion'] = '1.9.0dev'
    desc['DatasetType'] = 'derivative'
    desc['HowToAcknowledge'] = 'Include the generated boilerplate in the methods section.'

    # Start with GeneratedBy from the primary input dataset's dataset_description.json
    desc['GeneratedBy'] = desc.get('GeneratedBy', [])

    # Add GeneratedBy from fMRIPost-AROMA
    desc['GeneratedBy'].insert(
        0,
        {
            'Name': 'SimBIDS',
            'Version': '0.1.0',
            'CodeURL': DOWNLOAD_URL,
        },
    )

    # Keys that can only be set by environment
    if 'SIMBIDS_SINGULARITY_URL' in os.environ:
        desc['GeneratedBy'][0]['Container'] = {
            'Type': 'singularity',
            'URI': os.getenv('SIMBIDS_SINGULARITY_URL'),
        }

    # Replace local templateflow path with URL
    dataset_links = {}
    dataset_links['templateflow'] = 'https://github.com/templateflow/templateflow'

    # Add DatasetLinks
    desc['DatasetLinks'] = desc.get('DatasetLinks', {})
    for k, v in dataset_links.items():
        if k in desc['DatasetLinks'].keys() and str(desc['DatasetLinks'][k]) != str(v):
            print(f'"{k}" is already a dataset link. Overwriting.')

        desc['DatasetLinks'][k] = str(v)

    out_desc = Path(output_dir / 'dataset_description.json')
    out_desc.write_text(json.dumps(desc, indent=4))


def collect_derivatives(
    raw_dataset: Path | BIDSLayout | None,
    derivatives_dataset: Path | BIDSLayout | None,
    entities: dict | None,
    fieldmap_id: str | None,
    spec: dict | None = None,
    patterns: list[str] | None = None,
    allow_multiple: bool = False,
    spaces: SpatialReferences | None = None,
    bids_app: str | None = None,
) -> dict:
    """Gather existing derivatives and compose a cache.

    TODO: Ingress 'spaces' and search for BOLD+mask in the spaces *or* xfms.

    Parameters
    ----------
    raw_dataset : Path | BIDSLayout | None
        Path to the raw dataset or a BIDSLayout instance.
    derivatives_dataset : Path | BIDSLayout
        Path to the derivatives dataset or a BIDSLayout instance.
    entities : dict
        Dictionary of entities to use for filtering.
    fieldmap_id : str | None
        Fieldmap ID to use for filtering.
    spec : dict | None
        Specification dictionary.
    patterns : list[str] | None
        List of patterns to use for filtering.
    allow_multiple : bool
        Allow multiple files to be returned for a given query.
    spaces : SpatialReferences | None
        Spatial references to select for.

    Returns
    -------
    derivs_cache : dict
        Dictionary with keys corresponding to the derivatives and values
        corresponding to the file paths.
    """
    if not entities:
        entities = {}

    if spec is None or patterns is None:
        if bids_app == 'qsirecon':
            _spec = json.loads(load_data.readable('io_spec_qsirecon.json').read_text())
        elif bids_app == 'fmriprep':
            _spec = json.loads(load_data.readable('io_spec_fmriprep.json').read_text())
        else:
            _spec = json.loads(load_data.readable('io_spec.json').read_text())

        if spec is None:
            spec = _spec['queries']

        if patterns is None:
            patterns = _spec['patterns']

    # Search for derivatives data
    derivs_cache = defaultdict(list, {})
    if derivatives_dataset is not None:
        layout = derivatives_dataset
        if isinstance(layout, Path):
            layout = BIDSLayout(
                layout,
                config=['bids', 'derivatives'],
                validate=False,
            )

        for k, q in spec['derivatives'].items():
            if k.startswith('anat'):
                # Allow anatomical derivatives at session level or subject level
                query = {
                    **{'subject': entities['subject'], 'session': [entities.get('session'), None]},
                    **q,
                }
            else:
                # Combine entities with query. Query values override file entities.
                query = {**entities, **q}

            item = layout.get(return_type='filename', **query)
            if k.startswith('anat') and not item:
                # If the anatomical derivative is not found, try to find it
                # across sessions
                query = {**{'subject': entities['subject'], 'session': [Query.ANY]}, **q}
                item = layout.get(return_type='filename', **query)

            if not item:
                derivs_cache[k] = None
            elif not allow_multiple and len(item) > 1 and k.startswith('anat'):
                # Raise an error if multiple derivatives are found from different sessions
                item_sessions = [layout.get_file(f).entities['session'] for f in item]
                if len(set(item_sessions)) > 1:
                    raise ValueError(f'Multiple anatomical derivatives found for {k}: {item}')

                # Anatomical derivatives are allowed to have multiple files (e.g., T1w and T2w)
                # but we just grab the first one
                derivs_cache[k] = item[0]
            elif not allow_multiple and len(item) > 1:
                raise ValueError(f'Multiple files found for {k}: {item}')
            else:
                derivs_cache[k] = item[0] if len(item) == 1 else item

        for k, q in spec['transforms'].items():
            if k.startswith('anat'):
                # Allow anatomical derivatives at session level or subject level
                query = {
                    **{'subject': entities['subject'], 'session': [entities.get('session'), None]},
                    **q,
                }
            else:
                # Combine entities with query. Query values override file entities.
                query = {**entities, **q}

            if k == 'boldref2fmap':
                query['to'] = fieldmap_id

            item = layout.get(return_type='filename', **query)
            if k.startswith('anat') and not item:
                # If the anatomical derivative is not found, try to find it
                # across sessions
                query = {**{'subject': entities['subject'], 'session': [Query.ANY]}, **q}
                item = layout.get(return_type='filename', **query)

            if not item:
                derivs_cache[k] = None
            elif not allow_multiple and len(item) > 1 and k.startswith('anat'):
                # Anatomical derivatives are allowed to have multiple files (e.g., T1w and T2w)
                # but we just grab the first one
                derivs_cache[k] = item[0]
            elif not allow_multiple and len(item) > 1:
                raise ValueError(f'Multiple files found for {k}: {item}')
            else:
                derivs_cache[k] = item[0] if len(item) == 1 else item

    # Search for requested output spaces
    if spaces is not None:
        # Put the output-space files/transforms in lists so they can be parallelized with
        # template_iterator_wf.
        spaces_found, bold_outputspaces, bold_mask_outputspaces = [], [], []
        for space in spaces.references:
            # First try to find processed BOLD+mask files in the requested space
            bold_query = {**entities, **spec['derivatives']['bold_mni152nlin6asym']}
            bold_query['space'] = space.space
            bold_query = {**bold_query, **space.spec}
            bold_item = layout.get(return_type='filename', **bold_query)
            bold_outputspaces.append(bold_item[0] if bold_item else None)

            mask_query = {**entities, **spec['derivatives']['bold_mask_mni152nlin6asym']}
            mask_query['space'] = space.space
            mask_query = {**mask_query, **space.spec}
            mask_item = layout.get(return_type='filename', **mask_query)
            bold_mask_outputspaces.append(mask_item[0] if mask_item else None)

            spaces_found.append(bool(bold_item) and bool(mask_item))

        if all(spaces_found):
            derivs_cache['bold_outputspaces'] = bold_outputspaces
            derivs_cache['bold_mask_outputspaces'] = bold_mask_outputspaces
        else:
            # The requested spaces were not found, try to find transforms
            print(
                'Not all requested output spaces were found. '
                'We will try to find transforms to these spaces and apply them to the BOLD data.',
                flush=True,
            )

        spaces_found, anat2outputspaces_xfm = [], []
        for space in spaces.references:
            base_file = derivs_cache['anat2mni152nlin6asym']
            base_file = layout.get_file(base_file)
            # Now try to find transform to the requested space, using the
            # entities from the transform to MNI152NLin6Asym
            anat2space_query = base_file.entities
            anat2space_query['to'] = space.space
            item = layout.get(return_type='filename', **anat2space_query)
            anat2outputspaces_xfm.append(item[0] if item else None)
            spaces_found.append(bool(item))

        if all(spaces_found):
            derivs_cache['anat2outputspaces_xfm'] = anat2outputspaces_xfm
        else:
            missing_spaces = ', '.join(
                [
                    s.space
                    for s, found in zip(spaces.references, spaces_found, strict=False)
                    if not found
                ]
            )
            raise ValueError(
                f'Transforms to the following requested spaces not found: {missing_spaces}.'
            )

    # Search for raw BOLD data
    if not derivs_cache and raw_dataset is not None:
        if isinstance(raw_dataset, Path):
            raw_layout = BIDSLayout(raw_dataset, config=['bids'], validate=False)
        else:
            raw_layout = raw_dataset

        for k, q in spec['raw'].items():
            # Combine entities with query. Query values override file entities.
            query = {**entities, **q}
            item = raw_layout.get(return_type='filename', **query)
            if not item:
                derivs_cache[k] = None
            elif not allow_multiple and len(item) > 1:
                raise ValueError(f'Multiple files found for {k}: {item}')
            else:
                derivs_cache[k] = item[0] if len(item) == 1 else item

    return derivs_cache


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


def simulate_dataset(output_dir, yaml_file, fill_files=False, datalad_init=False):
    """Create a mock zipped input dataset with n_subjects, each with n_sessions.

    Parameters
    ----------
    output_dir : Pathlike
        The path to the output directory.
    yaml_file : str
        The name of the YAML file to use for the BIDS skeleton.
    fill_files : bool, optional
        Whether to fill the files with random data.
        Default is False.
    datalad_init : bool, optional
        Whether to initialize a datalad dataset in the output directory.
        Default is False.

    Returns
    -------
    output_dir : Path
        The path containing the output dataset.
    """

    output_dir = Path(output_dir)
    dataset_dir = output_dir / 'simbids'

    # Load the YAML file from the package resources if it exists there,
    # otherwise load it from the local file system
    with resources.path('simbids.data.bids_mri', '') as bids_mri_path:
        yaml_path = bids_mri_path / yaml_file
        if yaml_path.exists():
            with open(yaml_path) as f:
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

    if datalad_init:
        # initialize a datalad dataset in input_dataset
        dlapi.create(path=output_dir, force=True)

        # Datalad save the zip files
        dlapi.save(dataset=output_dir, message='Add dataset')

    return output_dir
