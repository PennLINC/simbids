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

import json
import sys
from importlib import resources
from pathlib import Path

import nipype.pipeline.engine as pe
import yaml
from niworkflows.engine.workflows import LiterateWorkflow as Workflow
from niworkflows.interfaces.bids import BIDSInfo

from simbids import config
from simbids.interfaces.bids import QSIReconDerivativesDataSink as DerivativesDataSink
from simbids.interfaces.reportlets import AboutSummary, SubjectSummary
from simbids.utils.utils import _get_wf_name

text_file = resources.files('simbids').joinpath('data/text_file.txt')


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


def init_single_subject_qsirecon_wf(subject_id: str):
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

    first_dwi_file = subject_data['dwi'][0]
    # Add atlases for the first DWI file
    workflow.add_nodes(_get_root_dwi_subject_datasinks(first_dwi_file))
    for dwi_file in subject_data['dwi']:
        workflow.add_nodes(
            _get_tortoise_mapmri_datasinks(dwi_file)
            + _get_mrtrix_datasinks(dwi_file)
            + _get_dipy_datasinks(dwi_file)
            + _get_dsi_studio_datasinks(dwi_file)
        )

    anat_file = (subject_data['t1w'] + subject_data.get('t2w', []))[0]
    workflow.add_nodes(_get_hsvs_datasinks(anat_file))

    return clean_datasinks(workflow)


def _get_root_dwi_subject_datasinks(dwi_file: str):
    """Get the datasinks for the sub-directory in the root output directory."""
    base_dir = config.execution.output_dir
    return [
        pe.Node(
            DerivativesDataSink(
                source_file=dwi_file,
                in_file=dwi_file,
                base_directory=base_dir,
                suffix='dseg',
                seg='4S156Parcels',
                space='ACPC',
                extension='.nii.gz',
            ),
            name=_get_wf_name(dwi_file, 'ds_4S156Parcels_nifti'),
            run_without_submitting=True,
        ),
        pe.Node(
            DerivativesDataSink(
                source_file=dwi_file,
                in_file=dwi_file,
                base_directory=base_dir,
                suffix='dseg',
                seg='4S156Parcels',
                space='ACPC',
                extension='.mif.gz',
            ),
            name=_get_wf_name(dwi_file, 'ds_4S156Parcels_mif'),
            run_without_submitting=True,
        ),
        pe.Node(
            DerivativesDataSink(
                source_file=dwi_file,
                in_file=text_file,
                base_directory=base_dir,
                suffix='dseg',
                seg='4S156Parcels',
                space='ACPC',
                extension='.txt',
            ),
            name=_get_wf_name(dwi_file, 'ds_4S156Parcels_txt'),
            run_without_submitting=True,
        ),
    ]


def _get_tortoise_mapmri_datasinks(dwi_file: str):
    """Get the datasinks for the tortoise mapmri."""
    base_dir = config.execution.output_dir / 'derivatives' / 'qsirecon-TORTOISE'
    return [
        pe.Node(
            DerivativesDataSink(
                source_file=dwi_file,
                in_file=dwi_file,
                base_directory=base_dir,
                model='mapmri',
                param='rtop',
                suffix='dwimap',
                extension='.nii.gz',
            ),
            name=_get_wf_name(dwi_file, 'ds_tortoise_mapmri_rtop'),
            run_without_submitting=True,
        ),
        pe.Node(
            DerivativesDataSink(
                source_file=dwi_file,
                in_file=dwi_file,
                base_directory=base_dir,
                model='mapmri',
                param='rtap',
                suffix='dwimap',
                extension='.nii.gz',
            ),
            name=_get_wf_name(dwi_file, 'ds_tortoise_mapmri_rtap'),
            run_without_submitting=True,
        ),
        pe.Node(
            DerivativesDataSink(
                source_file=dwi_file,
                in_file=dwi_file,
                base_directory=base_dir,
                model='mapmri',
                param='rtpp',
                suffix='dwimap',
                extension='.nii.gz',
            ),
            name=_get_wf_name(dwi_file, 'ds_tortoise_mapmri_rtpp'),
            run_without_submitting=True,
        ),
        pe.Node(
            DerivativesDataSink(
                source_file=dwi_file,
                in_file=dwi_file,
                base_directory=base_dir,
                model='tensor',
                param='fa',
                suffix='dwimap',
                extension='.nii.gz',
            ),
            name=_get_wf_name(dwi_file, 'ds_tortoise_tensor_fa'),
            run_without_submitting=True,
        ),
    ]


