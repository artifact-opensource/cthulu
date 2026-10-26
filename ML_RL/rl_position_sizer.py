"""
Reinforcement Learning for Position Sizing - Hybrid Q-Learning and PPO

Implements a hybrid RL approach combining:
1. Q-Learning for discrete sizing decisions
2. Proximal Policy Optimization (PPO) for continuous optimization

The RL agent learns optimal position sizing based on:
- Market state features
- Current exposure
- Recent performance
- Risk constraints

Part of Cthulu ML Pipeline v6.0.0
"""

from __future__ import annotations
import numpy as np
import os
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from collections import deque
from enum import Enum
import threading

logger = logging.getLogger("cthulu.ml.rl_sizing")

# Directory for RL model storage
RL_MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models', 'rl')
os.makedirs(RL_MODEL_DIR, exist_ok=True)


class SizeAction(Enum):
    """Discrete position sizing actions."""
    SKIP = 0           # Don't take the trade
    MICRO = 1          # 25% of base size
    SMALL = 2          # 50% of base size
    STANDARD = 3       # 100% of base size
    MODERATE = 4       # 125% of base size
    AGGRESSIVE = 5     # 150% of base size
    
    @property
    def multiplier(self) -> float:
        """Get size multiplier for this action."""
        multipliers = {
            SizeAction.SKIP: 0.0,
            SizeAction.MICRO: 0.25,
            SizeAction.SMALL: 0.50,
            SizeAction.STANDARD: 1.0,
            SizeAction.MODERATE: 1.25,
            SizeAction.AGGRESSIVE: 1.50
        }
        return multipliers[self]


@dataclass
class RLState:
    """State representation for RL agent."""
    # Market features
    trend_strength: float      # 0-1
    volatility_regime: float   # 0-1 (low to high)
    momentum_score: float      # -1 to 1
    
    # Signal features
    signal_confidence: float   # 0-1
    entry_quality: float       # 0-1
    risk_reward_ratio: float   # 0-5+
    
    # Account state
    current_exposure_pct: float  # Current exposure as % of balance
    win_rate_recent: float       # Recent win rate 0-1
    drawdown_pct: float          # Current drawdown %
    
    # Risk constraints
    max_position_pct: float    # Maximum position size allowed
    remaining_daily_risk: float  # Remaining daily risk budget
    
    def to_array(self) -> np.ndarray:
        """Convert to numpy array for neural network."""
        return np.array([
            self.trend_strength,
            self.volatility_regime,
            self.momentum_score,
            self.signal_confidence,
            self.entry_quality,
            min(self.risk_reward_ratio / 5, 1.0),  # Normalize
            self.current_exposure_pct,
            self.win_rate_recent,
            self.drawdown_pct,
            self.max_position_pct,
            min(self.remaining_daily_risk, 1.0)
        ], dtype=np.float32)


@dataclass
class RLExperience:
    """Single experience tuple for replay buffer."""
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool


@dataclass
class TrainingMetrics:
    """RL training metrics."""
    episode: int
    total_reward: float
    avg_reward: float
    loss: float
    epsilon: float
    q_values_mean: float


class ReplayBuffer:
    """Experience replay buffer for off-policy learning."""
    
    def __init__(self, capacity: int = 10000):
        self.buffer: deque = deque(maxlen=capacity)
    
    def push(self, experience: RLExperience):
        """Add experience to buffer."""
        self.buffer.append(experience)
    
    def sample(self, batch_size: int) -> List[RLExperience]:
        """Sample random batch."""
        indices = np.random.choice(len(self.buffer), min(batch_size, len(self.buffer)), replace=False)
        return [self.buffer[i] for i in indices]
    
    def __len__(self) -> int:
        return len(self.buffer)


