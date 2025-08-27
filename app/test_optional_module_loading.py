#!/usr/bin/env python3
"""
Test suite for optional module loading with graceful degradation.

This test verifies that the orchestrator can handle missing optional modules
gracefully and continue operating with basic functionality.

Requirements: 6.1, 6.2, 6.3, 6.4
"""

import pytest
import sys
import importlib
from unittest.mock import patch, MagicMock
import logging

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestOptionalModuleLoading:
    """Test optional module loading functionality."""
    
    def test_load_optional_modules_all_available(self):
        """Test loading when all optional modules are available."""
        # Import the function directly
        from orchestrator import load_optional_modules
        
        # Load modules
        modules = load_optional_modules()
        
        # Verify structure
        assert isinstance(modules, dict)
        assert 'psutil' in modules
        assert 'enhanced_orchestrator' in modules
        assert 'resilient_orchestrator' in modules
        
        # Each module should have the expected structure
        for module_name, module_info in modules.items():
            assert 'available' in module_info
            assert 'module' in module_info
            assert 'error' in module_info
            assert isinstance(module_info['available'], bool)
    
    def test_load_optional_modules_with_missing_psutil(self):
        """Test graceful degradation when psutil is missing."""
        # Mock psutil import failure
        with patch.dict('sys.modules', {'psutil': None}):
            with patch('builtins.__import__', side_effect=ImportError("No module named 'psutil'")):
                from orchestrator import load_optional_modules
                
                modules = load_optional_modules()
                
                # psutil should be marked as unavailable
                assert not modules['psutil']['available']
                assert modules['psutil']['error'] is not None
                assert modules['psutil']['module'] is None
    
    def test_load_optional_modules_with_missing_enhanced_orchestrator(self):
        """Test graceful degradation when enhanced_orchestrator is missing."""
        # Mock enhanced_orchestrator import failure
        original_import = __builtins__['__import__']
        
        def mock_import(name, *args, **kwargs):
            if name == 'enhanced_orchestrator':
                raise ImportError("No module named 'enhanced_orchestrator'")
            return original_import(name, *args, **kwargs)
        
        with patch('builtins.__import__', side_effect=mock_import):
            from orchestrator import load_optional_modules
            
            modules = load_optional_modules()
            
            # enhanced_orchestrator should be marked as unavailable
            assert not modules['enhanced_orchestrator']['available']
            assert modules['enhanced_orchestrator']['error'] is not None
            assert modules['enhanced_orchestrator']['module'] is None
    
    def test_load_optional_modules_with_missing_resilient_orchestrator(self):
        """Test graceful degradation when resilient_orchestrator is missing."""
        # Mock resilient_orchestrator import failure
        original_import = __builtins__['__import__']
        
        def mock_import(name, *args, **kwargs):
            if name == 'resilient_orchestrator':
                raise ImportError("No module named 'resilient_orchestrator'")
            return original_import(name, *args, **kwargs)
        
        with patch('builtins.__import__', side_effect=mock_import):
            from orchestrator import load_optional_modules
            
            modules = load_optional_modules()
            
            # resilient_orchestrator should be marked as unavailable
            assert not modules['resilient_orchestrator']['available']
            assert modules['resilient_orchestrator']['error'] is not None
            assert modules['resilient_orchestrator']['module'] is None
    
    def test_orchestrator_initialization_with_missing_modules(self):
        """Test StreamOrchestrator initialization with missing optional modules."""
        # Mock missing modules
        with patch('orchestrator.HAS_SMART_BALANCER', False):
            with patch('orchestrator.HAS_RESILIENT_ORCHESTRATOR', False):
                with patch('orchestrator.setup_database', return_value=True):
                    with patch('psycopg2.connect'):
                        from orchestrator import StreamOrchestrator
                        
                        # Should initialize without errors
                        orch = StreamOrchestrator()
                        
                        # Optional components should be None
                        assert orch.enhanced_orchestrator is None
                        assert orch.resilient_orchestrator is None
    
    def test_orchestrator_initialization_with_failed_enhanced_init(self):
        """Test graceful handling when enhanced orchestrator initialization fails."""
        with patch('orchestrator.HAS_SMART_BALANCER', True):
            with patch('orchestrator.create_load_balance_config', side_effect=Exception("Config error")):
                with patch('orchestrator.setup_database', return_value=True):
                    with patch('psycopg2.connect'):
                        from orchestrator import StreamOrchestrator
                        
                        # Should initialize without errors despite enhanced orchestrator failure
                        orch = StreamOrchestrator()
                        
                        # Enhanced orchestrator should be None due to initialization failure
                        assert orch.enhanced_orchestrator is None
    
    def test_orchestrator_initialization_with_failed_resilient_init(self):
        """Test graceful handling when resilient orchestrator initialization fails."""
        with patch('orchestrator.HAS_RESILIENT_ORCHESTRATOR', True):
            with patch('orchestrator.ResilientOrchestrator', side_effect=Exception("Init error")):
                with patch('orchestrator.setup_database', return_value=True):
                    with patch('psycopg2.connect'):
                        from orchestrator import StreamOrchestrator
                        
                        # Should initialize without errors despite resilient orchestrator failure
                        orch = StreamOrchestrator()
                        
                        # Resilient orchestrator should be None due to initialization failure
                        assert orch.resilient_orchestrator is None
    
    def test_get_optional_modules_status(self):
        """Test getting optional modules status information."""
        with patch('orchestrator.setup_database', return_value=True):
            with patch('psycopg2.connect'):
                from orchestrator import StreamOrchestrator
                
                orch = StreamOrchestrator()
                status = orch.get_optional_modules_status()
                
                # Verify status structure
                assert 'timestamp' in status
                assert 'modules' in status
                assert 'functionality' in status
                
                # Verify functionality flags
                functionality = status['functionality']
                assert 'basic_orchestration' in functionality
                assert 'smart_load_balancing' in functionality
                assert 'enhanced_failure_handling' in functionality
                assert 'system_metrics' in functionality
                
                # Basic orchestration should always be True
                assert functionality['basic_orchestration'] is True
    
    def test_db_connection_fallback_when_resilient_unavailable(self):
        """Test database connection fallback when resilient orchestrator is unavailable."""
        with patch('orchestrator.setup_database', return_value=True):
            with patch('psycopg2.connect') as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value = mock_conn
                
                from orchestrator import StreamOrchestrator
                
                # Create orchestrator without resilient orchestrator
                orch = StreamOrchestrator()
                orch.resilient_orchestrator = None
                
                # Get connection should use fallback
                conn = orch.get_db_connection()
                
                # Should have called psycopg2.connect directly
                mock_connect.assert_called()
                assert conn == mock_conn
    
    def test_db_connection_with_resilient_fallback(self):
        """Test database connection with resilient orchestrator fallback."""
        with patch('orchestrator.setup_database', return_value=True):
            with patch('psycopg2.connect') as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value = mock_conn
                
                from orchestrator import StreamOrchestrator
                
                # Create orchestrator with mock resilient orchestrator
                orch = StreamOrchestrator()
                mock_resilient = MagicMock()
                mock_resilient.get_db_connection.side_effect = Exception("Resilient connection failed")
                orch.resilient_orchestrator = mock_resilient
                
                # Get connection should fallback to basic connection
                conn = orch.get_db_connection()
                
                # Should have tried resilient first, then fallen back
                mock_resilient.get_db_connection.assert_called_once()
                mock_connect.assert_called()
                assert conn == mock_conn


