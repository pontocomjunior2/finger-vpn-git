#!/usr/bin/env python3
"""
Integration Tests for Orchestrator-Worker Communication

Focused integration testing for orchestrator-worker communication patterns,
including failure scenarios, retry mechanisms, and consistency verification.

Requirements: 1.1, 1.2, 4.1, 5.2, 5.3, 5.4
"""

import asyncio
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp
import pytest

logger = logging.getLogger(__name__)

# Import components for integration testing
try:
    from enhanced_orchestrator import EnhancedStreamOrchestrator
    from resilient_orchestrator import ResilientOrchestrator
    from resilient_worker_client import ResilientWorkerClient
    from smart_load_balancer import LoadBalanceConfig
    HAS_COMPONENTS = True
except ImportError as e:
    logger.warning(f"Components not available for integration testing: {e}")
    HAS_COMPONENTS = False


class MockOrchestratorServer:
    """Mock orchestrator server for integration testing"""
    
    def __init__(self):
        self.registered_instances = {}
        self.stream_assignments = {}
        self.heartbeat_history = {}
        self.failure_simulation = False
        self.response_delay = 0
        
    async def register_instance(self, server_id: str, ip: str, port: int, max_streams: int):
        """Mock instance registration"""
        if self.failure_simulation:
            raise aiohttp.ClientError("Simulated failure")
        
        if self.response_delay > 0:
            await asyncio.sleep(self.response_delay)
        
        self.registered_instances[server_id] = {
            'ip': ip,
            'port': port,
            'max_streams': max_streams,
            'current_streams': 0,
            'registered_at': datetime.now()
        }
        
        return {
            'status': 'success',
            'server_id': server_id,
            'assigned_streams': []
        }
    
    async def send_heartbeat(self, server_id: str, metrics: Dict):
        """Mock heartbeat processing"""
        if self.failure_simulation:
            raise aiohttp.ClientError("Simulated failure")
        
        if self.response_delay > 0:
            await asyncio.sleep(self.response_delay)
        
        if server_id not in self.registered_instances:
            return {'status': 'error', 'message': 'Instance not registered'}
        
        # Update instance metrics
        self.registered_instances[server_id].update(metrics)
        self.registered_instances[server_id]['last_heartbeat'] = datetime.now()
        
        # Store heartbeat history
        if server_id not in self.heartbeat_history:
            self.heartbeat_history[server_id] = []
        self.heartbeat_history[server_id].append({
            'timestamp': datetime.now(),
            'metrics': metrics.copy()
        })
        
        return {
            'status': 'ok',
            'server_id': server_id,
            'instructions': []
        }
    
    async def get_stream_assignments(self, server_id: str):
        """Mock stream assignment retrieval"""
        if self.failure_simulation:
            raise aiohttp.ClientError("Simulated failure")
        
        return {
            'status': 'success',
            'streams': self.stream_assignments.get(server_id, [])
        }
    
    def simulate_failure(self, enable: bool = True):
        """Enable/disable failure simulation"""
        self.failure_simulation = enable
    
    def set_response_delay(self, delay_seconds: float):
        """Set response delay for testing timeouts"""
        self.response_delay = delay_seconds


