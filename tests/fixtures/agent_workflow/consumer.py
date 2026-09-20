"""Tiny CPU consumer. Outputs observations, never expected judgments."""

def generate(cfg):
    counts = {source: len(list(range(cfg['samples_per_source']))) for source in cfg['sources']}
    output_limit = cfg['max_response_length']
    return {'counts': counts, 'output_limit': output_limit,
            'capacity_ok': cfg['max_prompt_length'] + output_limit <= cfg['context_window'],
            '_bindings': {
                'samples_per_source': {'config_key': 'samples_per_source', 'consumer_symbol': "cfg['samples_per_source']", 'value': counts},
                'max_response_length': {'config_key': 'max_response_length', 'consumer_symbol': "cfg['max_response_length']", 'value': output_limit}}}
