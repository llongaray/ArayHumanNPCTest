"""Numerical-run evidence checks; never train or evaluate held-out inputs."""
import hashlib
import json
from pathlib import Path

import pytest

from benchmark_neural import confidence_summary,latency
from neural_runtime import verify_manifest

ROOT=Path(__file__).resolve().parent
RUN=ROOT/'neural_artifacts'/'3c5b1-seed1729'

def test_latency_reports_tail_not_only_average():
    report=latency([1.0]*19+[100.0])
    assert report['median_ms']==1 and report['p95_ms']==100

def test_confidence_keeps_empty_bins_unknown():
    records=[{'expected':{'decision':'WAIT'},'prediction':{'decision':'WAIT','confidence':.95}},
             {'expected':{'decision':'WAIT'},'prediction':{'decision':'EXECUTE_ACTION','confidence':.4}}]
    report=confidence_summary(records)
    assert report['calibrated'] is False
    assert report['bins'][1]['decision_accuracy'] is None
    assert report['bins'][0]['decision_accuracy']==0

@pytest.mark.skipif(not (RUN/'manifest.json').is_file(),reason='optional numerical run absent')
def test_real_experimental_checkpoint_cannot_activate():
    manifest=json.loads((RUN/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['trained'] and not manifest['validated']
    with pytest.raises(ValueError):verify_manifest(RUN)

@pytest.mark.skipif(not (RUN/'manifest.json').is_file(),reason='optional numerical run absent')
def test_selected_weights_and_single_pass_predictions_preserved():
    manifest=json.loads((RUN/'manifest.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((RUN/'weights.pt').read_bytes()).hexdigest()==manifest['weights_sha256']
    assert manifest['test_evaluations']==1 and manifest['selection_uses_test'] is False
    predictions=json.loads((RUN/'test-predictions.json').read_text(encoding='utf-8'))
    assert len(predictions)==162 and [r['index'] for r in predictions]==list(range(162))

@pytest.mark.skipif(not (ROOT/'neural_environment'/'training-protocol.json').is_file(),reason='optional numerical run absent')
@pytest.mark.parametrize('name',['neural_model.py','neural_data.py','neural_contract.py','neural_runtime.py','neural_encoder.py'])
def test_frozen_learning_components_unchanged(name):
    protocol=json.loads((ROOT/'neural_environment'/'training-protocol.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==protocol['source_before_instrumentation'][name]
