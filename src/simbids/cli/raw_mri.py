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
"""Command-line interface for creating raw MRI data from a BIDS skeleton."""

import logging
from importlib import resources
from pathlib import Path

from simbids.utils.bids import simulate_dataset

LGR = logging.getLogger(__name__)

# Get all the yaml files using importlib
with resources.path('simbids.data.bids_mri', '') as bids_mri_path:
    yaml_files = [f.name for f in bids_mri_path.glob('*.yaml')]


def _build_parser(**kwargs):
    """Build parser object."""
    from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser

    parser = ArgumentParser(
        description='Create a BIDS skeleton from raw MRI data.',
        formatter_class=ArgumentDefaultsHelpFormatter,
        **kwargs,
    )

    parser.add_argument(
        'bids_dir',
        type=Path,
        help='Path to the output BIDS dataset created from the skeleton.',
    )

    parser.add_argument(
        'config_file',
        type=str,
        help='YAML file to use for creating the skeleton.',
    )

    parser.add_argument(
        '--fill-files',
        action='store_true',
        help='Fill the files with random data.',
    )

    return parser


def main():
    """Entry point."""

    parser = _build_parser()
    args = parser.parse_args()

    # If the config file is not in the list of available config files, it's a custom config file
    if args.config_file not in yaml_files:
        LGR.info(f'Using user-provided config file: {args.config_file}')
        config_path = Path(args.config_file)
        if not config_path.exists():
            raise FileNotFoundError(f'Config file {args.config_file} not found')
        # For custom config files, pass the string path
        simulate_dataset(args.bids_dir, str(config_path), args.fill_files)
    else:
        LGR.info(f'Using bundled config file: {args.config_file}')
        # For bundled config files, pass the filename directly
        simulate_dataset(args.bids_dir, args.config_file, args.fill_files)


if __name__ == '__main__':
    main()