def _get_dsi_studio_datasinks(source_file: str):
    """Add datasinks for DSI Studio outputs."""
    base_directory = config.execution.output_dir / 'derivatives' / 'qsirecon-DSIStudio'

    # Add datasinks for streamlines
    ds_arcuate_l = pe.Node(
        DerivativesDataSink(
            source_file=source_file,
            in_file=source_file,
            base_directory=base_directory,
            suffix='streamlines',
            extension='.tck.gz',
            model='gqi',
            bundle='AssociationArcuateFasciculusL',
        ),
        name=_get_wf_name(source_file, 'ds_dsi_studio_arcuate_l'),
        run_without_submitting=True,
    )

    ds_arcuate_r = pe.Node(
        DerivativesDataSink(
            source_file=source_file,
            in_file=source_file,
            base_directory=base_directory,
            suffix='streamlines',
            extension='.tck.gz',
            model='gqi',
            bundle='AssociationArcuateFasciculusR',
        ),
        name=_get_wf_name(source_file, 'ds_dsi_studio_arcuate_r'),
        run_without_submitting=True,
    )

    # Add datasink for bundle statistics
    ds_bundlestats = pe.Node(
        DerivativesDataSink(
            source_file=source_file,
            in_file=text_file,
            base_directory=base_directory,
            suffix='bundlestats',
            extension='.csv',
            model='gqi',
        ),
        name=_get_wf_name(source_file, 'ds_dsi_studio_bundlestats'),
        run_without_submitting=True,
    )

    # Add datasink for FIB file
    ds_fib = pe.Node(
        DerivativesDataSink(
            source_file=source_file,
            in_file=source_file,
            base_directory=base_directory,
            suffix='dwimap',
            extension='.fib.gz',
            model='gqi',
        ),
        name=_get_wf_name(source_file, 'ds_dsi_studio_fib'),
        run_without_submitting=True,
    )

    # Add datasink for ICBM152 map
    ds_icbm = pe.Node(
        DerivativesDataSink(
            source_file=source_file,
            in_file=source_file,
            base_directory=base_directory,
            suffix='dwimap',
            dsistudio_template='icbm152_adult',
            extension='.map.gz',
            model='gqi',
        ),
        name=_get_wf_name(source_file, 'ds_dsi_studio_icbm'),
        run_without_submitting=True,
    )

    return [ds_arcuate_l, ds_arcuate_r, ds_bundlestats, ds_fib, ds_icbm]


def _get_dipy_datasinks(source_file: str):
    """Add datasinks for DIPY DKI and tensor outputs."""
    base_directory = config.execution.output_dir / 'derivatives' / 'qsirecon-DKI'
    datasinks = []

    # DKI parameters
    dki_params = ['ad', 'ak', 'kfa', 'md', 'mk', 'mkt', 'rd', 'rk']
    for param in dki_params:
        # NIfTI file
        ds_nii = pe.Node(
            DerivativesDataSink(
                source_file=source_file,
                in_file=source_file,
                base_directory=base_directory,
                suffix='dwimap',
                extension='.nii.gz',
                model='dki',
                param=param,
            ),
            name=_get_wf_name(source_file, f'ds_dipy_dki_{param}'),
            run_without_submitting=True,
        )
        datasinks.append(ds_nii)

        # JSON file
        ds_json = pe.Node(
            DerivativesDataSink(
                source_file=source_file,
                in_file=source_file,
                base_directory=base_directory,
                suffix='dwimap',
                extension='.json',
                model='dki',
                param=param,
            ),
            name=_get_wf_name(source_file, f'ds_dipy_dki_{param}_json'),
            run_without_submitting=True,
        )
        datasinks.append(ds_json)

    # Tensor FA
    ds_fa_nii = pe.Node(
        DerivativesDataSink(
            source_file=source_file,
            in_file=source_file,
            base_directory=base_directory,
            suffix='dwimap',
            extension='.nii.gz',
            model='tensor',
            param='fa',
        ),
        name=_get_wf_name(source_file, 'ds_dipy_tensor_fa'),
        run_without_submitting=True,
    )
    datasinks.append(ds_fa_nii)

    ds_fa_json = pe.Node(
        DerivativesDataSink(
            source_file=source_file,
            in_file=source_file,
            base_directory=base_directory,
            suffix='dwimap',
            extension='.json',
            model='tensor',
            param='fa',
        ),
        name=_get_wf_name(source_file, 'ds_dipy_tensor_fa_json'),
        run_without_submitting=True,
    )
    datasinks.append(ds_fa_json)

    return datasinks


