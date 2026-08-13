#################
SimBIDS
#################

Simulate BIDS datasets and BIDS derivatives for CI testing.

********
Overview
********

SimBIDS creates BIDS datasets and derivative trees with the right paths, filenames, and JSON sidecars, but without image data.
Image files are created empty, or filled with random bytes if you ask for it.

That makes it useful for testing tools that *orchestrate* BIDS Apps (ie schedulers, provenance trackers, workflow engines) which need to resolve paths, discover subjects, and consume outputs, but never read a voxel.
Such a test can run in seconds instead of hours, and needs no real data.

************
Installation
************

SimBIDS is distributed as a container image on `Docker Hub <https://hub.docker.com/r/pennlinc/simbids>`_::

    docker pull pennlinc/simbids:0.0.3

The image default entry point is ``simbids``, so reaching ``simbids-raw-mri`` means overriding it::

    docker run --rm -v /path/to/data:/data --entrypoint simbids-raw-mri pennlinc/simbids:0.0.3 \
        /data ds004146_configs.yaml

That writes a raw dataset to ``/path/to/data/simbids/``.
Simulating a BIDS App's derivatives from it uses the entry point as-is::

    docker run --rm -v /path/to/data:/data pennlinc/simbids:0.0.3 \
        /data/simbids /data/derivatives participant --bids-app fmriprep

Podman works the same way, substituting ``podman`` for ``docker``.

*********************************************
``simbids-raw-mri``: simulate a raw dataset
*********************************************

Creates a raw BIDS dataset from a YAML skeleton::

    simbids-raw-mri <bids_dir> <config_file> [--fill-files] [--datalad-init]

``config_file`` is either the name of a bundled skeleton or a path to your own.
The bundled skeletons live in ``src/simbids/data/bids_mri/``, and several are modeled on real OpenNeuro datasets.

The dataset is written to a ``simbids/`` subdirectory of ``bids_dir``.

``--fill-files`` fills each image file with random bytes rather than leaving it empty.
The result is not valid NIfTI, but does allow files to have a realistic size.

``--datalad-init`` makes the output a DataLad dataset.

*************************************************
``simbids``: simulate a BIDS App's derivatives
*************************************************

Takes a raw BIDS dataset and writes the derivative tree a given BIDS App would produce::

    simbids <bids_dir> <output_dir> participant --bids-app {fmriprep,qsiprep,qsirecon,xcp_d}

``--anat-only`` restricts output to the anatomical workflow.

SimBIDS implements the BIDS App command-line interface and is built on the NiPreps config, CLI, and reporting infrastructure.
