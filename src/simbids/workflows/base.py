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

from copy import deepcopy

from packaging.version import Version

from simbids import config


def init_simbids_wf():
    """Build *SimBIDS*'s pipeline.

    This workflow organizes the execution of SimBIDS,
    with a sub-workflow for each subject.

    Workflow Graph
        .. workflow::
            :graph2use: orig
            :simple_form: yes

            from simbids.workflows.tests import mock_config
            from simbids.workflows.base import init_simbids_wf

            with mock_config():
                wf = init_simbids_wf()

    """
    from niworkflows.engine.workflows import LiterateWorkflow as Workflow

    ver = Version(config.environment.version)

    simbids_wf = Workflow(name=f'simbids_{ver.major}_{ver.minor}_wf')
    simbids_wf.base_dir = config.execution.work_dir

    for subject_id in config.execution.participant_label:
        single_subject_wf = init_single_subject_wf(subject_id)

        single_subject_wf.config['execution']['crashdump_dir'] = str(
            config.execution.output_dir / f'sub-{subject_id}' / 'log' / config.execution.run_uuid
        )
        for node in single_subject_wf._get_all_nodes():
            node.config = deepcopy(single_subject_wf.config)

        simbids_wf.add_nodes([single_subject_wf])

        # Dump a copy of the config file into the log directory
        log_dir = (
            config.execution.output_dir / f'sub-{subject_id}' / 'log' / config.execution.run_uuid
        )
        log_dir.mkdir(exist_ok=True, parents=True)
        config.to_filename(log_dir / 'simbids.toml')

    return simbids_wf


def init_single_subject_wf(subject_id: str):
    """Organize the postprocessing pipeline for a single subject.

    It collects and reports information about the subject,
    and prepares sub-workflows to postprocess each BOLD series.

    Workflow Graph
        .. workflow::
            :graph2use: orig
            :simple_form: yes

            from simbids.workflows.tests import mock_config
            from simbids.workflows.base import init_single_subject_wf

            with mock_config():
                wf = init_single_subject_wf('01')

    Parameters
    ----------
    subject_id : :obj:`str`
        Subject label for this single-subject workflow.
    """
    from bids.utils import listify

    from simbids.utils.bids import collect_derivatives

    entities = config.execution.bids_filters or {}
    entities['subject'] = subject_id

    if config.execution.derivatives:
        # Raw dataset + derivatives dataset
        config.loggers.workflow.info('Raw+derivatives workflow mode enabled')
        # Just build a list of BOLD files right now
        subject_data = collect_derivatives(
            raw_dataset=config.execution.layout,
            derivatives_dataset=None,
            entities=entities,
            fieldmap_id=None,
            allow_multiple=True,
            spaces=None,
        )
        subject_data['bold'] = listify(subject_data['bold_raw'])
    else:
        # Derivatives dataset only
        config.loggers.workflow.info('Derivatives-only workflow mode enabled')
        # Just build a list of BOLD files right now
        subject_data = collect_derivatives(
            raw_dataset=None,
            derivatives_dataset=config.execution.layout,
            entities=entities,
            fieldmap_id=None,
            allow_multiple=True,
            spaces=None,
        )
        # Patch standard-space BOLD files into 'bold' key
        subject_data['bold'] = listify(subject_data['bold_mni152nlin6asym'])

    if config.workflow.simulated_app == 'fmripost':
        from simbids.workflows.xcp_d.xcp_d import init_single_subject_fmripost_wf

        return init_single_subject_fmripost_wf(subject_id, subject_data)
    elif config.workflow.simulated_app == 'qsiprep':
        from simbids.workflows.qsiprep import init_single_subject_qsiprep_wf

        return init_single_subject_qsiprep_wf(subject_id, subject_data)
    else:
        raise ValueError(f'Unknown application: {config.workflow.simulated_app}')