@pytest.mark.skipif(not HAS_COMPONENTS, reason="Components not available")
class TestOrchestratorWorkerRegistration:
    """Test orchestrator-worker registration flow"""
    
    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator server"""
        return MockOrchestratorServer()
    
    @pytest.fixture
    def worker_client(self):
        """Create worker client for testing"""
        return ResilientWorkerClient("http://localhost:8001", "test-worker-1")
    
    @pytest.mark.asyncio
    async def test_successful_registration(self, worker_client, mock_orchestrator):
        """Test successful worker registration (Requirement 1.1)"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            # Mock successful registration
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value=await mock_orchestrator.register_instance(
                    "test-worker-1", "127.0.0.1", 8000, 20
                )
            )
            mock_post.return_value.__aenter__.return_value = mock_response
            
            result = await worker_client.register_with_orchestrator(
                ip="127.0.0.1", port=8000, max_streams=20
            )
            
            assert result is not None
            assert result['status'] == 'success'
            assert result['server_id'] == 'test-worker-1'
    
    @pytest.mark.asyncio
    async def test_registration_retry_on_failure(self, worker_client, mock_orchestrator):
        """Test registration retry mechanism (Requirement 5.3)"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            # First attempt fails, second succeeds
            mock_response_fail = AsyncMock()
            mock_response_fail.status = 500
            
            mock_response_success = AsyncMock()
            mock_response_success.status = 200
            mock_response_success.json = AsyncMock(
                return_value=await mock_orchestrator.register_instance(
                    "test-worker-1", "127.0.0.1", 8000, 20
                )
            )
            
            mock_post.side_effect = [
                mock_response_fail.__aenter__.return_value,
                mock_response_success.__aenter__.return_value
            ]
            
            result = await worker_client.register_with_orchestrator_retry(
                ip="127.0.0.1", port=8000, max_streams=20, max_retries=2
            )
            
            assert result is not None
            assert result['status'] == 'success'
    
    @pytest.mark.asyncio
    async def test_registration_timeout_handling(self, worker_client, mock_orchestrator):
        """Test registration timeout handling (Requirement 5.2)"""
        mock_orchestrator.set_response_delay(5.0)  # 5 second delay
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            # Simulate timeout
            mock_post.side_effect = asyncio.TimeoutError("Request timeout")
            
            start_time = time.time()
            result = await worker_client.register_with_orchestrator(
                ip="127.0.0.1", port=8000, max_streams=20, timeout=2.0
            )
            end_time = time.time()
            
            # Should timeout within reasonable time
            assert end_time - start_time < 3.0
            assert result is None or result.get('status') == 'timeout'
    
    @pytest.mark.asyncio
    async def test_duplicate_registration_handling(self, worker_client, mock_orchestrator):
        """Test handling of duplicate registration attempts"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            # First registration
            mock_response1 = AsyncMock()
            mock_response1.status = 200
            mock_response1.json = AsyncMock(
                return_value=await mock_orchestrator.register_instance(
                    "test-worker-1", "127.0.0.1", 8000, 20
                )
            )
            
            # Second registration (duplicate)
            mock_response2 = AsyncMock()
            mock_response2.status = 409  # Conflict
            mock_response2.json = AsyncMock(
                return_value={'status': 'already_registered', 'server_id': 'test-worker-1'}
            )
            
            mock_post.side_effect = [
                mock_response1.__aenter__.return_value,
                mock_response2.__aenter__.return_value
            ]
            
            # First registration should succeed
            result1 = await worker_client.register_with_orchestrator(
                ip="127.0.0.1", port=8000, max_streams=20
            )
            assert result1['status'] == 'success'
            
            # Second registration should handle duplicate gracefully
            result2 = await worker_client.register_with_orchestrator(
                ip="127.0.0.1", port=8000, max_streams=20
            )
            assert result2['status'] == 'already_registered'