def _get_hsvs_datasinks(anat_file: str):
    """Get the datasinks for the hsvs."""
    base_dir = config.execution.output_dir
    return [
        pe.Node(
            DerivativesDataSink(
                source_file=anat_file,
                in_file=anat_file,
                base_directory=base_dir,
                seg='hsvs',
                suffix='probseg',
                extension='.nii.gz',
            ),
            name=_get_wf_name(anat_file, 'ds_hsvs_nifti'),
            run_without_submitting=True,
        ),
        pe.Node(
            DerivativesDataSink(
                source_file=anat_file,
                in_file=anat_file,
                base_directory=base_dir,
                space='fsnative',
                seg='hsvs',
                suffix='probseg',
                extension='.mif.gz',
            ),
            name=_get_wf_name(anat_file, 'ds_hsvs_mif'),
            run_without_submitting=True,
        ),
    ]


def _get_mrtrix_datasinks(source_file: str):
    """Add datasinks for MRtrix3 outputs."""
    base_directory = config.execution.output_dir / 'derivatives' / 'qsirecon-MRtrix3_act-HSVS'

    # Add datasinks for connectivity matrix
    ds_connectivity = pe.Node(
        DerivativesDataSink(
            source_file=source_file,
            in_file=text_file,
            base_directory=base_directory,
            desc='connectivity',
            suffix='connectivity',
            extension='.mat',
            model='msmtcsd',
            algorithm='sdstream',
            reconstruction='sift2',
        ),
        name=_get_wf_name(source_file, 'ds_mrtrix_act_hsvs_connectivity'),
        run_without_submitting=True,
    )

    # Add datasinks for exemplar bundles
    ds_exemplarbundles = pe.Node(
        DerivativesDataSink(
            source_file=source_file,
            in_file=text_file,
            base_directory=base_directory,
            desc='exemplarbundles',
            suffix='exemplarbundles',
            extension='.zip',
            model='msmtcsd',
            algorithm='sdstream',
            reconstruction='sift2',
        ),
        name=_get_wf_name(source_file, 'ds_mrtrix_act_hsvs_exemplarbundles'),
        run_without_submitting=True,
    )

    # Add datasinks for FOD maps
    for tissue in ['CSF', 'GM', 'WM']:
        ds_fod = pe.Node(
            DerivativesDataSink(
                source_file=source_file,
                in_file=text_file,
                base_directory=base_directory,
                desc='fod',
                suffix='dwimap',
                extension='.mif.gz',
                model='msmtcsd',
                param='fod',
                label=tissue,
            ),
            name=_get_wf_name(source_file, f'ds_mrtrix_act_hsvs_fod_{tissue.lower()}'),
            run_without_submitting=True,
        )

        # Add datasinks for FOD text files
        ds_fod_txt = pe.Node(
            DerivativesDataSink(
                source_file=source_file,
                in_file=text_file,
                base_directory=base_directory,
                desc='fod',
                suffix='dwimap',
                extension='.txt',
                model='msmtcsd',
                param='fod',
                label=tissue,
            ),
            name=_get_wf_name(source_file, f'ds_mrtrix_act_hsvs_fod_{tissue.lower()}_txt'),
            run_without_submitting=True,
        )

    # Add datasinks for MT normalization outputs
    ds_mtnorm_inliermask = pe.Node(
        DerivativesDataSink(
            source_file=source_file,
            in_file=source_file,
            base_directory=base_directory,
            desc='mtnorm',
            suffix='dwimap',
            extension='.nii.gz',
            model='mtnorm',
            param='inliermask',
        ),
        name=_get_wf_name(source_file, 'ds_mrtrix_act_hsvs_mtnorm_inliermask'),
        run_without_submitting=True,
    )

    ds_mtnorm_norm = pe.Node(
        DerivativesDataSink(
            source_file=source_file,
            in_file=source_file,
            base_directory=base_directory,
            desc='mtnorm',
            suffix='dwimap',
            extension='.nii.gz',
            model='mtnorm',
            param='norm',
        ),
        name=_get_wf_name(source_file, 'ds_mrtrix_act_hsvs_mtnorm_norm'),
        run_without_submitting=True,
    )

    # Add datasinks for streamlines
    ds_streamlines = pe.Node(
        DerivativesDataSink(
            source_file=source_file,
            in_file=source_file,
            base_directory=base_directory,
            desc='sdstream',
            suffix='streamlines',
            extension='.tck.gz',
            model='sdstream',
        ),
        name=_get_wf_name(source_file, 'ds_mrtrix_act_hsvs_streamlines'),
        run_without_submitting=True,
    )

    # Add datasinks for SIFT2 outputs
    ds_sift2_mu = pe.Node(
        DerivativesDataSink(
            source_file=source_file,
            in_file=text_file,
            base_directory=base_directory,
            desc='sift2',
            suffix='mu',
            extension='.txt',
            model='sift2',
        ),
        name=_get_wf_name(source_file, 'ds_mrtrix_act_hsvs_sift2_mu'),
        run_without_submitting=True,
    )

    ds_sift2_weights = pe.Node(
        DerivativesDataSink(
            source_file=source_file,
            in_file=text_file,
            base_directory=base_directory,
            desc='sift2',
            suffix='streamlineweights',
            extension='.csv',
            model='sift2',
        ),
        name=_get_wf_name(source_file, 'ds_mrtrix_act_hsvs_sift2_weights'),
        run_without_submitting=True,
    )
    return [
        ds_connectivity,
        ds_exemplarbundles,
        ds_fod,
        ds_fod_txt,
        ds_mtnorm_inliermask,
        ds_mtnorm_norm,
        ds_streamlines,
        ds_sift2_mu,
        ds_sift2_weights,
    ]


