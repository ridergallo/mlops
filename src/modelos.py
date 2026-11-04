"""Referencia sencilla y serializable para pronosticar la siguiente hora."""

import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin


class Persistencia(RegressorMixin, BaseEstimator):
    def fit(self, X, y=None):
        self.n_features_in_ = X.shape[1]
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        return self

    def predict(self, X):
        return X["temperatura_actual"].to_numpy(dtype=float)