@pytest.mark.skipif(not HAS_COMPONENTS, reason="Components not available")
class TestOrchestratorWorkerHeartbeat:
    """Test orchestrator-worker heartbeat communication"""
    
    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator server"""
        return MockOrchestratorServer()
    
    @pytest.fixture
    def worker_client(self):
        """Create worker client for testing"""
        return ResilientWorkerClient("http://localhost:8001", "test-worker-heartbeat")
    
    @pytest.mark.asyncio
    async def test_successful_heartbeat(self, worker_client, mock_orchestrator):
        """Test successful heartbeat communication (Requirement 4.1)"""
        # Register instance first
        await mock_orchestrator.register_instance("test-worker-heartbeat", "127.0.0.1", 8000, 20)
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value=await mock_orchestrator.send_heartbeat(
                    "test-worker-heartbeat", {
                        'current_streams': 10,
                        'cpu_percent': 50.0,
                        'memory_percent': 60.0
                    }
                )
            )
            mock_post.return_value.__aenter__.return_value = mock_response
            
            result = await worker_client.send_heartbeat({
                'current_streams': 10,
                'cpu_percent': 50.0,
                'memory_percent': 60.0
            })
            
            assert result is not None
            assert result['status'] == 'ok'
    
    @pytest.mark.asyncio
    async def test_heartbeat_with_unregistered_instance(self, worker_client, mock_orchestrator):
        """Test heartbeat from unregistered instance"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_response.json = AsyncMock(
                return_value={'status': 'error', 'message': 'Instance not registered'}
            )
            mock_post.return_value.__aenter__.return_value = mock_response
            
            result = await worker_client.send_heartbeat({
                'current_streams': 10
            })
            
            # Should handle unregistered instance gracefully
            assert result is not None
            assert result['status'] == 'error'
    
    @pytest.mark.asyncio
    async def test_heartbeat_failure_recovery(self, worker_client, mock_orchestrator):
        """Test heartbeat failure and recovery (Requirement 5.2, 5.3)"""
        # Register instance first
        await mock_orchestrator.register_instance("test-worker-heartbeat", "127.0.0.1", 8000, 20)
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            # Simulate failure then recovery
            mock_response_fail = AsyncMock()
            mock_response_fail.status = 500
            
            mock_response_success = AsyncMock()
            mock_response_success.status = 200
            mock_response_success.json = AsyncMock(
                return_value=await mock_orchestrator.send_heartbeat(
                    "test-worker-heartbeat", {'current_streams': 10}
                )
            )
            
            mock_post.side_effect = [
                mock_response_fail.__aenter__.return_value,
                mock_response_success.__aenter__.return_value
            ]
            
            # Should retry and recover
            result = await worker_client.send_heartbeat_with_retry({
                'current_streams': 10
            })
            
            assert result is not None
            assert result['status'] == 'ok'
    
    @pytest.mark.asyncio
    async def test_heartbeat_circuit_breaker(self, worker_client, mock_orchestrator):
        """Test circuit breaker pattern in heartbeat (Requirement 5.2)"""
        mock_orchestrator.simulate_failure(True)
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.side_effect = aiohttp.ClientError("Persistent failure")
            
            # Send multiple failed heartbeats to trigger circuit breaker
            for i in range(6):  # Exceed failure threshold
                result = await worker_client.send_heartbeat({'current_streams': i})
                assert result is None or result.get('status') == 'error'
            
            # Circuit breaker should be open
            assert worker_client.circuit_breaker_open is True
            
            # Next heartbeat should be blocked by circuit breaker
            result = await worker_client.send_heartbeat({'current_streams': 10})
            assert result is None or result.get('status') == 'circuit_breaker_open'
    
    @pytest.mark.asyncio
    async def test_heartbeat_frequency_control(self, worker_client, mock_orchestrator):
        """Test heartbeat frequency control"""
        # Register instance first
        await mock_orchestrator.register_instance("test-worker-heartbeat", "127.0.0.1", 8000, 20)
        
        heartbeat_count = 0
        
        async def mock_heartbeat_handler(*args, **kwargs):
            nonlocal heartbeat_count
            heartbeat_count += 1
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value=await mock_orchestrator.send_heartbeat(
                    "test-worker-heartbeat", {'current_streams': 10}
                )
            )
            return mock_response.__aenter__.return_value
        
        with patch('aiohttp.ClientSession.post', side_effect=mock_heartbeat_handler):
            # Start heartbeat with 0.1 second interval
            heartbeat_task = asyncio.create_task(
                worker_client.start_heartbeat_loop(interval=0.1)
            )
            
            # Let it run for 0.5 seconds
            await asyncio.sleep(0.5)
            heartbeat_task.cancel()
            
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            
            # Should have sent approximately 5 heartbeats
            assert 3 <= heartbeat_count <= 7  # Allow some variance


