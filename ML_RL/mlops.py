"""
MLOps - Model Versioning, Drift Detection, and Automated Retraining

Provides infrastructure for:
1. Model versioning and registry
2. Data drift detection
3. Performance monitoring
4. Automated retraining triggers
5. A/B testing support

Part of Cthulu ML Pipeline v6.0.0
"""

from __future__ import annotations
import os
import json
import hashlib
import logging
import numpy as np
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import threading
from collections import deque

logger = logging.getLogger("cthulu.ml.mlops")

# Directory for model storage
MODEL_REGISTRY_DIR = os.path.join(os.path.dirname(__file__), 'models')
os.makedirs(MODEL_REGISTRY_DIR, exist_ok=True)

# Metrics storage
METRICS_DIR = os.path.join(os.path.dirname(__file__), 'data', 'metrics')
os.makedirs(METRICS_DIR, exist_ok=True)


class ModelStatus(Enum):
    """Model deployment status."""
    TRAINING = "training"
    VALIDATION = "validation"
    STAGING = "staging"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"
    FAILED = "failed"


class DriftType(Enum):
    """Types of drift detected."""
    NONE = "none"
    FEATURE_DRIFT = "feature_drift"
    PREDICTION_DRIFT = "prediction_drift"
    PERFORMANCE_DRIFT = "performance_drift"
    CONCEPT_DRIFT = "concept_drift"


@dataclass
class ModelMetadata:
    """Metadata for a registered model."""
    model_id: str
    model_type: str
    version: str
    status: ModelStatus
    created_at: str
    updated_at: str
    metrics: Dict[str, float]
    hyperparameters: Dict[str, Any]
    feature_names: List[str]
    training_samples: int
    validation_accuracy: float
    tags: List[str] = field(default_factory=list)
    description: str = ""
    path: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['status'] = self.status.value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModelMetadata':
        data['status'] = ModelStatus(data['status'])
        return cls(**data)


@dataclass
class DriftReport:
    """Drift detection report."""
    timestamp: str
    model_id: str
    drift_type: DriftType
    drift_score: float
    threshold: float
    triggered: bool
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['drift_type'] = self.drift_type.value
        return result


@dataclass
class PerformanceMetrics:
    """Model performance metrics over time."""
    timestamp: str
    model_id: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    samples_evaluated: int
    predictions: Dict[str, int] = field(default_factory=dict)  # direction -> count


