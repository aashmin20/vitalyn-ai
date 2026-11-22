"""
bilstm_model.py — BiLSTM fall classifier.

Architecture is reconstructed from the saved state_dict:
  lstm.weight_ih_l0:  [256, 34]  → input_size=34, hidden_size=64, 2 layers, bidirectional
  fc1.weight:         [32, 128]  → 128 = hidden_size*2 (bidirectional), out=32
  fc2.weight:         [1,  32]   → binary sigmoid output

Input:  (batch, seq_len, 34)  — sequence of normalised keypoint vectors
Output: (batch, 1)            — sigmoid probability of fall
"""
from __future__ import annotations

import torch
import torch.nn as nn
import numpy as np
from typing import Optional

from config import (
    BILSTM_MODEL_PATH,
    BILSTM_INPUT_SIZE,
    BILSTM_HIDDEN_SIZE,
    BILSTM_NUM_LAYERS,
    BILSTM_FC1_OUT,
    FALL_THRESHOLD,
)


class BiLSTMFallClassifier(nn.Module):
    def __init__(
        self,
        input_size: int = BILSTM_INPUT_SIZE,
        hidden_size: int = BILSTM_HIDDEN_SIZE,
        num_layers: int = BILSTM_NUM_LAYERS,
        fc1_out: int = BILSTM_FC1_OUT,
        dropout: float = 0.3,
    ):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            bidirectional=True,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.fc1     = nn.Linear(hidden_size * 2, fc1_out)
        self.relu    = nn.ReLU()
        self.dropout = nn.Dropout(dropout)
        self.fc2     = nn.Linear(fc1_out, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq_len, input_size)
        out, _ = self.lstm(x)
        # Global average pooling over all timesteps (matches training notebook)
        pooled = torch.mean(out, dim=1)        # (batch, hidden*2)
        logit = self.fc2(self.relu(self.fc1(pooled)))
        return torch.sigmoid(logit)            # (batch, 1)


class FallClassifier:
    """
    Loads the trained BiLSTM and classifies a window of keypoint sequences.
    Thread-safe after __init__.
    """

    def __init__(self):
        self._model: Optional[BiLSTMFallClassifier] = None
        self._device = "mps" if torch.backends.mps.is_available() else "cpu"

    def _load(self) -> BiLSTMFallClassifier:
        if self._model is None:
            model = BiLSTMFallClassifier()
            state = torch.load(BILSTM_MODEL_PATH, map_location="cpu", weights_only=True)
            model.load_state_dict(state)
            model.eval()
            model.to(self._device)
            self._model = model
        return self._model

    def predict(self, sequence: np.ndarray) -> tuple[float, bool]:
        """
        Classify a sequence of keypoint vectors.

        Args:
            sequence: np.ndarray of shape (seq_len, 34)

        Returns:
            (probability, is_fall) where probability ∈ [0,1]
        """
        model = self._load()

        # (1, seq_len, 34)
        x = torch.tensor(sequence, dtype=torch.float32).unsqueeze(0).to(self._device)

        with torch.no_grad():
            prob = model(x).item()

        return prob, prob >= FALL_THRESHOLD