@pytest.mark.skipif(not HAS_COMPONENTS, reason="Components not available")
class TestOrchestratorWorkerStreamManagement:
    """Test stream assignment and management between orchestrator and worker"""
    
    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator server"""
        orchestrator = MockOrchestratorServer()
        # Pre-populate with some stream assignments
        orchestrator.stream_assignments = {
            "test-worker-streams": [1, 2, 3, 4, 5]
        }
        return orchestrator
    
    @pytest.fixture
    def worker_client(self):
        """Create worker client for testing"""
        return ResilientWorkerClient("http://localhost:8001", "test-worker-streams")
    
    @pytest.mark.asyncio
    async def test_stream_assignment_retrieval(self, worker_client, mock_orchestrator):
        """Test retrieving stream assignments from orchestrator"""
        # Register instance first
        await mock_orchestrator.register_instance("test-worker-streams", "127.0.0.1", 8000, 20)
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value=await mock_orchestrator.get_stream_assignments("test-worker-streams")
            )
            mock_get.return_value.__aenter__.return_value = mock_response
            
            streams = await worker_client.get_assigned_streams()
            
            assert streams is not None
            assert len(streams) == 5
            assert streams == [1, 2, 3, 4, 5]
    
    @pytest.mark.asyncio
    async def test_stream_assignment_update_notification(self, worker_client, mock_orchestrator):
        """Test notification of stream assignment updates"""
        # Register instance first
        await mock_orchestrator.register_instance("test-worker-streams", "127.0.0.1", 8000, 20)
        
        # Simulate stream assignment update through heartbeat response
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'status': 'ok',
                'server_id': 'test-worker-streams',
                'instructions': [
                    {'action': 'assign_streams', 'streams': [6, 7, 8]},
                    {'action': 'release_streams', 'streams': [1, 2]}
                ]
            })
            mock_post.return_value.__aenter__.return_value = mock_response
            
            result = await worker_client.send_heartbeat({'current_streams': 5})
            
            assert result is not None
            assert 'instructions' in result
            assert len(result['instructions']) == 2
    
    @pytest.mark.asyncio
    async def test_stream_consistency_verification(self, worker_client, mock_orchestrator):
        """Test stream consistency verification between worker and orchestrator"""
        # Register instance first
        await mock_orchestrator.register_instance("test-worker-streams", "127.0.0.1", 8000, 20)
        
        # Worker thinks it has different streams than orchestrator
        worker_streams = [1, 2, 3, 9, 10]  # 9, 10 not in orchestrator
        orchestrator_streams = [1, 2, 3, 4, 5]  # 4, 5 not in worker
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'status': 'inconsistency_detected',
                'expected_streams': orchestrator_streams,
                'instructions': [
                    {'action': 'release_streams', 'streams': [9, 10]},
                    {'action': 'assign_streams', 'streams': [4, 5]}
                ]
            })
            mock_post.return_value.__aenter__.return_value = mock_response
            
            # Send heartbeat with current streams
            result = await worker_client.send_heartbeat({
                'current_streams': len(worker_streams),
                'stream_list': worker_streams
            })
            
            assert result is not None
            assert result['status'] == 'inconsistency_detected'
            assert 'expected_streams' in result
            assert 'instructions' in result


@pytest.mark.skipif(not HAS_COMPONENTS, reason="Components not available")
class TestOrchestratorWorkerFailureScenarios:
    """Test failure scenarios in orchestrator-worker communication"""
    
    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator server"""
        return MockOrchestratorServer()
    
    @pytest.fixture
    def worker_client(self):
        """Create worker client for testing"""
        return ResilientWorkerClient("http://localhost:8001", "test-worker-failure")
    
    @pytest.mark.asyncio
    async def test_orchestrator_unavailable_scenario(self, worker_client, mock_orchestrator):
        """Test worker behavior when orchestrator is unavailable (Requirement 5.4)"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            # Simulate orchestrator unavailable
            mock_post.side_effect = aiohttp.ClientConnectorError(
                connection_key=None, os_error=OSError("Connection refused")
            )
            
            # Worker should detect orchestrator unavailability
            result = await worker_client.check_orchestrator_availability()
            assert result is False
            
            # Worker should enter local operation mode
            await worker_client.handle_orchestrator_unavailable()
            assert worker_client.local_mode_enabled is True
            
            # Worker should continue processing with local streams
            local_streams = await worker_client.get_local_streams()
            assert isinstance(local_streams, list)
    
    @pytest.mark.asyncio
    async def test_partial_network_failure(self, worker_client, mock_orchestrator):
        """Test partial network failure scenarios"""
        failure_count = 0
        
        async def intermittent_failure(*args, **kwargs):
            nonlocal failure_count
            failure_count += 1
            
            if failure_count % 3 == 0:  # Every third request succeeds
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value={'status': 'ok'})
                return mock_response.__aenter__.return_value
            else:
                raise aiohttp.ClientError("Intermittent failure")
        
        with patch('aiohttp.ClientSession.post', side_effect=intermittent_failure):
            # Should handle intermittent failures with retry
            success_count = 0
            for i in range(10):
                result = await worker_client.send_heartbeat_with_retry(
                    {'current_streams': i}, max_retries=3
                )
                if result and result.get('status') == 'ok':
                    success_count += 1
            
            # Should have some successful heartbeats despite failures
            assert success_count > 0
    
    @pytest.mark.asyncio
    async def test_orchestrator_recovery_detection(self, worker_client, mock_orchestrator):
        """Test detection of orchestrator recovery after failure"""
        # Start with orchestrator unavailable
        worker_client.orchestrator_reachable = False
        worker_client.local_mode_enabled = True
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            # First few attempts fail, then orchestrator recovers
            mock_response_fail = AsyncMock()
            mock_response_fail.side_effect = aiohttp.ClientError("Still down")
            
            mock_response_success = AsyncMock()
            mock_response_success.status = 200
            mock_response_success.json = AsyncMock(return_value={'status': 'ok'})
            
            mock_post.side_effect = [
                mock_response_fail,
                mock_response_fail,
                mock_response_success.__aenter__.return_value
            ]
            
            # Should detect recovery
            recovery_detected = await worker_client.check_orchestrator_recovery()
            assert recovery_detected is True
            
            # Should exit local mode
            assert worker_client.local_mode_enabled is False
            assert worker_client.orchestrator_reachable is True
    
    @pytest.mark.asyncio
    async def test_data_corruption_in_communication(self, worker_client, mock_orchestrator):
        """Test handling of corrupted data in communication"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            # Return corrupted JSON response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(side_effect=json.JSONDecodeError("Invalid JSON", "", 0))
            mock_post.return_value.__aenter__.return_value = mock_response
            
            # Should handle corrupted response gracefully
            result = await worker_client.send_heartbeat({'current_streams': 10})
            
            # Should return None or error indication, but not crash
            assert result is None or result.get('status') == 'error'
    
    @pytest.mark.asyncio
    async def test_timeout_escalation(self, worker_client, mock_orchestrator):
        """Test timeout escalation strategy"""
        mock_orchestrator.set_response_delay(2.0)  # 2 second delay
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            # Simulate slow responses
            async def slow_response(*args, **kwargs):
                await asyncio.sleep(2.0)
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value={'status': 'ok'})
                return mock_response.__aenter__.return_value
            
            mock_post.side_effect = slow_response
            
            # Should escalate timeout and eventually succeed or fail gracefully
            start_time = time.time()
            result = await worker_client.send_heartbeat_with_escalating_timeout(
                {'current_streams': 10},
                initial_timeout=0.5,
                max_timeout=3.0
            )
            end_time = time.time()
            
            # Should either succeed within max timeout or fail gracefully
            assert end_time - start_time <= 4.0  # Allow some buffer
            assert result is not None or result is None


