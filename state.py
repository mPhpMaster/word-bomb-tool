# state.py - Application state management

import json
import threading
import logging
from datetime import datetime
from typing import List, Optional, Dict, Set
from dataclasses import dataclass, field
from config import CONFIG_FILE, METRICS_FILE

logger = logging.getLogger(__name__)

@dataclass
class TypingRecord:
    """Record of typed word with timestamp."""
    word: str
    timestamp: datetime
    search_term: str

@dataclass
class AppMetrics:
    """Application telemetry and metrics."""
    total_ocr_attempts: int = 0
    successful_ocr_count: int = 0
    failed_ocr_count: int = 0
    api_requests: int = 0
    successful_api_calls: int = 0
    failed_api_calls: int = 0
    average_ocr_time_ms: float = 0.0
    average_api_time_ms: float = 0.0
    session_start_time: datetime = field(default_factory=datetime.now)

@dataclass
class AppState:
    """Central application state."""
    region: Optional[Dict] = None
    suggestions: List[str] = field(default_factory=list)
    last_ocr_text: Optional[str] = None
    auto_mode_active: bool = False
    current_mode_index: int = 2
    current_sort_mode_index: int = 2
    suggestion_index: int = 0
    typed_words_history: Set[str] = field(default_factory=set)
    typing_records: List[TypingRecord] = field(default_factory=list)
    total_typed_count: int = 0
    api_status: str = "[OK] Online"
    metrics: AppMetrics = field(default_factory=AppMetrics)

class StateManager:
    """Thread-safe state management."""
    
    def __init__(self):
        self.state = AppState()
        self._lock = threading.RLock()
    
    def get_state(self) -> AppState:
        """Get copy of current state."""
        with self._lock:
            return self.state
    
    def update_state(self, **kwargs):
        """Update state attributes safely."""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.state, key):
                    setattr(self.state, key, value)
                else:
                    logger.warning(f"Unknown state attribute: {key}")
    
    def add_typing_record(self, word: str, search_term: str):
        """Add a typing record."""
        with self._lock:
            record = TypingRecord(
                word=word,
                timestamp=datetime.now(),
                search_term=search_term
            )
            self.state.typing_records.append(record)
    
    def undo_last_word(self) -> Optional[str]:
        """Undo last typed word and return it."""
        with self._lock:
            if not self.state.typing_records:
                return None
            
            record = self.state.typing_records.pop()
            self.state.typed_words_history.discard(record.word)
            self.state.total_typed_count = max(0, self.state.total_typed_count - 1)
            return record.word
    
    def record_ocr_attempt(self, success: bool, duration_ms: float):
        """Record WBT attempt metrics."""
        with self._lock:
            self.state.metrics.total_ocr_attempts += 1
            if success:
                self.state.metrics.successful_ocr_count += 1
            else:
                self.state.metrics.failed_ocr_count += 1
            
            # Update average
            if self.state.metrics.total_ocr_attempts > 0:
                total = self.state.metrics.average_ocr_time_ms * (self.state.metrics.total_ocr_attempts - 1)
                self.state.metrics.average_ocr_time_ms = (total + duration_ms) / self.state.metrics.total_ocr_attempts
    
    def record_api_call(self, success: bool, duration_ms: float):
        """Record API call metrics."""
        with self._lock:
            self.state.metrics.api_requests += 1
            if success:
                self.state.metrics.successful_api_calls += 1
            else:
                self.state.metrics.failed_api_calls += 1
            
            # Update average
            if self.state.metrics.api_requests > 0:
                total = self.state.metrics.average_api_time_ms * (self.state.metrics.api_requests - 1)
                self.state.metrics.average_api_time_ms = (total + duration_ms) / self.state.metrics.api_requests
    
    def save_state(self):
        """Save state to config file."""
        try:
            with self._lock:
                config = {
                    "region": self.state.region,
                    "current_mode_index": self.state.current_mode_index,
                    "current_sort_mode_index": self.state.current_sort_mode_index,
                    "total_typed_count": self.state.total_typed_count,
                }
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info("Configuration saved")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def load_state(self):
        """Load state from config file."""
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            
            with self._lock:
                self.state.region = config.get("region")
                self.state.current_mode_index = config.get("current_mode_index", 2)
                self.state.current_sort_mode_index = config.get("current_sort_mode_index", 2)
                self.state.total_typed_count = config.get("total_typed_count", 0)
            
            logger.info("Configuration loaded from file")
        except FileNotFoundError:
            logger.info("No config file found, using defaults")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    
    def save_metrics(self):
        """Save metrics to file."""
        try:
            with self._lock:
                metrics_dict = {
                    "total_ocr_attempts": self.state.metrics.total_ocr_attempts,
                    "successful_ocr_count": self.state.metrics.successful_ocr_count,
                    "failed_ocr_count": self.state.metrics.failed_ocr_count,
                    "api_requests": self.state.metrics.api_requests,
                    "successful_api_calls": self.state.metrics.successful_api_calls,
                    "failed_api_calls": self.state.metrics.failed_api_calls,
                    "average_ocr_time_ms": self.state.metrics.average_ocr_time_ms,
                    "average_api_time_ms": self.state.metrics.average_api_time_ms,
                    "session_start_time": self.state.metrics.session_start_time.isoformat(),
                }
            with open(METRICS_FILE, 'w') as f:
                json.dump(metrics_dict, f, indent=2)
            logger.info("Metrics saved")
        except Exception as e:
            logger.error(f"Error saving metrics: {e}")