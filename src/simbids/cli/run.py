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
"""Simulated BIDS workflows."""

from simbids import config

EXITCODE: int = -1


def main():
    """Entry point."""
    import gc
    import sys
    from multiprocessing import Manager, Process

    from simbids.cli.parser import parse_args
    from simbids.cli.raw_mri import main as raw_mri_main
    from simbids.cli.workflow import build_workflow

    # Code Carbon
    if config.execution.track_carbon:
        pass

    if 'pdb' in config.execution.debug:
        from simbids.utils.debug import setup_exceptionhook

        setup_exceptionhook()
        config.nipype.plugin = 'Linear'

    # CRITICAL Save the config to a file. This is necessary because the execution graph
    # is built as a separate process to keep the memory footprint low. The most
    # straightforward way to communicate with the child process is via the filesystem.
    config_file = config.execution.work_dir / config.execution.run_uuid / 'config.toml'
    config_file.parent.mkdir(exist_ok=True, parents=True)
    config.to_filename(config_file)

    # CRITICAL Call build_workflow(config_file, retval) in a subprocess.
    # Because Python on Linux does not ever free virtual memory (VM), running the
    # workflow construction jailed within a process preempts excessive VM buildup.
    if 'pdb' not in config.execution.debug:
        with Manager() as mgr:
            retval = mgr.dict()
            p = Process(target=build_workflow, args=(str(config_file), retval))
            p.start()
            p.join()
            retval = dict(retval.items())  # Convert to base dictionary

            if p.exitcode:
                retval['return_code'] = p.exitcode

    else:
        retval = build_workflow(str(config_file), {})

    global EXITCODE
    EXITCODE = retval.get('return_code', 0)
    simbids_wf = retval.get('workflow', None)

    # CRITICAL Load the config from the file. This is necessary because the ``build_workflow``
    # function executed constrained in a process may change the config (and thus the global
    # state of SimBIDS).
    config.load(config_file)

    # Clean up master process before running workflow, which may create forks
    gc.collect()

    config.loggers.workflow.log(
        15,
        '\n'.join(['SimBIDS config:'] + [f'\t\t{s}' for s in config.dumps().splitlines()]),
    )
    config.loggers.workflow.log(25, 'SimBIDS started!')
    try:
        simbids_wf.run(**config.nipype.get_plugin())
    except Exception as e:
        config.loggers.workflow.critical('SimBIDS failed: %s', e)
        raise

    else:
        config.loggers.workflow.log(25, 'SimBIDS finished successfully!')


if __name__ == '__main__':
    raise RuntimeError(
        'simbids/cli/run.py should not be run directly;\n'
        'Please `pip install` simbids and use the `simbids` command'
    )