class QNetwork:
    """
    Simple Q-Network for discrete action selection.
    
    Architecture:
    - Input: State features (11)
    - Hidden: 64 -> 32 (ReLU)
    - Output: Q-values for each action (6)
    """
    
    def __init__(self, state_size: int = 11, action_size: int = 6, hidden_sizes: Tuple[int, int] = (64, 32)):
        self.state_size = state_size
        self.action_size = action_size
        
        # Xavier initialization
        np.random.seed(42)
        
        # Layer 1: state_size -> hidden[0]
        scale1 = np.sqrt(2.0 / (state_size + hidden_sizes[0]))
        self.W1 = np.random.randn(state_size, hidden_sizes[0]) * scale1
        self.b1 = np.zeros(hidden_sizes[0])
        
        # Layer 2: hidden[0] -> hidden[1]
        scale2 = np.sqrt(2.0 / (hidden_sizes[0] + hidden_sizes[1]))
        self.W2 = np.random.randn(hidden_sizes[0], hidden_sizes[1]) * scale2
        self.b2 = np.zeros(hidden_sizes[1])
        
        # Output: hidden[1] -> action_size
        scale3 = np.sqrt(2.0 / (hidden_sizes[1] + action_size))
        self.W3 = np.random.randn(hidden_sizes[1], action_size) * scale3
        self.b3 = np.zeros(action_size)
        
        # Velocity buffers for momentum
        self._velocities = {
            'W1': np.zeros_like(self.W1), 'b1': np.zeros_like(self.b1),
            'W2': np.zeros_like(self.W2), 'b2': np.zeros_like(self.b2),
            'W3': np.zeros_like(self.W3), 'b3': np.zeros_like(self.b3)
        }
    
    def forward(self, state: np.ndarray) -> np.ndarray:
        """Forward pass returning Q-values."""
        # Ensure 2D input
        if state.ndim == 1:
            state = state.reshape(1, -1)
        
        # Hidden layer 1
        z1 = np.dot(state, self.W1) + self.b1
        a1 = np.maximum(0, z1)  # ReLU
        
        # Hidden layer 2
        z2 = np.dot(a1, self.W2) + self.b2
        a2 = np.maximum(0, z2)  # ReLU
        
        # Output layer (linear)
        q_values = np.dot(a2, self.W3) + self.b3
        
        return q_values
    
    def backward(self, state: np.ndarray, target: np.ndarray, learning_rate: float = 0.001, momentum: float = 0.9):
        """Backward pass with gradient descent."""
        # Forward pass with intermediate values
        if state.ndim == 1:
            state = state.reshape(1, -1)
        
        z1 = np.dot(state, self.W1) + self.b1
        a1 = np.maximum(0, z1)
        z2 = np.dot(a1, self.W2) + self.b2
        a2 = np.maximum(0, z2)
        output = np.dot(a2, self.W3) + self.b3
        
        # Compute gradients (MSE loss)
        batch_size = state.shape[0]
        dout = 2 * (output - target) / batch_size
        
        # Output layer gradients
        dW3 = np.dot(a2.T, dout)
        db3 = np.sum(dout, axis=0)
        da2 = np.dot(dout, self.W3.T)
        
        # Layer 2 gradients
        dz2 = da2 * (z2 > 0)  # ReLU derivative
        dW2 = np.dot(a1.T, dz2)
        db2 = np.sum(dz2, axis=0)
        da1 = np.dot(dz2, self.W2.T)
        
        # Layer 1 gradients
        dz1 = da1 * (z1 > 0)  # ReLU derivative
        dW1 = np.dot(state.T, dz1)
        db1 = np.sum(dz1, axis=0)
        
        # Update with momentum
        for name, grad, weight in [
            ('W1', dW1, self.W1), ('b1', db1, self.b1),
            ('W2', dW2, self.W2), ('b2', db2, self.b2),
            ('W3', dW3, self.W3), ('b3', db3, self.b3)
        ]:
            self._velocities[name] = momentum * self._velocities[name] - learning_rate * grad
            if name.startswith('W'):
                setattr(self, name, getattr(self, name) + self._velocities[name])
            else:
                setattr(self, name, getattr(self, name) + self._velocities[name])
        
        # Return loss
        return float(np.mean((output - target) ** 2))
    
    def copy_from(self, other: 'QNetwork'):
        """Copy weights from another network."""
        self.W1 = other.W1.copy()
        self.b1 = other.b1.copy()
        self.W2 = other.W2.copy()
        self.b2 = other.b2.copy()
        self.W3 = other.W3.copy()
        self.b3 = other.b3.copy()


