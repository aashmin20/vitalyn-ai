"""
Tests for the BiLSTM fall classifier (bilstm_model.py).

Tests verify:
  - Model loads without error
  - Output is a valid probability in [0, 1]
  - Zero input (no person) produces high fall probability (documented behaviour)
  - Output shape is correct
  - Model is deterministic in eval mode
  - predict() returns (float, bool) correctly
"""
import numpy as np
import pytest
import torch
from bilstm_model import BiLSTMFallClassifier, FallClassifier
from config import FALL_THRESHOLD


class TestBiLSTMArchitecture:
    """Unit tests for model architecture and weight loading."""

    def test_model_instantiates(self):
        model = BiLSTMFallClassifier()
        assert model is not None

    def test_model_loads_checkpoint(self, fall_classifier):
        """Checkpoint loads without KeyError — architecture matches saved weights."""
        model = fall_classifier._load()
        assert model is not None

    def test_lstm_has_correct_layers(self, fall_classifier):
        model = fall_classifier._load()
        assert model.lstm.num_layers == 2
        assert model.lstm.bidirectional is True
        assert model.lstm.input_size == 34
        assert model.lstm.hidden_size == 64

    def test_fc_dimensions(self, fall_classifier):
        model = fall_classifier._load()
        assert model.fc1.in_features == 128   # hidden_size * 2 (bidirectional)
        assert model.fc1.out_features == 32
        assert model.fc2.in_features == 32
        assert model.fc2.out_features == 1

    def test_model_in_eval_mode_after_load(self, fall_classifier):
        model = fall_classifier._load()
        assert not model.training


class TestFallClassifierPredict:
    """Tests for FallClassifier.predict()."""

    def test_output_is_probability(self, fall_classifier, standing_seq):
        prob, is_fall = fall_classifier.predict(standing_seq)
        assert 0.0 <= prob <= 1.0

    def test_output_types(self, fall_classifier, standing_seq):
        prob, is_fall = fall_classifier.predict(standing_seq)
        assert isinstance(prob, float)
        assert isinstance(is_fall, bool)

    def test_is_fall_matches_threshold(self, fall_classifier, standing_seq):
        prob, is_fall = fall_classifier.predict(standing_seq)
        assert is_fall == (prob >= FALL_THRESHOLD)

    def test_original_checkpoint_reads_an_empty_window_as_a_fall(self, zero_seq):
        """Known flaw of the ORIGINAL checkpoint (why the 80% person-coverage guard exists)."""
        import os
        from config import ML_ENGINE_DIR
        original = FallClassifier(os.path.join(ML_ENGINE_DIR, "vitalyn_fall_bilstm.pt"), threshold=0.45)
        prob, _ = original.predict(zero_seq)
        assert prob > 0.5

    def test_retrained_model_does_not_read_an_empty_window_as_a_fall(self, zero_seq):
        import os
        from config import ML_ENGINE_DIR
        path = os.path.join(ML_ENGINE_DIR, "vitalyn_fall_bilstm_v2.pt")
        if not os.path.exists(path):
            pytest.skip("retrained weights not present (run train_bilstm.py)")
        prob, is_fall = FallClassifier(path, threshold=0.65).predict(zero_seq)
        assert prob < 0.5 and not is_fall

    def test_deterministic_in_eval_mode(self, fall_classifier, standing_seq):
        """Same input must produce identical output (model is in eval mode, no dropout)."""
        p1, _ = fall_classifier.predict(standing_seq)
        p2, _ = fall_classifier.predict(standing_seq)
        assert p1 == p2

    def test_accepts_numpy_array(self, fall_classifier, standing_seq):
        assert isinstance(standing_seq, np.ndarray)
        prob, _ = fall_classifier.predict(standing_seq)
        assert isinstance(prob, float)

    def test_sequence_shape_30x34(self, fall_classifier):
        seq = np.random.rand(30, 34).astype(np.float32)
        prob, _ = fall_classifier.predict(seq)
        assert 0.0 <= prob <= 1.0

    def test_different_inputs_produce_different_outputs(
        self, fall_classifier, standing_seq, zero_seq
    ):
        """Standing vs no-person should not produce identical probability."""
        p_stand, _ = fall_classifier.predict(standing_seq)
        p_zero,  _ = fall_classifier.predict(zero_seq)
        assert p_stand != p_zero


class TestFallClassifierEdgeCases:
    """Edge cases and boundary conditions."""

    def test_all_ones_input(self, fall_classifier):
        seq = np.ones((30, 34), dtype=np.float32)
        prob, _ = fall_classifier.predict(seq)
        assert 0.0 <= prob <= 1.0

    def test_normalised_coords_in_range(self, fall_classifier):
        """Normalised [0,1] coords should not cause NaN or inf."""
        seq = np.clip(np.random.rand(30, 34).astype(np.float32), 0.0, 1.0)
        prob, _ = fall_classifier.predict(seq)
        assert not np.isnan(prob)
        assert not np.isinf(prob)

    def test_single_nonzero_frame_rest_zeros(self, fall_classifier):
        seq = np.zeros((30, 34), dtype=np.float32)
        seq[15] = np.random.rand(34).astype(np.float32)
        prob, _ = fall_classifier.predict(seq)
        assert 0.0 <= prob <= 1.0
