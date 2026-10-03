"""
A small, dependency-free logistic-regression classifier.

Stage 4 trains a real model on analyst decisions, so it must run in any
environment — including restricted boxes where the heavy ML stack (numpy,
scipy, ...) is not installed. The classifier is therefore pure Python /
standard library.

The model is tiny by design: the feature vectors produced by
``learning.features`` are short and structured, and the training set is the set
of incidents an analyst has labelled. Batch gradient descent on standardised
features converges fine at that scale.

The trained model serialises to a plain JSON-able dict (``to_dict`` /
``from_dict``) so it can be stored on ``FineTuningRun.model_artifact`` and
reloaded for inference without any binary pickle.
"""
from __future__ import annotations

import math
from typing import Sequence


def sigmoid(z: float) -> float:
    """Numerically stable logistic function."""
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


class LogisticRegression:
    """Binary logistic regression trained with batch gradient descent.

    Features are standardised internally (zero mean, unit variance) using
    statistics learned at ``fit`` time, so callers pass raw feature vectors for
    both training and prediction.
    """

    def __init__(self, learning_rate: float = 0.1, epochs: int = 800, l2: float = 0.01) -> None:
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.l2 = l2
        self.weights: list[float] = []
        self.bias: float = 0.0
        self.mean: list[float] = []
        self.std: list[float] = []
        self.n_features: int = 0

    # -- standardisation ----------------------------------------------------
    def _fit_scaler(self, X: Sequence[Sequence[float]]) -> None:
        n, d = len(X), len(X[0])
        self.mean = [0.0] * d
        self.std = [0.0] * d
        for j in range(d):
            col = [float(row[j]) for row in X]
            m = sum(col) / n
            var = sum((v - m) ** 2 for v in col) / n
            self.mean[j] = m
            self.std[j] = math.sqrt(var) if var > 1e-12 else 1.0

    def _standardize(self, x: Sequence[float]) -> list[float]:
        return [(float(x[j]) - self.mean[j]) / self.std[j] for j in range(self.n_features)]

    # -- training -----------------------------------------------------------
    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> "LogisticRegression":
        if not X:
            raise ValueError("Cannot fit on an empty dataset.")
        if len(X) != len(y):
            raise ValueError("X and y must have the same length.")

        self.n_features = len(X[0])
        self._fit_scaler(X)
        Z = [self._standardize(row) for row in X]
        self.weights = [0.0] * self.n_features
        self.bias = 0.0
        n = len(Z)

        for _ in range(self.epochs):
            grad_w = [0.0] * self.n_features
            grad_b = 0.0
            for i in range(n):
                error = sigmoid(self._raw(Z[i])) - float(y[i])
                for j in range(self.n_features):
                    grad_w[j] += error * Z[i][j]
                grad_b += error
            for j in range(self.n_features):
                grad_w[j] = grad_w[j] / n + self.l2 * self.weights[j]
                self.weights[j] -= self.learning_rate * grad_w[j]
            self.bias -= self.learning_rate * (grad_b / n)

        return self

    def _raw(self, z: Sequence[float]) -> float:
        total = self.bias
        for j in range(self.n_features):
            total += self.weights[j] * z[j]
        return total

    # -- inference ----------------------------------------------------------
    def predict_proba(self, x: Sequence[float]) -> float:
        if self.n_features == 0:
            raise ValueError("Model is not trained.")
        return sigmoid(self._raw(self._standardize(x)))

    def predict(self, x: Sequence[float], threshold: float = 0.5) -> int:
        return 1 if self.predict_proba(x) >= threshold else 0

    # -- (de)serialisation --------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "type": "logistic_regression",
            "n_features": self.n_features,
            "weights": list(self.weights),
            "bias": self.bias,
            "mean": list(self.mean),
            "std": list(self.std),
            "hyperparameters": {
                "learning_rate": self.learning_rate,
                "epochs": self.epochs,
                "l2": self.l2,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LogisticRegression":
        hp = data.get("hyperparameters", {})
        model = cls(
            learning_rate=hp.get("learning_rate", 0.1),
            epochs=hp.get("epochs", 800),
            l2=hp.get("l2", 0.01),
        )
        model.n_features = data["n_features"]
        model.weights = list(data["weights"])
        model.bias = float(data["bias"])
        model.mean = list(data["mean"])
        model.std = list(data["std"])
        return model


def evaluate(y_true: Sequence[float], y_pred: Sequence[int]) -> dict:
    """Precision / recall / FPR / accuracy for binary predictions (positive==1).

    Returns 0.0 for a metric whose denominator is empty rather than raising.
    """
    tp = fp = tn = fn = 0
    for actual, predicted in zip(y_true, y_pred):
        actual = int(round(float(actual)))
        if predicted == 1 and actual == 1:
            tp += 1
        elif predicted == 1 and actual == 0:
            fp += 1
        elif predicted == 0 and actual == 0:
            tn += 1
        else:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total if total else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "false_positive_rate": fpr,
        "accuracy": accuracy,
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
    }
