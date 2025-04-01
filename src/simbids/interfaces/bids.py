"""BIDS-related interfaces for SimBIDS."""

from json import loads

from bids.layout import Config
from niworkflows.interfaces.bids import DerivativesDataSink as BaseDerivativesDataSink

from simbids.data import load as load_data


class DerivativesDataSink(BaseDerivativesDataSink):
    """Store derivative files.

    A child class of the niworkflows DerivativesDataSink,
    using simbids's configuration files.
    """

    simbids_spec = loads(load_data('io_spec.json').read_text())
    bids_config = Config.load('bids')
    deriv_config = Config.load('derivatives')

    simbids_entities = {v['name']: v['pattern'] for v in simbids_spec['entities']}
    merged_entities = {**bids_config.entities, **deriv_config.entities}
    merged_entities = {k: v.pattern for k, v in merged_entities.items()}
    merged_entities = {**merged_entities, **simbids_entities}
    merged_entities = [{'name': k, 'pattern': v} for k, v in merged_entities.items()]
    config_entities = frozenset({e['name'] for e in merged_entities})
    out_path_base = ''
    _allowed_entities = set(config_entities)
    _config_entities = config_entities
    _config_entities_dict = merged_entities
    _file_patterns = simbids_spec['default_path_patterns']


class QSIPrepDerivativesDataSink(BaseDerivativesDataSink):
    """Store derivative files.

    A child class of the niworkflows DerivativesDataSink,
    using simbids's configuration files.
    """

    simbids_spec = loads(load_data('qsiprep_io_spec.json').read_text())
    bids_config = Config.load('bids')
    deriv_config = Config.load('derivatives')

    simbids_entities = {v['name']: v['pattern'] for v in simbids_spec['entities']}
    merged_entities = {**bids_config.entities, **deriv_config.entities}
    merged_entities = {k: v.pattern for k, v in merged_entities.items()}
    merged_entities = {**merged_entities, **simbids_entities}
    merged_entities = [{'name': k, 'pattern': v} for k, v in merged_entities.items()]
    config_entities = frozenset({e['name'] for e in merged_entities})
    out_path_base = ''
    _allowed_entities = set(config_entities)
    _config_entities = config_entities
    _config_entities_dict = merged_entities
    _file_patterns = simbids_spec['default_path_patterns']


class QSIReconDerivativesDataSink(BaseDerivativesDataSink):
    """Store derivative files.

    A child class of the niworkflows DerivativesDataSink,
    using simbids's configuration files.
    """

    simbids_spec = loads(load_data('qsirecon_io_spec.json').read_text())
    bids_config = Config.load('bids')
    deriv_config = Config.load('derivatives')

    simbids_entities = {v['name']: v['pattern'] for v in simbids_spec['entities']}
    merged_entities = {**bids_config.entities, **deriv_config.entities}
    merged_entities = {k: v.pattern for k, v in merged_entities.items()}
    merged_entities = {**merged_entities, **simbids_entities}
    merged_entities = [{'name': k, 'pattern': v} for k, v in merged_entities.items()]
    config_entities = frozenset({e['name'] for e in merged_entities})
    out_path_base = ''
    _allowed_entities = set(config_entities)
    _config_entities = config_entities
    _config_entities_dict = merged_entities
    _file_patterns = simbids_spec['default_path_patterns']