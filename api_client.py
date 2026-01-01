# api_client.py - Datamuse API client

import requests
import logging
import time
from typing import List
from config import DATAMUSE_API, OCR_TIMEOUT, MAX_SUGGESTIONS_DISPLAY, STATUS_ONLINE, STATUS_OFFLINE, STATUS_TIMEOUT, STATUS_ERROR

logger = logging.getLogger(__name__)

class DatamuseClient:
    """Client for Datamuse API with error handling."""
    
    def __init__(self):
        self.session = requests.Session()
        self.status = STATUS_ONLINE
    
    def get_suggestions(self, letters: str, mode: str) -> List[str]:
        """
        Fetch word suggestions from Datamuse API.
        
        Args:
            letters: Search term
            mode: Search mode (Starts With, Ends With, Contains, Rhymes, Related Words)
        
        Returns:
            List of suggestions or empty list if failed
        """
        if not letters or len(letters) < 1:
            return []
        
        start_time = time.time()
        
        try:
            params = {"max": MAX_SUGGESTIONS_DISPLAY}
            
            if mode == "Starts With":
                params["sp"] = letters + "*"
            elif mode == "Ends With":
                params["sp"] = "*" + letters
            elif mode == "Contains":
                params["sp"] = "*" + letters + "*"
            elif mode == "Rhymes":
                params["rel_rhy"] = letters
            elif mode == "Related Words":
                params["rel_jja"] = letters
            
            logger.info(f"API request for {mode}: '{letters}'")
            
            response = self.session.get(DATAMUSE_API, params=params, timeout=OCR_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            suggestions = [item["word"] for item in data if len(item["word"].split()) == 1]
            suggestions = suggestions[:MAX_SUGGESTIONS_DISPLAY]
            
            self.status = STATUS_ONLINE
            duration = (time.time() - start_time) * 1000
            logger.info(f"API call successful in {duration:.2f}ms, found {len(suggestions)} suggestions")
            
            return suggestions
        
        except requests.exceptions.Timeout:
            self.status = STATUS_TIMEOUT
            logger.error("API request timeout")
            return []
        except requests.exceptions.ConnectionError:
            self.status = STATUS_OFFLINE
            logger.error("API connection failed")
            return []
        except Exception as e:
            self.status = STATUS_ERROR
            logger.error(f"API error: {e}", exc_info=True)
            return []
    
    def close(self):
        """Close session."""
        self.session.close()