class ModelRegistry:
    """
    Model versioning and registry.
    
    Handles:
    - Model registration and versioning
    - Status management (training -> staging -> production)
    - Model retrieval and comparison
    - Automatic cleanup of old versions
    """
    
    def __init__(self, registry_dir: str = MODEL_REGISTRY_DIR):
        self.registry_dir = registry_dir
        self._models: Dict[str, ModelMetadata] = {}
        self._lock = threading.Lock()
        self._load_registry()
    
    def _load_registry(self):
        """Load existing model registry."""
        registry_file = os.path.join(self.registry_dir, 'registry.json')
        if os.path.exists(registry_file):
            try:
                with open(registry_file, 'r') as f:
                    data = json.load(f)
                for model_id, metadata in data.items():
                    self._models[model_id] = ModelMetadata.from_dict(metadata)
                logger.info(f"Loaded {len(self._models)} models from registry")
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")
    
    def _save_registry(self):
        """Save model registry."""
        registry_file = os.path.join(self.registry_dir, 'registry.json')
        with self._lock:
            data = {mid: m.to_dict() for mid, m in self._models.items()}
            with open(registry_file, 'w') as f:
                json.dump(data, f, indent=2)
    
    def register(
        self,
        model_type: str,
        version: str,
        metrics: Dict[str, float],
        hyperparameters: Dict[str, Any],
        feature_names: List[str],
        training_samples: int,
        validation_accuracy: float,
        tags: Optional[List[str]] = None,
        description: str = ""
    ) -> str:
        """
        Register a new model.
        
        Returns:
            model_id: Unique identifier for the model
        """
        # Generate model ID - format: cthulu-[codename]-v[version]
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        hash_input = f"{model_type}_{version}_{timestamp}".encode()
        model_hash = hashlib.md5(hash_input).hexdigest()[:8]
        # Clean model_id: cthulu-type-vX.Y.Z_hash
        model_id = f"{model_type}-{version}_{model_hash}"
        
        # Create metadata
        now = datetime.now(timezone.utc).isoformat()
        metadata = ModelMetadata(
            model_id=model_id,
            model_type=model_type,
            version=version,
            status=ModelStatus.TRAINING,
            created_at=now,
            updated_at=now,
            metrics=metrics,
            hyperparameters=hyperparameters,
            feature_names=feature_names,
            training_samples=training_samples,
            validation_accuracy=validation_accuracy,
            tags=tags or [],
            description=description,
            path=os.path.join(self.registry_dir, f"{model_id}.json")
        )
        
        with self._lock:
            self._models[model_id] = metadata
        
        self._save_registry()
        logger.info(f"Registered model: {model_id} (accuracy={validation_accuracy:.2%})")
        
        return model_id
    
    def update_status(self, model_id: str, status: ModelStatus):
        """Update model status."""
        with self._lock:
            if model_id in self._models:
                self._models[model_id].status = status
                self._models[model_id].updated_at = datetime.now(timezone.utc).isoformat()
        self._save_registry()
        logger.info(f"Model {model_id} status updated to {status.value}")
    
    def get_model(self, model_id: str) -> Optional[ModelMetadata]:
        """Get model metadata."""
        return self._models.get(model_id)
    
    def get_production_model(self, model_type: str) -> Optional[ModelMetadata]:
        """Get the production model for a given type."""
        for model in self._models.values():
            if model.model_type == model_type and model.status == ModelStatus.PRODUCTION:
                return model
        return None
    
    def list_models(self, model_type: Optional[str] = None, status: Optional[ModelStatus] = None) -> List[ModelMetadata]:
        """List models with optional filters."""
        models = list(self._models.values())
        
        if model_type:
            models = [m for m in models if m.model_type == model_type]
        if status:
            models = [m for m in models if m.status == status]
        
        return sorted(models, key=lambda m: m.created_at, reverse=True)
    
    def promote_to_production(self, model_id: str) -> bool:
        """Promote a model to production, demoting current production model."""
        model = self.get_model(model_id)
        if not model:
            logger.error(f"Model {model_id} not found")
            return False
        
        # Demote current production model
        current_prod = self.get_production_model(model.model_type)
        if current_prod:
            self.update_status(current_prod.model_id, ModelStatus.DEPRECATED)
        
        # Promote new model
        self.update_status(model_id, ModelStatus.PRODUCTION)
        logger.info(f"Promoted {model_id} to production")
        return True
    
    def cleanup_old_models(self, keep_count: int = 5):
        """Remove old deprecated models, keeping the most recent ones."""
        for model_type in set(m.model_type for m in self._models.values()):
            deprecated = [m for m in self._models.values() 
                         if m.model_type == model_type and m.status == ModelStatus.DEPRECATED]
            deprecated = sorted(deprecated, key=lambda m: m.created_at, reverse=True)
            
            for model in deprecated[keep_count:]:
                # Remove model file
                if os.path.exists(model.path):
                    os.remove(model.path)
                del self._models[model.model_id]
                logger.info(f"Cleaned up old model: {model.model_id}")
        
        self._save_registry()


