# -*- coding: utf-8 -*-
"""Session state management for voice_llm multi-round dialog.

Manages per-session context history, round results, and metadata.
All operations are thread-safe via threading.Lock.
"""

import time
import threading
from typing import Optional

from api_adapter_service.utils.logger import logger


class SessionStore:
    """
    Multi-round dialog session state store.

    For each session_id manages:
    - context_history (dialog round records)
    - round_results
    - session metadata (created_at, last_active, status)
    """

    def __init__(self):
        self._sessions: dict = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        session_id: str,
        task_id: str,
        context_mode: str = 'full',
        max_history_rounds: int = 10,
        session_timeout: int = 60,
    ) -> dict:
        """Create a new session."""
        with self._lock:
            session = {
                'session_id': session_id,
                'task_id': task_id,
                'context_mode': context_mode,
                'max_history_rounds': max_history_rounds,
                'session_timeout': session_timeout,
                'context_history': [],
                'round_results': [],
                'created_at': time.time(),
                'last_active': time.time(),
                'status': 'active',
            }
            self._sessions[session_id] = session
            logger.info(f'Session created: {session_id} for task {task_id}')
            return session

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session state."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            return dict(session)  # return copy

    def ensure_session(
        self,
        session_id: str,
        task_id: str,
        context_mode: str = 'full',
        max_history_rounds: int = 10,
        session_timeout: int = 60,
    ) -> dict:
        """Get existing session or create if not found."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session['last_active'] = time.time()
                return dict(session)
        # Not found — create outside the read lock
        return self.create_session(
            session_id, task_id, context_mode, max_history_rounds, session_timeout,
        )

    def add_round(
        self,
        session_id: str,
        round_idx: int,
        input_text: str,
        output_text: str,
        latency: float,
    ):
        """Add a dialog round record to the session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                logger.warning(f'Session not found: {session_id}')
                return

            round_data = {
                'round': round_idx,
                'input': input_text,
                'output': output_text,
                'latency': latency,
                'timestamp': time.time(),
            }

            session['round_results'].append(round_data)
            session['context_history'].append({
                'role': 'user',
                'content': input_text,
            })
            session['context_history'].append({
                'role': 'assistant',
                'content': output_text,
            })
            session['last_active'] = time.time()

    def get_context(self, session_id: str) -> list:
        """
        Get current context history for next-round requests.

        Returns different scope based on context_mode:
        - 'full': complete history
        - 'sliding_window': last max_history_rounds rounds
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return []

            history = session['context_history']
            mode = session['context_mode']
            max_rounds = session['max_history_rounds']

            if mode == 'sliding_window':
                # Each round = user + assistant = 2 messages
                max_messages = max_rounds * 2
                return list(history[-max_messages:]) if len(history) > max_messages else list(history)
            else:
                return list(history)

    def get_round_results(self, session_id: str) -> list:
        """Get all round results for a session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return []
            return list(session['round_results'])

    def destroy_session(self, session_id: str):
        """Destroy a session."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]['status'] = 'destroyed'
                del self._sessions[session_id]
                logger.info(f'Session destroyed: {session_id}')

    def cleanup_expired(self):
        """Clean up expired sessions (timeout * 1.5 grace period)."""
        now = time.time()
        with self._lock:
            expired = [
                sid for sid, s in self._sessions.items()
                if now - s['last_active'] > s['session_timeout'] * 1.5
            ]
            for sid in expired:
                del self._sessions[sid]
                logger.info(f'Expired session cleaned: {sid}')
        return len(expired)

    def get_session_count(self) -> int:
        """Get active session count."""
        return len(self._sessions)


# Singleton
session_store = SessionStore()