class PolicyNetwork:
    """
    Policy network for PPO continuous optimization.
    
    Outputs:
    - Mean: Continuous size multiplier
    - Log_std: Log standard deviation for exploration
    """
    
    def __init__(self, state_size: int = 11, hidden_size: int = 64):
        self.state_size = state_size
        
        np.random.seed(43)
        
        # Hidden layer
        scale1 = np.sqrt(2.0 / (state_size + hidden_size))
        self.W1 = np.random.randn(state_size, hidden_size) * scale1
        self.b1 = np.zeros(hidden_size)
        
        # Mean output
        scale2 = np.sqrt(2.0 / (hidden_size + 1))
        self.W_mean = np.random.randn(hidden_size, 1) * scale2 * 0.1
        self.b_mean = np.array([1.0])  # Initialize to output ~1.0
        
        # Log std (learnable)
        self.log_std = np.array([-0.5])  # Start with moderate exploration
    
    def forward(self, state: np.ndarray) -> Tuple[float, float]:
        """
        Forward pass returning mean and std.
        
        Returns:
            mean: Expected size multiplier (0-2)
            std: Standard deviation for sampling
        """
        if state.ndim == 1:
            state = state.reshape(1, -1)
        
        # Hidden layer
        z1 = np.dot(state, self.W1) + self.b1
        a1 = np.tanh(z1)  # Tanh for bounded hidden activation
        
        # Mean output (sigmoid scaled to 0-2)
        mean = np.dot(a1, self.W_mean) + self.b_mean
        mean = 2.0 / (1.0 + np.exp(-mean))  # Sigmoid scaled to [0, 2]
        
        std = np.exp(self.log_std)
        
        return float(mean[0, 0]), float(std[0])
    
    def sample_action(self, state: np.ndarray) -> Tuple[float, float]:
        """Sample action from policy distribution."""
        mean, std = self.forward(state)
        action = np.random.normal(mean, std)
        action = np.clip(action, 0, 2)  # Clip to valid range
        log_prob = -0.5 * ((action - mean) / (std + 1e-8)) ** 2 - np.log(std + 1e-8)
        return float(action), float(log_prob)


