#################
SimBIDS
#################

A generic SimBIDS workflow.

********
Overview
********

SimBIDS is a template repository that can be used to create new SimBIDS workflows.

The workflows and functions in this repository are designed to implement the majority of
general-purpose steps in an SimBIDS pipeline.
Here are a few of the key features:

1.  Configuration files to define expected BIDS derivatives from the preprocessing pipeline.
2.  Functions to collect and organize data from the BIDS derivatives.
3.  The ability to work with the following preprocessing configurations:

    -   fMRIPrep with ``--level full`` and the required output space for the SimBIDS workflow.
        For example, SimBIDS-AROMA requires outputs in ``MNI152NLin6Asym`` space with
        2x2x2 mm voxels.
    -   fMRIPrep with ``--level full`` and boldref-space outputs,
        along with transforms to the required output space for the SimBIDS workflow.
    -   fMRIPrep with ``--level full`` and boldref-space outputs,
        along with transforms to spaces that can be combined with existing transforms to
        required spaces.
        For example, users may apply SimBIDS-AROMA to boldref derivatives with transforms to
        MNI152NLin2009cAsym space.
        In this case, the SimBIDS-AROMA workflow will pull a transform from MNI152NLin2009cAsym
        to MNI152NLin6Asym from TemplateFlow and apply it,
        along with the boldref-to-MNI152NLin2009cAsym transform, to the boldref-space derivatives.
    -   fMRIPrep with ``--level full`` and raw BOLD data.
        In this case, the SimBIDS workflow will apply minimal preprocessing steps internally
        to generate the required derivatives.
        This will rarely be used, but may be useful for SimBIDS workflows that require raw data,
        like SimBIDS-phase.

    .. warning::

        Currently, minimal- and resampling-level fMRIPrep derivatives are not supported,
        as SimBIDS workflows typically require confounds that are only generated with
        ``--level full``.

4.  General NiPreps infrastructure for running a BIDS App, such as a config file,
    a command-line interface, and tools to generate HTML reports.


*****
Usage
*****

If you use this template to create a new SimBIDS workflow, you will need to:

1.  Replace all instances of ``simbids`` with the name of your new workflow.
2.  Replace all instances of ``SimBIDS`` with the name of your new workflow.
3.  Modify the workflows and interfaces to apply your desired processing steps.
4.  Update the documentation to reflect the new workflow.

Please also include something like the following in your boilerplate:

> Data were postprocessed using *SimBIDS-<name>*,
> which is based on *SimBIDS* ([cite SimBIDS version and DOI here]).
