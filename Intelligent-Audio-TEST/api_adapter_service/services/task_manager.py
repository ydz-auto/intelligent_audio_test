# -*- coding: utf-8 -*-
"""Task manager with round-level result support for dialog mode.

Extends the traditional frame-level result management with
round-level results for voice_llm dialog tasks.
"""

import time
import threading
from collections import defaultdict
from typing import Optional

from api_adapter_service.utils.logger import logger


class TaskManager:
    """
    Manages task lifecycle and results for both streaming and dialog modes.

    - Streaming tasks: frame_results + final_results (existing)
    - Dialog tasks: round_results (new)
    """

    def __init__(self):
        self.tasks: dict = {}
        self.frame_results: dict = defaultdict(list)
        self.round_results: dict = defaultdict(list)
        self.final_results: dict = {}
        self._lock = threading.Lock()

    # ── Task lifecycle ──────────────────────────────────────────

    def create_task(self, task_id: str, **kwargs) -> dict:
        """Register a new task."""
        with self._lock:
            self.tasks[task_id] = {
                'task_id': task_id,
                'status': 'pending',
                'created_at': time.time(),
                'error_message': None,
                **kwargs,
            }
        return self.tasks[task_id]

    def update_task_status(self, task_id: str, status: str, error_message: str = None):
        """Update task status."""
        with self._lock:
            task = self.tasks.get(task_id)
            if task:
                task['status'] = status
                if error_message:
                    task['error_message'] = error_message

    def get_task(self, task_id: str) -> Optional[dict]:
        """Get task info."""
        return self.tasks.get(task_id)

    # ── Round results (dialog mode) ─────────────────────────────

    def add_round_result(self, task_id: str, round_idx: int, result: dict):
        """
        Add a round result for a dialog task.

        Args:
            task_id: Task ID
            round_idx: Round number
            result: {asr_text, trans_text, latency, raw_response, ...}
        """
        with self._lock:
            self.round_results[task_id].append({
                'round': round_idx,
                'result': result,
                'timestamp': time.time(),
            })

    def get_round_results(self, task_id: str) -> list:
        """Get all round results for a task."""
        return self.round_results.get(task_id, [])

    def get_round_result(self, task_id: str, round_idx: int) -> Optional[dict]:
        """Get a specific round result."""
        results = self.round_results.get(task_id, [])
        for r in results:
            if r['round'] == round_idx:
                return r
        return None

    # ── Frame results (streaming mode, existing) ────────────────

    def add_frame_result(self, task_id: str, frame_result: dict):
        """Add a frame result for a streaming task."""
        with self._lock:
            self.frame_results[task_id].append(frame_result)

    def get_frame_results(self, task_id: str) -> list:
        """Get all frame results for a task."""
        return self.frame_results.get(task_id, [])

    # ── Final results ───────────────────────────────────────────

    def set_final_result(self, task_id: str, result: dict):
        """Set the final aggregated result for a task."""
        with self._lock:
            self.final_results[task_id] = result

    def get_final_result(self, task_id: str) -> Optional[dict]:
        """Get final result (dialog or streaming)."""
        task = self.tasks.get(task_id)
        if not task:
            return None

        # Dialog mode: has round results
        if task_id in self.round_results and self.round_results[task_id]:
            rounds = self.round_results[task_id]
            return {
                'task_id': task_id,
                'session_id': task.get('session_id', ''),
                'status': task['status'],
                'result_type': 'dialog',
                'total_rounds': len(rounds),
                'rounds': [
                    {
                        'round': r['round'],
                        'asr_text': r['result'].get('asr_text', ''),
                        'trans_text': r['result'].get('trans_text', ''),
                        'output': r['result'].get('output', ''),
                        'latency': r['result'].get('latency', 0),
                    }
                    for r in sorted(rounds, key=lambda x: x['round'])
                ],
                'total_latency': sum(
                    r['result'].get('latency', 0) for r in rounds
                ),
            }

        # Streaming mode
        if task_id in self.final_results:
            result = self.final_results[task_id]
            result['result_type'] = 'streaming'
            return result

        return None

    # ── Cleanup ─────────────────────────────────────────────────

    def delete_task(self, task_id: str):
        """Delete a task and all its results."""
        with self._lock:
            self.tasks.pop(task_id, None)
            self.frame_results.pop(task_id, None)
            self.round_results.pop(task_id, None)
            self.final_results.pop(task_id, None)

    def cleanup_expired(self, expire_minutes: int = 60):
        """Clean up expired tasks."""
        now = time.time()
        expired_ids = []
        for tid, task in self.tasks.items():
            if now - task.get('created_at', now) > expire_minutes * 60:
                expired_ids.append(tid)
        for tid in expired_ids:
            self.delete_task(tid)
        return len(expired_ids)

    def get_task_count(self) -> int:
        """Get total task count."""
        return len(self.tasks)


# Singleton
task_manager = TaskManager()
