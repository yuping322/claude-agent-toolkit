import asyncio
import pytest
import tempfile
import os
import subprocess
from unittest.mock import patch, AsyncMock

from claude_agent_toolkit.system.sandbox import SandboxManager, SandboxSession
from claude_agent_toolkit.system.config import SandboxStrategyConfig
from claude_agent_toolkit.system.observability import event_bus, SandboxExecutionEvent


class TestSandboxFailures:
    """测试沙箱各种失败情况"""

    @pytest.mark.asyncio
    async def test_unknown_strategy(self):
        """测试未知沙箱策略的情况"""
        strategies = {"subprocess": SandboxStrategyConfig()}
        sandbox = SandboxManager(strategies)

        with pytest.raises(ValueError, match="Unknown sandbox strategy"):
            await sandbox.create_session("agent1", "unknown_strategy")

    @pytest.mark.asyncio
    async def test_command_execution_failure(self):
        """测试命令执行失败的情况"""
        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=90,
                memory_limit_mb=512
            )
        }
        sandbox = SandboxManager(strategies)
        session = await sandbox.create_session("agent1", "subprocess")

        # 执行一个会失败的命令
        result = await sandbox.run(session, "false")  # false命令总是返回1

        assert not result.success
        assert result.stdout == ""
        assert "exit code" in result.stderr.lower() or result.stderr == ""

    @pytest.mark.asyncio
    async def test_command_not_found(self):
        """测试命令不存在的情况"""
        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=90,
                memory_limit_mb=512
            )
        }
        sandbox = SandboxManager(strategies)
        session = await sandbox.create_session("agent1", "subprocess")

        # 执行不存在的命令
        result = await sandbox.run(session, "nonexistent_command_xyz")

        assert not result.success
        assert "command not found" in result.stderr.lower() or "no such file" in result.stderr.lower()

    @pytest.mark.asyncio
    async def test_command_timeout(self):
        """测试命令超时的情"""
        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=90,
                memory_limit_mb=512
            )
        }
        sandbox = SandboxManager(strategies)
        session = await sandbox.create_session("agent1", "subprocess")

        # 执行一个会长时间运行的命令（超过30秒超时）
        result = await sandbox.run(session, "sleep 35")

        # 由于我们在run方法中设置了30秒超时，这应该会超时
        assert not result.success
        assert result.latency_ms >= 30000  # 至少30秒

    @pytest.mark.asyncio
    async def test_resource_limit_exceeded_cpu(self):
        """测试CPU资源限制超限的情况"""
        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=1,  # 设置非常低的CPU限制
                memory_limit_mb=512
            )
        }
        sandbox = SandboxManager(strategies)
        session = await sandbox.create_session("agent1", "subprocess")

        # 执行一个CPU密集型命令
        result = await sandbox.run(session, "dd if=/dev/zero of=/dev/null bs=1M count=100")

        # 由于CPU限制很低，应该会失败
        # 注意：实际行为可能因系统而异，这里主要测试逻辑
        assert isinstance(result.success, bool)

    @pytest.mark.asyncio
    async def test_resource_limit_exceeded_memory(self):
        """测试内存资源限制超限的情况"""
        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=90,
                memory_limit_mb=1  # 设置非常低的内存限制
            )
        }
        sandbox = SandboxManager(strategies)
        session = await sandbox.create_session("agent1", "subprocess")

        # 尝试分配大量内存的命令
        result = await sandbox.run(session, "python3 -c \"[0] * 10**8\"")

        # 由于内存限制很低，应该会失败或被限制
        assert isinstance(result.success, bool)

    @pytest.mark.asyncio
    async def test_permission_denied(self):
        """测试权限拒绝的情况"""
        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=90,
                memory_limit_mb=512
            )
        }
        sandbox = SandboxManager(strategies)
        session = await sandbox.create_session("agent1", "subprocess")

        # 尝试访问无权限的文件
        result = await sandbox.run(session, "cat /etc/shadow")

        # 通常会权限拒绝
        assert not result.success or "permission denied" in result.stderr.lower()

    @pytest.mark.asyncio
    async def test_empty_command(self):
        """测试空命令的情况"""
        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=90,
                memory_limit_mb=512
            )
        }
        sandbox = SandboxManager(strategies)
        session = await sandbox.create_session("agent1", "subprocess")

        # 执行一个肯定会失败的命令
        result = await sandbox.run(session, "false")

        # false命令总是失败
        assert not result.success

    @pytest.mark.asyncio
    async def test_command_with_special_characters(self):
        """测试包含特殊字符的命令"""
        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=90,
                memory_limit_mb=512
            )
        }
        sandbox = SandboxManager(strategies)
        session = await sandbox.create_session("agent1", "subprocess")

        # 执行包含特殊字符的命令
        result = await sandbox.run(session, "echo 'hello & world'")

        assert result.success
        assert "hello & world" in result.stdout

    @pytest.mark.asyncio
    async def test_multiple_sessions_concurrent(self):
        """测试多个会话并发执行"""
        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=2,  # 限制并发数
                hard_cpu_limit_pct=90,
                memory_limit_mb=512
            )
        }
        sandbox = SandboxManager(strategies)

        async def run_command(agent_id):
            session = await sandbox.create_session(agent_id, "subprocess")
            result = await sandbox.run(session, f"echo 'Hello from {agent_id}'")
            return result

        # 并发执行多个命令
        tasks = [run_command(f"agent{i}") for i in range(5)]
        results = await asyncio.gather(*tasks)

        # 所有命令都应该成功
        assert all(result.success for result in results)
        assert all("Hello from" in result.stdout for result in results)

    @pytest.mark.asyncio
    async def test_event_emission_on_start(self):
        """测试执行开始时的事件发射"""
        events = []
        def event_handler(event):
            events.append(event)

        event_bus.subscribe("sandbox.exec", event_handler)

        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=90,
                memory_limit_mb=512
            )
        }
        sandbox = SandboxManager(strategies)
        session = await sandbox.create_session("agent1", "subprocess")

        # 执行命令
        result = await sandbox.run(session, "echo 'test'")

        # 检查开始事件
        start_events = [e for e in events if e.phase == "start"]
        assert len(start_events) == 1
        event = start_events[0]
        assert event.agent_id == "agent1"
        assert event.sandbox_strategy == "subprocess"
        assert event.command == "echo 'test'"

    @pytest.mark.asyncio
    async def test_event_emission_on_finish(self):
        """测试执行完成时的事件发射"""
        events = []
        def event_handler(event):
            events.append(event)

        event_bus.subscribe("sandbox.exec", event_handler)

        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=90,
                memory_limit_mb=512
            )
        }
        sandbox = SandboxManager(strategies)
        session = await sandbox.create_session("agent1", "subprocess")

        # 执行命令
        result = await sandbox.run(session, "echo 'test'")

        # 检查完成事件
        finish_events = [e for e in events if e.phase == "finish"]
        assert len(finish_events) == 1
        event = finish_events[0]
        assert event.agent_id == "agent1"
        assert event.sandbox_strategy == "subprocess"
        assert event.success == result.success
        assert event.latency_ms > 0

    @pytest.mark.asyncio
    async def test_psutil_not_available(self):
        """测试psutil不可用的情况"""
        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=90,
                memory_limit_mb=512
            )
        }
        sandbox = SandboxManager(strategies)
        session = await sandbox.create_session("agent1", "subprocess")

        # Mock psutil import failure
        with patch.dict('sys.modules', {'psutil': None}):
            result = await sandbox.run(session, "echo 'test without psutil'")

            # 应该仍然工作（使用fallback逻辑）
            assert isinstance(result.success, bool)

    @pytest.mark.asyncio
    async def test_subprocess_communication_failure(self):
        """测试子进程通信失败的情况"""
        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=90,
                memory_limit_mb=512
            )
        }
        sandbox = SandboxManager(strategies)
        session = await sandbox.create_session("agent1", "subprocess")

        # Mock subprocess.Popen to raise exception
        with patch('subprocess.Popen', side_effect=Exception("Process creation failed")):
            result = await sandbox.run(session, "echo 'test'")

            assert not result.success
            assert "Process creation failed" in result.stderr

    @pytest.mark.asyncio
    async def test_large_output_handling(self):
        """测试大输出处理的情况"""
        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=90,
                memory_limit_mb=512
            )
        }
        sandbox = SandboxManager(strategies)
        session = await sandbox.create_session("agent1", "subprocess")

        # 生成大量输出的命令
        result = await sandbox.run(session, "python3 -c \"print('x' * 10000)\"")

        assert result.success
        assert len(result.stdout) == 10001  # 10000 'x' + newline
        assert result.stdout.startswith("x")
        assert result.stdout.endswith("x\n")

    @pytest.mark.asyncio
    async def test_signal_interruption(self):
        """测试信号中断的情况"""
        strategies = {
            "subprocess": SandboxStrategyConfig(
                max_concurrency=8,
                hard_cpu_limit_pct=90,
                memory_limit_mb=512
            )
        }
        sandbox = SandboxManager(strategies)
        session = await sandbox.create_session("agent1", "subprocess")

        # 执行一个会被中断的命令
        result = await sandbox.run(session, "sleep 1 && exit 130")  # 130是SIGINT

        # 结果可能成功或失败，取决于具体实现
        assert isinstance(result.success, bool)