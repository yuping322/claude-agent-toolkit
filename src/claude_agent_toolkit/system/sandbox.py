#!/usr/bin/env python3
# sandbox.py - SandboxManager abstraction

import asyncio
import time
import psutil
import threading
from typing import Dict, Any, Optional
from dataclasses import dataclass

from .observability import event_bus, SandboxExecutionEvent
from .config import SandboxStrategyConfig

@dataclass
class SandboxSession:
    agent_id: str
    strategy: str
    created_ts: float

@dataclass
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    latency_ms: float

class SandboxManager:
    def __init__(self, strategies: Dict[str, SandboxStrategyConfig]):
        self._strategies = strategies

    async def create_session(self, agent_id: str, strategy: str) -> SandboxSession:
        if strategy not in self._strategies:
            raise ValueError(f"Unknown sandbox strategy: {strategy}")
        return SandboxSession(agent_id=agent_id, strategy=strategy, created_ts=time.time())

    async def run(self, session: SandboxSession, command: str) -> SandboxResult:
        strategy_config = self._strategies[session.strategy]
        
        # Get resource limits from config
        cpu_limit_pct = getattr(strategy_config, 'hard_cpu_limit_pct', 90)
        memory_limit_mb = getattr(strategy_config, 'memory_limit_mb', None)
        
        t0 = time.time()
        event_bus.publish(SandboxExecutionEvent(
            event_type="sandbox.exec",
            agent_id=session.agent_id,
            sandbox_strategy=session.strategy,
            phase="start",
            command=command,
            component="sandbox",
            data={
                "cpu_limit_pct": cpu_limit_pct,
                "memory_limit_mb": memory_limit_mb
            }
        ))
        
        # Execute command in subprocess (real implementation)
        try:
            import subprocess
            import psutil
            import threading
            
            # Track resource usage during execution
            max_cpu = 0.0
            max_memory_mb = 0
            
            def monitor_resources(process):
                nonlocal max_cpu, max_memory_mb
                try:
                    ps_process = psutil.Process(process.pid)
                    while process.poll() is None:
                        cpu_percent = ps_process.cpu_percent(interval=0.1)
                        memory_info = ps_process.memory_info()
                        memory_mb = memory_info.rss / 1024 / 1024
                        
                        max_cpu = max(max_cpu, cpu_percent)
                        max_memory_mb = max(max_memory_mb, memory_mb)
                        
                        time.sleep(0.1)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Start subprocess
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Start resource monitoring in background
            monitor_thread = threading.Thread(target=monitor_resources, args=(process,))
            monitor_thread.daemon = True
            monitor_thread.start()
            
            # Wait for completion with timeout
            try:
                stdout, stderr = process.communicate(timeout=30)  # 30 second timeout
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                exit_code = -1
            
            latency_ms = (time.time() - t0) * 1000
            
            # Check resource limits
            resource_exceeded = (max_cpu > cpu_limit_pct) or \
                              (memory_limit_mb and max_memory_mb > memory_limit_mb)
            
            success = (exit_code == 0) and not resource_exceeded
            
            result = SandboxResult(
                success=success, 
                stdout=stdout,
                stderr=stderr if not success else "",
                latency_ms=latency_ms
            )
            
            event_bus.publish(SandboxExecutionEvent(
                event_type="sandbox.exec",
                agent_id=session.agent_id,
                sandbox_strategy=session.strategy,
                phase="finish",
                command=command,
                success=success,
                latency_ms=latency_ms,
                component="sandbox",
                data={
                    "cpu_limit_pct": cpu_limit_pct,
                    "memory_limit_mb": memory_limit_mb,
                    "actual_cpu_used": max_cpu,
                    "actual_memory_mb": max_memory_mb,
                    "resource_exceeded": resource_exceeded,
                    "exit_code": exit_code
                }
            ))
            
            return result
            
        except Exception as e:
            # Fallback for systems without psutil
            latency_ms = (time.time() - t0) * 1000
            result = SandboxResult(
                success=False,
                stdout="",
                stderr=f"Execution failed: {str(e)}",
                latency_ms=latency_ms
            )
            
            event_bus.publish(SandboxExecutionEvent(
                event_type="sandbox.exec",
                agent_id=session.agent_id,
                sandbox_strategy=session.strategy,
                phase="finish",
                command=command,
                success=False,
                latency_ms=latency_ms,
                component="sandbox",
                data={
                    "cpu_limit_pct": cpu_limit_pct,
                    "memory_limit_mb": memory_limit_mb,
                    "error": str(e)
                }
            ))
            
            return result

    async def cleanup(self, session: SandboxSession) -> None:
        # Could emit cleanup event
        pass

__all__ = ["SandboxManager","SandboxSession","SandboxResult"]