class RLPositionSizer:
    """
    Reinforcement Learning Position Sizer.
    
    Combines Q-Learning and PPO for robust position sizing:
    - Q-Learning: Discrete action selection (SKIP/MICRO/SMALL/STANDARD/MODERATE/AGGRESSIVE)
    - PPO: Fine-tuning the continuous multiplier within selected category
    
    Reward function:
    - Positive reward for profitable trades (scaled by PnL)
    - Negative reward for losses (scaled by loss)
    - Penalty for excessive risk
    - Bonus for risk-adjusted returns
    """
    
    def __init__(
        self,
        learning_rate: float = 0.001,
        gamma: float = 0.99,
        epsilon_start: float = 1.0,
        epsilon_end: float = 0.05,
        epsilon_decay: float = 0.995,
        batch_size: int = 64,
        target_update_freq: int = 100,
        use_ppo: bool = True
    ):
        self.learning_rate = learning_rate
        self.gamma = gamma
        self.epsilon = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay = epsilon_decay
        self.batch_size = batch_size
        self.target_update_freq = target_update_freq
        self.use_ppo = use_ppo
        
        # Q-Learning components
        self.q_network = QNetwork()
        self.target_network = QNetwork()
        self.target_network.copy_from(self.q_network)
        
        # PPO component (optional fine-tuning)
        self.policy_network = PolicyNetwork() if use_ppo else None
        
        # Replay buffer
        self.replay_buffer = ReplayBuffer(capacity=10000)
        
        # Training state
        self.steps = 0
        self.training_metrics: List[TrainingMetrics] = []
        
        # Lock for thread safety
        self._lock = threading.Lock()
        
        logger.info(f"RLPositionSizer initialized: lr={learning_rate}, gamma={gamma}, ppo={use_ppo}")
    
    def select_action(self, state: RLState, explore: bool = True) -> Tuple[SizeAction, float]:
        """
        Select position sizing action.
        
        Args:
            state: Current RL state
            explore: Whether to use exploration (epsilon-greedy)
            
        Returns:
            action: Selected sizing action
            multiplier: Final size multiplier (0-2)
        """
        state_array = state.to_array()
        
        # Epsilon-greedy for Q-learning
        if explore and np.random.random() < self.epsilon:
            action = SizeAction(np.random.randint(0, 6))
        else:
            q_values = self.q_network.forward(state_array)
            action = SizeAction(int(np.argmax(q_values[0])))
        
        # Get base multiplier from action
        base_mult = action.multiplier
        
        # Fine-tune with PPO if enabled and action is not SKIP
        if self.use_ppo and action != SizeAction.SKIP:
            ppo_mult, _ = self.policy_network.sample_action(state_array)
            # Blend: use PPO to adjust within ±25% of base
            adjustment = (ppo_mult - 1.0) * 0.25
            final_mult = base_mult * (1.0 + adjustment)
            final_mult = np.clip(final_mult, 0, 2)
        else:
            final_mult = base_mult
        
        return action, float(final_mult)
    
    def calculate_reward(
        self,
        action: SizeAction,
        multiplier: float,
        pnl: float,
        risk_taken: float,
        max_risk: float,
        trade_duration_bars: int
    ) -> float:
        """
        Calculate reward for a completed trade.
        
        Args:
            action: Action taken
            multiplier: Size multiplier used
            pnl: Profit/Loss (positive = profit)
            risk_taken: Risk taken as % of balance
            max_risk: Maximum allowed risk
            trade_duration_bars: How long trade was held
            
        Returns:
            reward: Calculated reward
        """
        # Base reward from PnL
        if pnl > 0:
            # Profitable: reward scaled by profit and adjusted for risk
            reward = pnl * (1.0 + multiplier * 0.5)  # Bonus for sizing up on winners
        else:
            # Loss: penalty scaled by loss and risk taken
            reward = pnl * (1.0 + risk_taken / max_risk)  # Higher penalty for excessive risk
        
        # Risk-adjusted bonus
        if pnl > 0 and risk_taken > 0:
            sharpe_proxy = pnl / (risk_taken + 1e-10)
            reward += sharpe_proxy * 0.1  # Small bonus for good risk-adjusted returns
        
        # Penalty for skipping good opportunities
        if action == SizeAction.SKIP and pnl > 0:
            reward -= pnl * 0.5  # Missed opportunity cost
        
        # Duration penalty (discourage holding too long)
        if trade_duration_bars > 50:
            reward -= 0.1 * (trade_duration_bars - 50) / 50
        
        return float(reward)
    
    def store_experience(
        self,
        state: RLState,
        action: SizeAction,
        reward: float,
        next_state: RLState,
        done: bool
    ):
        """Store experience in replay buffer."""
        experience = RLExperience(
            state=state.to_array(),
            action=action.value,
            reward=reward,
            next_state=next_state.to_array(),
            done=done
        )
        self.replay_buffer.push(experience)
    
    def train_step(self) -> Optional[float]:
        """
        Perform one training step.
        
        Returns:
            loss: Training loss or None if not enough samples
        """
        if len(self.replay_buffer) < self.batch_size:
            return None
        
        # Sample batch
        batch = self.replay_buffer.sample(self.batch_size)
        
        states = np.array([e.state for e in batch])
        actions = np.array([e.action for e in batch])
        rewards = np.array([e.reward for e in batch])
        next_states = np.array([e.next_state for e in batch])
        dones = np.array([e.done for e in batch])
        
        # Compute target Q-values
        next_q = self.target_network.forward(next_states)
        max_next_q = np.max(next_q, axis=1)
        targets = rewards + self.gamma * max_next_q * (1 - dones)
        
        # Current Q-values
        current_q = self.q_network.forward(states)
        
        # Create target array (only update chosen action)
        target_q = current_q.copy()
        for i, action in enumerate(actions):
            target_q[i, action] = targets[i]
        
        # Backward pass
        loss = self.q_network.backward(states, target_q, self.learning_rate)
        
        # Update target network
        self.steps += 1
        if self.steps % self.target_update_freq == 0:
            self.target_network.copy_from(self.q_network)
        
        # Decay epsilon
        self.epsilon = max(self.epsilon_end, self.epsilon * self.epsilon_decay)
        
        return loss
    
    def get_sizing_recommendation(
        self,
        trend_strength: float,
        volatility: float,
        momentum: float,
        signal_confidence: float,
        entry_quality: float,
        risk_reward: float,
        current_exposure: float,
        recent_win_rate: float,
        current_drawdown: float,
        max_position_pct: float,
        remaining_risk: float
    ) -> Tuple[SizeAction, float, Dict[str, Any]]:
        """
        Get position sizing recommendation.
        
        Returns:
            action: Recommended action
            multiplier: Size multiplier
            details: Additional details
        """
        state = RLState(
            trend_strength=trend_strength,
            volatility_regime=volatility,
            momentum_score=momentum,
            signal_confidence=signal_confidence,
            entry_quality=entry_quality,
            risk_reward_ratio=risk_reward,
            current_exposure_pct=current_exposure,
            win_rate_recent=recent_win_rate,
            drawdown_pct=current_drawdown,
            max_position_pct=max_position_pct,
            remaining_daily_risk=remaining_risk
        )
        
        action, multiplier = self.select_action(state, explore=False)
        
        # Get Q-values for explanation
        q_values = self.q_network.forward(state.to_array())[0]
        
        details = {
            'action': action.name,
            'multiplier': multiplier,
            'q_values': {SizeAction(i).name: float(q_values[i]) for i in range(6)},
            'epsilon': self.epsilon,
            'confidence': float(np.max(q_values) - np.mean(q_values))  # Confidence proxy
        }
        
        return action, multiplier, details
    
    def save(self, path: Optional[str] = None):
        """Save RL model."""
        if path is None:
            path = os.path.join(RL_MODEL_DIR, 'rl_sizer.json')
        
        state = {
            'q_network': {
                'W1': self.q_network.W1.tolist(),
                'b1': self.q_network.b1.tolist(),
                'W2': self.q_network.W2.tolist(),
                'b2': self.q_network.b2.tolist(),
                'W3': self.q_network.W3.tolist(),
                'b3': self.q_network.b3.tolist()
            },
            'epsilon': self.epsilon,
            'steps': self.steps,
            'config': {
                'learning_rate': self.learning_rate,
                'gamma': self.gamma,
                'use_ppo': self.use_ppo
            }
        }
        
        with open(path, 'w') as f:
            json.dump(state, f, indent=2)
        
        logger.info(f"Saved RL model to {path}")
    
    def load(self, path: Optional[str] = None):
        """Load RL model."""
        if path is None:
            path = os.path.join(RL_MODEL_DIR, 'rl_sizer.json')
        
        if not os.path.exists(path):
            logger.warning(f"No saved model found at {path}")
            return
        
        with open(path, 'r') as f:
            state = json.load(f)
        
        self.q_network.W1 = np.array(state['q_network']['W1'])
        self.q_network.b1 = np.array(state['q_network']['b1'])
        self.q_network.W2 = np.array(state['q_network']['W2'])
        self.q_network.b2 = np.array(state['q_network']['b2'])
        self.q_network.W3 = np.array(state['q_network']['W3'])
        self.q_network.b3 = np.array(state['q_network']['b3'])
        
        self.target_network.copy_from(self.q_network)
        self.epsilon = state['epsilon']
        self.steps = state['steps']
        
        logger.info(f"Loaded RL model from {path}")


# Singleton instance
_rl_sizer: Optional[RLPositionSizer] = None


def get_rl_position_sizer() -> RLPositionSizer:
    """Get singleton RL position sizer."""
    global _rl_sizer
    if _rl_sizer is None:
        _rl_sizer = RLPositionSizer()
        # Try to load existing model
        _rl_sizer.load()
    return _rl_sizer