class DriftDetector:
    """
    Data and model drift detection.
    
    Detects:
    - Feature drift (distribution changes in input features)
    - Prediction drift (distribution changes in predictions)
    - Performance drift (degradation in model performance)
    - Concept drift (relationship between features and target changes)
    """
    
    def __init__(
        self,
        feature_drift_threshold: float = 0.3,
        prediction_drift_threshold: float = 0.2,
        performance_drift_threshold: float = 0.1,
        window_size: int = 1000
    ):
        self.feature_drift_threshold = feature_drift_threshold
        self.prediction_drift_threshold = prediction_drift_threshold
        self.performance_drift_threshold = performance_drift_threshold
        self.window_size = window_size
        
        # Baseline statistics
        self._baseline_feature_stats: Optional[Dict[str, Tuple[float, float]]] = None  # mean, std
        self._baseline_prediction_dist: Optional[Dict[str, float]] = None
        self._baseline_accuracy: Optional[float] = None
        
        # Running windows
        self._recent_features: deque = deque(maxlen=window_size)
        self._recent_predictions: deque = deque(maxlen=window_size)
        self._recent_accuracies: deque = deque(maxlen=100)
        
        self._lock = threading.Lock()
    
    def set_baseline(
        self,
        feature_stats: Dict[str, Tuple[float, float]],
        prediction_dist: Dict[str, float],
        accuracy: float
    ):
        """Set baseline statistics for drift detection."""
        with self._lock:
            self._baseline_feature_stats = feature_stats
            self._baseline_prediction_dist = prediction_dist
            self._baseline_accuracy = accuracy
        logger.info(f"Drift baseline set: accuracy={accuracy:.2%}")
    
    def record_observation(
        self,
        features: np.ndarray,
        prediction: str,
        actual: Optional[str] = None
    ):
        """Record an observation for drift monitoring."""
        with self._lock:
            self._recent_features.append(features)
            self._recent_predictions.append(prediction)
            
            if actual is not None:
                correct = 1 if prediction == actual else 0
                self._recent_accuracies.append(correct)
    
    def detect_drift(self, model_id: str) -> DriftReport:
        """
        Run drift detection.
        
        Returns:
            DriftReport with detection results
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        if not self._baseline_feature_stats:
            return DriftReport(
                timestamp=timestamp,
                model_id=model_id,
                drift_type=DriftType.NONE,
                drift_score=0.0,
                threshold=0.0,
                triggered=False,
                details={"error": "No baseline set"}
            )
        
        drift_scores = {}
        
        # Feature drift (PSI - Population Stability Index approximation)
        if len(self._recent_features) >= 100:
            feature_drift = self._calculate_feature_drift()
            drift_scores['feature'] = feature_drift
        
        # Prediction drift
        if len(self._recent_predictions) >= 100:
            pred_drift = self._calculate_prediction_drift()
            drift_scores['prediction'] = pred_drift
        
        # Performance drift
        if len(self._recent_accuracies) >= 50 and self._baseline_accuracy:
            perf_drift = self._calculate_performance_drift()
            drift_scores['performance'] = perf_drift
        
        # Determine overall drift
        max_drift_type = DriftType.NONE
        max_drift_score = 0.0
        threshold = 0.0
        
        if 'feature' in drift_scores and drift_scores['feature'] > self.feature_drift_threshold:
            max_drift_type = DriftType.FEATURE_DRIFT
            max_drift_score = drift_scores['feature']
            threshold = self.feature_drift_threshold
        
        if 'prediction' in drift_scores and drift_scores['prediction'] > self.prediction_drift_threshold:
            if drift_scores['prediction'] > max_drift_score:
                max_drift_type = DriftType.PREDICTION_DRIFT
                max_drift_score = drift_scores['prediction']
                threshold = self.prediction_drift_threshold
        
        if 'performance' in drift_scores and drift_scores['performance'] > self.performance_drift_threshold:
            if drift_scores['performance'] > max_drift_score:
                max_drift_type = DriftType.PERFORMANCE_DRIFT
                max_drift_score = drift_scores['performance']
                threshold = self.performance_drift_threshold
        
        triggered = max_drift_type != DriftType.NONE
        
        report = DriftReport(
            timestamp=timestamp,
            model_id=model_id,
            drift_type=max_drift_type,
            drift_score=max_drift_score,
            threshold=threshold,
            triggered=triggered,
            details=drift_scores
        )
        
        if triggered:
            logger.warning(f"Drift detected for {model_id}: {max_drift_type.value} (score={max_drift_score:.3f})")
        
        return report
    
    def _calculate_feature_drift(self) -> float:
        """Calculate feature drift using simplified PSI."""
        features_array = np.array(list(self._recent_features))
        current_means = np.mean(features_array, axis=0)
        current_stds = np.std(features_array, axis=0)
        
        # Compare to baseline
        drift_scores = []
        for i, (name, (baseline_mean, baseline_std)) in enumerate(self._baseline_feature_stats.items()):
            if i < len(current_means):
                # Normalized difference
                mean_diff = abs(current_means[i] - baseline_mean) / (baseline_std + 1e-10)
                std_diff = abs(current_stds[i] - baseline_std) / (baseline_std + 1e-10)
                drift_scores.append((mean_diff + std_diff) / 2)
        
        return float(np.mean(drift_scores)) if drift_scores else 0.0
    
    def _calculate_prediction_drift(self) -> float:
        """Calculate prediction distribution drift."""
        predictions = list(self._recent_predictions)
        current_dist = {}
        for pred in predictions:
            current_dist[pred] = current_dist.get(pred, 0) + 1
        
        total = len(predictions)
        for pred in current_dist:
            current_dist[pred] /= total
        
        # Compare to baseline
        drift = 0.0
        all_preds = set(current_dist.keys()) | set(self._baseline_prediction_dist.keys())
        
        for pred in all_preds:
            baseline_prob = self._baseline_prediction_dist.get(pred, 0.01)
            current_prob = current_dist.get(pred, 0.01)
            drift += abs(current_prob - baseline_prob)
        
        return drift / 2  # Normalize to [0, 1]
    
    def _calculate_performance_drift(self) -> float:
        """Calculate performance degradation."""
        current_accuracy = np.mean(list(self._recent_accuracies))
        accuracy_drop = self._baseline_accuracy - current_accuracy
        return max(0.0, accuracy_drop)


class RetrainingTrigger:
    """
    Automated retraining trigger.
    
    Triggers retraining based on:
    - Drift detection alerts
    - Performance degradation
    - Time-based schedule
    - Manual trigger
    """
    
    def __init__(
        self,
        drift_detector: DriftDetector,
        model_registry: ModelRegistry,
        min_retrain_interval_hours: int = 24,
        performance_threshold: float = 0.5
    ):
        self.drift_detector = drift_detector
        self.model_registry = model_registry
        self.min_retrain_interval_hours = min_retrain_interval_hours
        self.performance_threshold = performance_threshold
        
        self._last_retrain: Dict[str, datetime] = {}
        self._retrain_callbacks: List[callable] = []
        self._lock = threading.Lock()
    
    def register_callback(self, callback: callable):
        """Register a callback to be called when retraining is triggered."""
        self._retrain_callbacks.append(callback)
    
    def check_retrain_needed(self, model_id: str) -> Tuple[bool, str]:
        """
        Check if retraining is needed.
        
        Returns:
            (should_retrain, reason)
        """
        # Check minimum interval
        with self._lock:
            last_retrain = self._last_retrain.get(model_id)
            if last_retrain:
                hours_since = (datetime.now(timezone.utc) - last_retrain).total_seconds() / 3600
                if hours_since < self.min_retrain_interval_hours:
                    return False, f"Recent retrain ({hours_since:.1f}h ago)"
        
        # Check drift
        drift_report = self.drift_detector.detect_drift(model_id)
        if drift_report.triggered:
            return True, f"Drift detected: {drift_report.drift_type.value}"
        
        # Check performance
        model = self.model_registry.get_model(model_id)
        if model and model.validation_accuracy < self.performance_threshold:
            return True, f"Performance below threshold: {model.validation_accuracy:.2%}"
        
        return False, "No retrain needed"
    
    def trigger_retrain(self, model_id: str, reason: str):
        """Trigger retraining for a model."""
        logger.info(f"Triggering retrain for {model_id}: {reason}")
        
        with self._lock:
            self._last_retrain[model_id] = datetime.now(timezone.utc)
        
        # Call registered callbacks
        for callback in self._retrain_callbacks:
            try:
                callback(model_id, reason)
            except Exception as e:
                logger.error(f"Retrain callback error: {e}")


# Singleton instances
_model_registry: Optional[ModelRegistry] = None
_drift_detector: Optional[DriftDetector] = None


def get_model_registry() -> ModelRegistry:
    """Get singleton model registry."""
    global _model_registry
    if _model_registry is None:
        _model_registry = ModelRegistry()
    return _model_registry


def get_drift_detector() -> DriftDetector:
    """Get singleton drift detector."""
    global _drift_detector
    if _drift_detector is None:
        _drift_detector = DriftDetector()
    return _drift_detector
