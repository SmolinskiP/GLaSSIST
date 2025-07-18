# GLaSSIST Tests

Comprehensive test suite for GLaSSIST Desktop Voice Assistant.

## Overview

This test suite provides comprehensive coverage for all major components of GLaSSIST:

- **Unit Tests** - Test individual components in isolation
- **Integration Tests** - Test component interactions and workflows
- **Configuration Tests** - Test configuration validation and loading
- **Error Handling Tests** - Test error scenarios and recovery

## Test Structure

```
tests/
├── __init__.py              # Package initialization
├── conftest.py             # Pytest configuration and fixtures
├── pytest.ini             # Pytest settings
├── requirements-test.txt   # Test dependencies
├── run_tests.py           # Test runner script
├── README.md              # This file
├── test_utils.py          # Tests for utils module
├── test_audio.py          # Tests for audio module
├── test_client.py         # Tests for Home Assistant client
├── test_wake_word_detector.py # Tests for wake word detection
├── test_animation_server.py   # Tests for animation server
├── test_main.py           # Tests for main application
└── test_integration.py    # Integration tests
```

## Running Tests

### Quick Start

```bash
# Install test dependencies and run all tests
python tests/run_tests.py

# Run only unit tests
python tests/run_tests.py --unit-only

# Run with coverage report
python tests/run_tests.py --coverage
```

### Manual Test Execution

```bash
# Install test dependencies
pip install -r tests/requirements-test.txt

# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_utils.py

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=html
```

### Test Runner Options

The `run_tests.py` script provides several options:

- `--unit-only` - Run only unit tests
- `--integration-only` - Run only integration tests
- `--coverage` - Generate coverage report
- `--parallel` - Run tests in parallel
- `--html` - Generate HTML test report
- `--verbose` - Verbose output
- `--skip-install` - Skip installing dependencies
- `--skip-syntax` - Skip syntax check
- `--test-file <file>` - Run specific test file

## Test Categories

### Unit Tests

Test individual components in isolation:

- **test_utils.py** - Environment variables, audio conversion, sound playback
- **test_audio.py** - Audio recording, microphone detection, VAD integration
- **test_client.py** - Home Assistant WebSocket client, pipeline management
- **test_wake_word_detector.py** - Wake word detection, model loading
- **test_animation_server.py** - WebSocket animation server, client communication
- **test_main.py** - Main application class, configuration validation

### Integration Tests

Test component interactions:

- **Voice Command Flow** - Complete voice command processing
- **Wake Word to Voice** - Wake word triggering voice commands
- **Animation Communication** - Server-client WebSocket communication
- **Configuration Loading** - Cross-module configuration consistency
- **Error Handling** - System-wide error handling and recovery

## Test Configuration

### Fixtures

The `conftest.py` file provides common test fixtures:

- `temp_dir` - Temporary directory for testing
- `mock_env_vars` - Mock environment variables
- `mock_pyaudio` - Mock PyAudio for audio testing
- `mock_websocket` - Mock WebSocket for network testing
- `mock_openwakeword` - Mock OpenWakeWord for wake word testing
- `mock_webview` - Mock webview for GUI testing

### Markers

Tests can be marked with categories:

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Slow tests (can be skipped)
- `@pytest.mark.asyncio` - Async tests

## Test Coverage

The test suite aims for high coverage across all modules:

- **Utils Module** - Environment handling, audio utilities, sound playback
- **Audio Module** - Recording, VAD, microphone management
- **Client Module** - WebSocket communication, pipeline management
- **Wake Word Module** - Model loading, detection, configuration
- **Animation Server** - WebSocket server, client handling
- **Main Application** - App lifecycle, configuration, error handling

## Writing Tests

### Test Structure

```python
class TestComponentName:
    """Test cases for ComponentName class."""
    
    def test_method_success(self):
        """Test successful method execution."""
        # Arrange
        component = ComponentName()
        
        # Act
        result = component.method()
        
        # Assert
        assert result is True
    
    def test_method_failure(self):
        """Test method failure handling."""
        # Test error scenarios
        pass
    
    @pytest.mark.asyncio
    async def test_async_method(self):
        """Test async method."""
        # Test async functionality
        pass
```

### Mocking Guidelines

- Use `unittest.mock` for mocking external dependencies
- Mock at the integration boundary (e.g., PyAudio, WebSocket)
- Use fixtures for common mock setups
- Test both success and failure scenarios

### Test Naming

- Test classes: `TestComponentName`
- Test methods: `test_method_scenario`
- Be descriptive: `test_connect_timeout`, `test_audio_init_no_microphone`

## Common Test Patterns

### Testing Environment Variables

```python
@patch.dict('os.environ', {'VAR_NAME': 'test_value'})
def test_env_variable():
    result = utils.get_env('VAR_NAME')
    assert result == 'test_value'
```

### Testing Async Code

```python
@pytest.mark.asyncio
async def test_async_function():
    result = await async_function()
    assert result is not None
```

### Testing Error Handling

```python
def test_error_handling():
    with pytest.raises(ValueError, match="Expected error message"):
        function_that_should_fail()
```

### Testing with Temporary Files

```python
def test_file_operations(temp_dir):
    test_file = os.path.join(temp_dir, 'test.txt')
    with open(test_file, 'w') as f:
        f.write('test content')
    
    # Test file operations
    assert os.path.exists(test_file)
```

## Continuous Integration

The test suite is designed to work with CI/CD systems:

- Tests run in isolation with proper mocking
- No external dependencies (Home Assistant, audio devices)
- Comprehensive error handling tests
- Fast execution with parallel support

## Troubleshooting

### Common Issues

1. **Import Errors** - Make sure project root is in Python path
2. **Audio Tests Failing** - Check PyAudio mocking in conftest.py
3. **WebSocket Tests Failing** - Verify websocket mocking setup
4. **Async Tests Failing** - Use `pytest-asyncio` and proper markers

### Debug Mode

Run tests with verbose output:

```bash
python tests/run_tests.py --verbose
```

### Coverage Reports

Generate detailed coverage reports:

```bash
python tests/run_tests.py --coverage
# Open htmlcov/index.html in browser
```

## Contributing

When adding new features:

1. Write tests for new functionality
2. Maintain test coverage above 80%
3. Include both unit and integration tests
4. Test error handling scenarios
5. Update test documentation