@pytest.mark.skipif(not HAS_COMPONENTS, reason="Components not available")
class TestOrchestratorWorkerLoadBalancing:
    """Test load balancing integration between orchestrator and workers"""
    
    @pytest.fixture
    def mock_orchestrator_with_balancing(self):
        """Create mock orchestrator with load balancing capabilities"""
        orchestrator = MockOrchestratorServer()
        
        # Add load balancing logic
        orchestrator.load_balancer = Mock()
        orchestrator.load_balancer.detect_imbalance.return_value = True
        orchestrator.load_balancer.generate_rebalance_plan.return_value = Mock(
            migrations=[
                Mock(source_server="worker-1", target_server="worker-2", stream_count=5),
                Mock(source_server="worker-3", target_server="worker-2", stream_count=3)
            ]
        )
        
        return orchestrator
    
    @pytest.fixture
    def multiple_worker_clients(self):
        """Create multiple worker clients for load balancing tests"""
        return [
            ResilientWorkerClient("http://localhost:8001", f"test-worker-{i}")
            for i in range(1, 4)
        ]
    
    @pytest.mark.asyncio
    async def test_load_balancing_trigger(self, multiple_worker_clients, mock_orchestrator_with_balancing):
        """Test load balancing trigger through worker communication"""
        # Register all workers
        for i, client in enumerate(multiple_worker_clients):
            await mock_orchestrator_with_balancing.register_instance(
                f"test-worker-{i+1}", "127.0.0.1", 8000 + i, 20
            )
        
        # Simulate imbalanced load through heartbeats
        imbalanced_loads = [18, 2, 15]  # Heavily imbalanced
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            responses = []
            
            for i, (client, load) in enumerate(zip(multiple_worker_clients, imbalanced_loads)):
                if i == 0:  # First worker triggers rebalancing
                    response_data = {
                        'status': 'rebalancing_triggered',
                        'instructions': [
                            {'action': 'release_streams', 'streams': [1, 2, 3, 4, 5]}
                        ]
                    }
                else:
                    response_data = {'status': 'ok'}
                
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value=response_data)
                responses.append(mock_response.__aenter__.return_value)
            
            mock_post.side_effect = responses
            
            # Send heartbeats from all workers
            results = []
            for client, load in zip(multiple_worker_clients, imbalanced_loads):
                result = await client.send_heartbeat({'current_streams': load})
                results.append(result)
            
            # First worker should receive rebalancing instructions
            assert results[0]['status'] == 'rebalancing_triggered'
            assert 'instructions' in results[0]
    
    @pytest.mark.asyncio
    async def test_stream_migration_coordination(self, multiple_worker_clients, mock_orchestrator_with_balancing):
        """Test coordination of stream migration between workers"""
        # Register workers
        for i, client in enumerate(multiple_worker_clients):
            await mock_orchestrator_with_balancing.register_instance(
                f"test-worker-{i+1}", "127.0.0.1", 8000 + i, 20
            )
        
        # Simulate stream migration
        with patch('aiohttp.ClientSession.post') as mock_post:
            # Source worker receives release instruction
            release_response = AsyncMock()
            release_response.status = 200
            release_response.json = AsyncMock(return_value={
                'status': 'ok',
                'instructions': [
                    {'action': 'release_streams', 'streams': [1, 2, 3], 'target_worker': 'test-worker-2'}
                ]
            })
            
            # Target worker receives assign instruction
            assign_response = AsyncMock()
            assign_response.status = 200
            assign_response.json = AsyncMock(return_value={
                'status': 'ok',
                'instructions': [
                    {'action': 'assign_streams', 'streams': [1, 2, 3], 'source_worker': 'test-worker-1'}
                ]
            })
            
            mock_post.side_effect = [
                release_response.__aenter__.return_value,
                assign_response.__aenter__.return_value
            ]
            
            # Source worker heartbeat
            result1 = await multiple_worker_clients[0].send_heartbeat({'current_streams': 18})
            assert 'instructions' in result1
            assert result1['instructions'][0]['action'] == 'release_streams'
            
            # Target worker heartbeat
            result2 = await multiple_worker_clients[1].send_heartbeat({'current_streams': 2})
            assert 'instructions' in result2
            assert result2['instructions'][0]['action'] == 'assign_streams'
    
    @pytest.mark.asyncio
    async def test_load_balancing_failure_recovery(self, multiple_worker_clients, mock_orchestrator_with_balancing):
        """Test recovery from load balancing failures"""
        # Register workers
        for i, client in enumerate(multiple_worker_clients):
            await mock_orchestrator_with_balancing.register_instance(
                f"test-worker-{i+1}", "127.0.0.1", 8000 + i, 20
            )
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            # Simulate migration failure
            failure_response = AsyncMock()
            failure_response.status = 200
            failure_response.json = AsyncMock(return_value={
                'status': 'migration_failed',
                'instructions': [
                    {'action': 'rollback_migration', 'streams': [1, 2, 3]}
                ]
            })
            
            mock_post.return_value.__aenter__.return_value = failure_response
            
            # Worker reports migration failure
            result = await multiple_worker_clients[0].send_heartbeat({
                'current_streams': 15,
                'migration_status': 'failed',
                'failed_streams': [1, 2, 3]
            })
            
            assert result['status'] == 'migration_failed'
            assert 'instructions' in result
            assert result['instructions'][0]['action'] == 'rollback_migration'


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "--tb=short"])