def write_root_level_atlases(output_dir: Path):
    """Write the atlases to the root level of the output directory."""
    # Create atlases directory
    atlases_dir = output_dir / 'atlases'
    atlases_dir.mkdir(exist_ok=True)

    # Create dataset_description.json
    dataset_desc = {
        'Name': 'SimBIDS Atlases',
        'BIDSVersion': '1.7.0',
        'DatasetType': 'derivative',
        'GeneratedBy': [
            {
                'Name': 'SimBIDS',
                'Version': config.environment.version,
                'Description': 'SimBIDS atlas collection',
            }
        ],
    }
    with open(atlases_dir / 'dataset_description.json', 'w') as f:
        json.dump(dataset_desc, f, indent=4)

    # Create 4S156Parcels atlas directory and files
    atlas_dir = atlases_dir / 'atlas-4S156Parcels'
    atlas_dir.mkdir(exist_ok=True)

    # Create empty TSV file
    (atlas_dir / 'atlas-4S156Parcels_dseg.tsv').touch()

    # Create empty NIfTI file
    (atlas_dir / 'atlas-4S156Parcels_space-MNI152NLin2009cAsym_res-01_dseg.nii.gz').touch()


def clean_datasinks(workflow: pe.Workflow) -> pe.Workflow:
    """Overwrite ``out_path_base`` of DataSinks."""
    for node in workflow.list_node_names():
        if node.split('.')[-1].startswith('ds_'):
            workflow.get_node(node).interface.out_path_base = ''
    return workflow
