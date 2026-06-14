"""Telemetry helper for provenance and long-term order auditing.

Provides a small wrapper around `cthulu.persistence.database.Database` to record
order provenance entries and expose simple query helpers.
"""
from typing import Dict, Any, List, Optional
import logging
from cthulu.persistence.database import Database

logger = logging.getLogger('cthulu.telemetry')

class Telemetry:
    def __init__(self, db: Database):
        self.db = db

    def record_provenance(self, provenance: Dict[str, Any]) -> int:
        try:
            row_id = self.db.record_provenance(provenance)
            logger.debug(f"Recorded provenance id={row_id} for client_tag={provenance.get('client_tag')}")
            return row_id
        except Exception:
            logger.exception('Failed to record provenance via Telemetry')
            return -1

    def get_recent_provenance(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            return self.db.get_recent_provenance(limit)
        except Exception:
            logger.exception('Failed to fetch recent provenance')
            return []




