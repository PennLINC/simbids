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
"""
SimBIDS workflows
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autofunction:: init_simbids_wf
.. autofunction:: init_single_subject_wf
.. autofunction:: init_single_run_wf

"""

import sys
from importlib import resources

import nipype.pipeline.engine as pe
import yaml
from niworkflows.engine.workflows import LiterateWorkflow as Workflow
from niworkflows.interfaces.bids import BIDSInfo

from simbids import config
from simbids.interfaces.bids import QSIPrepDerivativesDataSink as DerivativesDataSink
from simbids.interfaces.reportlets import AboutSummary, SubjectSummary
from simbids.utils.utils import _get_wf_name


def collect_data(layout, participant_label, session_id=None, filters=None):
    """Use pybids to retrieve the input data for a given participant."""

    from bids.layout import Query

    queries = {
        'fmap': {'datatype': 'fmap'},
        'sbref': {'datatype': 'func', 'suffix': 'sbref'},
        'flair': {'datatype': 'anat', 'suffix': 'FLAIR'},
        't2w': {'datatype': 'anat', 'suffix': 'T2w'},
        't1w': {'datatype': 'anat', 'suffix': 'T1w'},
        'roi': {'datatype': 'anat', 'suffix': 'roi'},
        'dwi': {'datatype': 'dwi', 'suffix': 'dwi'},
    }
    bids_filters = filters or {}
    for acq in queries.keys():
        entities = bids_filters.get(acq, {})

        if ('session' in entities.keys()) and (session_id is not None):
            config.loggers.workflow.warning(
                'BIDS filter file value for session may conflict with values specified '
                'on the command line'
            )
        queries[acq]['session'] = session_id or Query.OPTIONAL
        queries[acq].update(entities)

    subj_data = {
        dtype: sorted(
            layout.get(
                return_type='file',
                subject=participant_label,
                extension=['nii', 'nii.gz'],
                **query,
            )
        )
        for dtype, query in queries.items()
    }

    config.loggers.workflow.log(
        25,
        f'Collected data:\n{yaml.dump(subj_data, default_flow_style=False, indent=4)}',
    )

    return subj_data