class TestModuleStatusEndpoint:
    """Test the module status API endpoint."""
    
    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock orchestrator for testing."""
        mock_orch = MagicMock()
        mock_orch.get_optional_modules_status.return_value = {
            "timestamp": "2025-01-01T00:00:00",
            "modules": {
                "psutil": {"available": True, "error": None, "initialized": True},
                "enhanced_orchestrator": {"available": False, "error": "ImportError", "initialized": False},
                "resilient_orchestrator": {"available": True, "error": None, "initialized": True}
            },
            "functionality": {
                "basic_orchestration": True,
                "smart_load_balancing": False,
                "enhanced_failure_handling": True,
                "system_metrics": True
            }
        }
        return mock_orch
    
    def test_modules_status_endpoint_success(self, mock_orchestrator):
        """Test successful module status endpoint response."""
        from fastapi.testclient import TestClient
        from orchestrator import app
        
        # Mock the app state
        app.state.orchestrator = mock_orchestrator
        
        client = TestClient(app)
        response = client.get("/modules/status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "success"
        assert "timestamp" in data
        assert "modules" in data
        assert "functionality" in data
        assert "summary" in data
        
        # Verify summary calculations
        summary = data["summary"]
        assert summary["total_modules"] == 3
        assert summary["available_modules"] == 2  # psutil and resilient_orchestrator
        assert summary["initialized_modules"] == 2
        assert summary["degraded_functionality"] is True  # smart_load_balancing is False
    
    def test_modules_status_endpoint_error(self):
        """Test module status endpoint error handling."""
        from fastapi.testclient import TestClient
        from orchestrator import app
        
        # Mock orchestrator that raises an exception
        mock_orch = MagicMock()
        mock_orch.get_optional_modules_status.side_effect = Exception("Test error")
        app.state.orchestrator = mock_orch
        
        client = TestClient(app)
        response = client.get("/modules/status")
        
        assert response.status_code == 500
        data = response.json()
        
        assert data["detail"]["status"] == "error"
        assert "error" in data["detail"]
        assert "timestamp" in data["detail"]


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])