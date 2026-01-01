# suggestion_manager.py - Suggestion handling and sorting

import random
import logging
from typing import List
from config import SORT_MODES

logger = logging.getLogger(__name__)

class SuggestionManager:
    """Manages suggestion list operations."""
    
    @staticmethod
    def sort_suggestions(suggestions: List[str], sort_mode: str) -> List[str]:
        """
        Sort suggestions based on mode.
        
        Args:
            suggestions: List of words to sort
            sort_mode: Sort mode (Shortest, Longest, Random, Frequency)
        
        Returns:
            Sorted list
        """
        if not suggestions:
            return []
        
        if sort_mode == "Shortest":
            return sorted(suggestions, key=len)
        elif sort_mode == "Longest":
            return sorted(suggestions, key=len, reverse=True)
        elif sort_mode == "Frequency":
            # Sort by complexity (longer words, unusual patterns first)
            return sorted(suggestions, key=lambda w: -sum(1 for c in w if c.isupper()))
        elif sort_mode == "Random":
            shuffled = suggestions.copy()
            random.shuffle(shuffled)
            return shuffled
        else:
            return suggestions
    
    @staticmethod
    def get_next_untyped_word(suggestions: List[str], start_index: int, 
                              typed_history: set) -> tuple:
        """
        Find next untyped word in suggestions list.
        
        Args:
            suggestions: List of suggestions
            start_index: Starting index to search from
            typed_history: Set of already-typed words
        
        Returns:
            Tuple of (word, index) or (None, start_index) if all typed
        """
        if not suggestions:
            return None, start_index
        
        for i in range(len(suggestions)):
            current_idx = (start_index + i) % len(suggestions)
            word = suggestions[current_idx]
            
            if ' ' in word:
                continue
            
            if word not in typed_history:
                return word, current_idx + 1
        
        return None, start_index