def init_single_subject_qsiprep_wf(subject_id: str):
    """Organize the postprocessing pipeline for a single subject."""

    workflow = Workflow(name=f'sub_{subject_id}_wf')
    workflow.__desc__ = f"""
Results included in this manuscript come from postprocessing
performed using *SimBIDS* {config.environment.version},
which is based on *Nipype* {config.environment.nipype_version}
(@nipype1; @nipype2; RRID:SCR_002502).

"""
    workflow.__postdesc__ = """

For more details of the pipeline, see [the section corresponding
to workflows in *SimBIDS*'s documentation]\
(https://simbids.readthedocs.io/en/latest/workflows.html).


### Copyright Waiver

The above boilerplate text was automatically generated by SimBIDS
with the express intention that users should copy and paste this
text into their manuscripts *unchanged*.
It is released under the
[CC0](https://creativecommons.org/publicdomain/zero/1.0/) license.

### References

"""
    spaces = config.workflow.spaces
    subject_data = collect_data(config.execution.layout, subject_id)
    # Make sure we always go through these two checks
    if not subject_data['dwi']:
        raise RuntimeError(
            f'No DWI images found for participant {subject_id}. '
            f'Please check your BIDS filters: {config.execution.bids_filters}.'
        )

    config.loggers.workflow.info(
        f'Collected subject data:\n{yaml.dump(subject_data, default_flow_style=False, indent=4)}',
    )

    bids_info = pe.Node(
        BIDSInfo(
            bids_dir=config.execution.bids_dir,
            bids_validate=False,
            in_file=subject_data['dwi'][0],
        ),
        name='bids_info',
    )

    summary = pe.Node(
        SubjectSummary(
            bold=subject_data['dwi'],
            std_spaces=spaces.get_spaces(nonstandard=False),
            nstd_spaces=spaces.get_spaces(standard=False),
        ),
        name='summary',
        run_without_submitting=True,
    )
    workflow.connect([(bids_info, summary, [('subject', 'subject_id')])])

    about = pe.Node(
        AboutSummary(version=config.environment.version, command=' '.join(sys.argv)),
        name='about',
        run_without_submitting=True,
    )

    ds_report_summary = pe.Node(
        DerivativesDataSink(
            source_file=subject_data['dwi'][0],
            base_directory=config.execution.output_dir,
            desc='summary',
            datatype='figures',
        ),
        name='ds_report_summary',
        run_without_submitting=True,
    )
    workflow.connect([(summary, ds_report_summary, [('out_report', 'in_file')])])

    ds_report_about = pe.Node(
        DerivativesDataSink(
            source_file=subject_data['dwi'][0],
            base_directory=config.execution.output_dir,
            desc='about',
            datatype='figures',
        ),
        name='ds_report_about',
        run_without_submitting=True,
    )
    workflow.connect([(about, ds_report_about, [('out_report', 'in_file')])])

    # Append the functional section to the existing anatomical excerpt
    # That way we do not need to stream down the number of bold datasets
    dwi_pre_desc = f"""
dMRI data postprocessing

: For each of the {len(subject_data['dwi'])} DWI runs found per subject
(across all sessions), these files were copied into the output directory.
"""
    workflow.__desc__ += dwi_pre_desc

    text_file = resources.files('simbids').joinpath('data/text_file.txt')

    for dwi_file in subject_data['dwi']:
        workflow.add_nodes(
            [
                pe.Node(
                    DerivativesDataSink(
                        source_file=dwi_file,
                        in_file=dwi_file,
                        base_directory=config.execution.output_dir,
                        space='ACPC',
                        desc='preproc',
                        suffix='dwi',
                        extension='.nii.gz',
                        compress=True,
                    ),
                    name=_get_wf_name(dwi_file, 'ds_dwi_t1'),
                    run_without_submitting=True,
                ),
                pe.Node(
                    DerivativesDataSink(
                        source_file=dwi_file,
                        in_file=text_file,
                        base_directory=config.execution.output_dir,
                        space='ACPC',
                        suffix='dwi',
                        extension='.bval',
                        desc='preproc',
                    ),
                    name=_get_wf_name(dwi_file, 'ds_bvals_t1'),
                    run_without_submitting=True,
                ),
                pe.Node(
                    DerivativesDataSink(
                        source_file=dwi_file,
                        in_file=text_file,
                        base_directory=config.execution.output_dir,
                        space='ACPC',
                        suffix='dwi',
                        extension='.bvec',
                        desc='preproc',
                    ),
                    name=_get_wf_name(dwi_file, 'ds_bvecs_t1'),
                    run_without_submitting=True,
                ),
                pe.Node(
                    DerivativesDataSink(
                        source_file=dwi_file,
                        in_file=dwi_file,
                        base_directory=config.execution.output_dir,
                        space='ACPC',
                        suffix='dwiref',
                        extension='.nii.gz',
                        compress=True,
                    ),
                    name=_get_wf_name(dwi_file, 'ds_t1_b0_ref'),
                    run_without_submitting=True,
                ),
                pe.Node(
                    DerivativesDataSink(
                        source_file=dwi_file,
                        in_file=dwi_file,
                        base_directory=config.execution.output_dir,
                        space='ACPC',
                        desc='brain',
                        suffix='mask',
                        extension='.nii.gz',
                        compress=True,
                    ),
                    name=_get_wf_name(dwi_file, 'ds_dwi_mask_t1'),
                    run_without_submitting=True,
                ),
                pe.Node(
                    DerivativesDataSink(
                        source_file=dwi_file,
                        in_file=dwi_file,
                        base_directory=config.execution.output_dir,
                        space='ACPC',
                        model='eddy',
                        statistic='cnr',
                        suffix='dwimap',
                        extension='.nii.gz',
                        compress=True,
                        meta_dict={
                            'Description': 'Contrast-to-noise ratio map for the HMC step.',
                        },
                    ),
                    name=_get_wf_name(dwi_file, 'ds_cnr_map_t1'),
                    run_without_submitting=True,
                ),
                pe.Node(
                    DerivativesDataSink(
                        source_file=dwi_file,
                        in_file=text_file,
                        base_directory=config.execution.output_dir,
                        space='ACPC',
                        desc='preproc',
                        suffix='dwi',
                        extension='.b',
                    ),
                    name=_get_wf_name(dwi_file, 'ds_gradient_table_t1'),
                    run_without_submitting=True,
                ),
                pe.Node(
                    DerivativesDataSink(
                        source_file=dwi_file,
                        in_file=text_file,
                        base_directory=config.execution.output_dir,
                        space='ACPC',
                        desc='preproc',
                        suffix='dwi',
                        extension='.b_table.txt',
                    ),
                    name=_get_wf_name(dwi_file, 'ds_btable_t1'),
                    run_without_submitting=True,
                ),
            ]
        )

    # Create the anatomical datasinks
    anatomical_template = 'MNI152NLin6Asym'
    for anat_file in subject_data['t1w']:
        workflow.add_nodes(
            [
                pe.Node(
                    DerivativesDataSink(
                        compress=True,
                        in_file=anat_file,
                        source_file=anat_file,
                        base_directory=config.execution.output_dir,
                        space='ACPC',
                        desc='preproc',
                        keep_dtype=True,
                    ),
                    name=_get_wf_name(anat_file, 'ds_t1_preproc'),
                    run_without_submitting=True,
                ),
                pe.Node(
                    DerivativesDataSink(
                        compress=True,
                        in_file=anat_file,
                        source_file=anat_file,
                        base_directory=config.execution.output_dir,
                        space='ACPC',
                        desc='brain',
                        suffix='mask',
                    ),
                    name=_get_wf_name(anat_file, 'ds_t1_mask'),
                    run_without_submitting=True,
                ),
                pe.Node(
                    DerivativesDataSink(
                        compress=True,
                        in_file=anat_file,
                        source_file=anat_file,
                        base_directory=config.execution.output_dir,
                        space='ACPC',
                        suffix='dseg',
                    ),
                    name=_get_wf_name(anat_file, 'ds_t1_seg'),
                    run_without_submitting=True,
                ),
                pe.Node(
                    DerivativesDataSink(
                        compress=True,
                        in_file=anat_file,
                        source_file=anat_file,
                        base_directory=config.execution.output_dir,
                        space='ACPC',
                        desc='aseg',
                        suffix='dseg',
                    ),
                    name=_get_wf_name(anat_file, 'ds_t1_aseg'),
                    run_without_submitting=True,
                ),
                pe.Node(
                    DerivativesDataSink(
                        in_file=anat_file,
                        source_file=anat_file,
                        base_directory=config.execution.output_dir,
                        to='ACPC',
                        mode='image',
                        suffix='xfm',
                        **{'from': anatomical_template},
                    ),
                    name=_get_wf_name(anat_file, 'ds_t1_mni_inv_warp'),
                    run_without_submitting=True,
                ),
                pe.Node(
                    DerivativesDataSink(
                        source_file=anat_file,
                        in_file=anat_file,
                        base_directory=config.execution.output_dir,
                        to='ACPC',
                        mode='image',
                        suffix='xfm',
                        **{'from': 'anat'},
                    ),
                    name=_get_wf_name(anat_file, 'ds_t1_template_acpc_transforms'),
                    run_without_submitting=True,
                ),
                pe.Node(
                    DerivativesDataSink(
                        in_file=anat_file,
                        source_file=anat_file,
                        base_directory=config.execution.output_dir,
                        to='anat',
                        mode='image',
                        suffix='xfm',
                        **{'from': 'ACPC'},
                    ),
                    name=_get_wf_name(anat_file, 'ds_t1_template_acpc_inv_transforms'),
                    run_without_submitting=True,
                ),
                pe.Node(
                    DerivativesDataSink(
                        in_file=anat_file,
                        source_file=anat_file,
                        base_directory=config.execution.output_dir,
                        to=anatomical_template,
                        mode='image',
                        suffix='xfm',
                        **{'from': 'ACPC'},
                    ),
                    name=_get_wf_name(anat_file, 'ds_t1_mni_warp'),
                    run_without_submitting=True,
                ),
            ]
        )

    return clean_datasinks(workflow)


def init_single_dwi_run_wf(dwi_file: str):
    """Set up a single-run workflow for SimBIDS."""
    from niworkflows.engine.workflows import LiterateWorkflow as Workflow

    workflow = Workflow(name=_get_wf_name(dwi_file, 'single_run'))
    workflow.__desc__ = ''

    # Fill in datasinks seen so far
    for node in workflow.list_node_names():
        if node.split('.')[-1].startswith('ds_'):
            workflow.get_node(node).inputs.base_directory = config.execution.output_dir
            workflow.get_node(node).inputs.source_file = dwi_file

    return workflow


def clean_datasinks(workflow: pe.Workflow) -> pe.Workflow:
    """Overwrite ``out_path_base`` of DataSinks."""
    for node in workflow.list_node_names():
        if node.split('.')[-1].startswith('ds_'):
            workflow.get_node(node).interface.out_path_base = ''
    return workflow
