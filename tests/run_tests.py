#!/usr/bin/env python3
"""
Test runner script for GLaSSIST Desktop Voice Assistant.
"""
import os
import sys
import subprocess
import argparse


def run_command(command, description):
    """Run a command and handle errors."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {command}")
    print('='*60)
    
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=False)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed with exit code {e.returncode}")
        return False
    except Exception as e:
        print(f"❌ {description} failed with error: {e}")
        return False


def install_test_dependencies():
    """Install test dependencies."""
    print("Installing test dependencies...")
    
    # Check if we're in a virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("✅ Virtual environment detected")
    else:
        print("⚠️  Warning: Not in a virtual environment")
    
    # Install test requirements
    test_req_path = os.path.join(os.path.dirname(__file__), 'requirements-test.txt')
    if os.path.exists(test_req_path):
        command = f"pip install -r {test_req_path}"
        return run_command(command, "Installing test dependencies")
    else:
        print("❌ requirements-test.txt not found")
        return False


def run_syntax_check():
    """Run Python syntax check on all source files."""
    print("Running Python syntax check...")
    
    # Get project root
    project_root = os.path.dirname(os.path.dirname(__file__))
    
    # Find all Python files
    python_files = []
    for root, dirs, files in os.walk(project_root):
        # Skip test directory and virtual environments
        if 'tests' in root or 'venv' in root or '__pycache__' in root:
            continue
            
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    if not python_files:
        print("❌ No Python files found")
        return False
    
    print(f"Found {len(python_files)} Python files")
    
    # Check syntax for each file
    failed_files = []
    for file_path in python_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                compile(f.read(), file_path, 'exec')
        except SyntaxError as e:
            print(f"❌ Syntax error in {file_path}: {e}")
            failed_files.append(file_path)
        except Exception as e:
            print(f"❌ Error checking {file_path}: {e}")
            failed_files.append(file_path)
    
    if failed_files:
        print(f"❌ Syntax check failed for {len(failed_files)} files")
        return False
    else:
        print("✅ All Python files have valid syntax")
        return True


def run_unit_tests(args):
    """Run unit tests."""
    print("Running unit tests...")
    
    # Base command
    cmd_parts = ["python", "-m", "pytest"]
    
    # Add test directory
    test_dir = os.path.dirname(__file__)
    cmd_parts.append(test_dir)
    
    # Add coverage if requested
    if args.coverage:
        cmd_parts.extend([
            "--cov=../",
            "--cov-report=html:htmlcov",
            "--cov-report=term-missing",
            "--cov-exclude=tests/*",
            "--cov-exclude=venv/*",
            "--cov-exclude=old/*"
        ])
    
    # Add specific test filters
    if args.unit_only:
        cmd_parts.extend(["-m", "unit"])
    elif args.integration_only:
        cmd_parts.extend(["-m", "integration"])
    
    # Add verbose output
    if args.verbose:
        cmd_parts.append("-v")
    
    # Add parallel execution
    if args.parallel:
        cmd_parts.extend(["-n", "auto"])
    
    # Add HTML report
    if args.html:
        cmd_parts.extend(["--html=report.html", "--self-contained-html"])
    
    # Add specific test file if provided
    if args.test_file:
        cmd_parts.append(args.test_file)
    
    command = " ".join(cmd_parts)
    return run_command(command, "Unit Tests")


def run_integration_tests():
    """Run integration tests."""
    print("Running integration tests...")
    
    test_dir = os.path.dirname(__file__)
    command = f"python -m pytest {test_dir}/test_integration.py -v"
    return run_command(command, "Integration Tests")


def run_all_tests(args):
    """Run all test suites."""
    print("🧪 GLaSSIST Test Suite")
    print("=" * 60)
    
    results = {}
    
    # Install dependencies
    if not args.skip_install:
        results['install'] = install_test_dependencies()
    else:
        results['install'] = True
        print("⏭️  Skipping dependency installation")
    
    # Run syntax check
    if not args.skip_syntax:
        results['syntax'] = run_syntax_check()
    else:
        results['syntax'] = True
        print("⏭️  Skipping syntax check")
    
    # Run unit tests
    if results['install'] and results['syntax']:
        results['unit'] = run_unit_tests(args)
    else:
        results['unit'] = False
        print("⏭️  Skipping unit tests due to previous failures")
    
    # Run integration tests
    if results['unit'] and not args.unit_only:
        results['integration'] = run_integration_tests()
    else:
        results['integration'] = True if args.unit_only else False
        if args.unit_only:
            print("⏭️  Skipping integration tests (unit only mode)")
        else:
            print("⏭️  Skipping integration tests due to previous failures")
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    for test_type, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{test_type.upper():15} {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n💥 Some tests failed!")
        return 1


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="GLaSSIST Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tests.py                    # Run all tests
  python run_tests.py --unit-only        # Run only unit tests
  python run_tests.py --integration-only # Run only integration tests
  python run_tests.py --coverage         # Run with coverage report
  python run_tests.py --parallel         # Run tests in parallel
  python run_tests.py --html             # Generate HTML report
  python run_tests.py --test-file test_utils.py  # Run specific test file
        """
    )
    
    parser.add_argument(
        '--unit-only',
        action='store_true',
        help='Run only unit tests'
    )
    
    parser.add_argument(
        '--integration-only',
        action='store_true',
        help='Run only integration tests'
    )
    
    parser.add_argument(
        '--coverage',
        action='store_true',
        help='Generate coverage report'
    )
    
    parser.add_argument(
        '--parallel',
        action='store_true',
        help='Run tests in parallel'
    )
    
    parser.add_argument(
        '--html',
        action='store_true',
        help='Generate HTML test report'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    parser.add_argument(
        '--skip-install',
        action='store_true',
        help='Skip installing test dependencies'
    )
    
    parser.add_argument(
        '--skip-syntax',
        action='store_true',
        help='Skip syntax check'
    )
    
    parser.add_argument(
        '--test-file',
        help='Run specific test file'
    )
    
    args = parser.parse_args()
    
    # Change to project root directory
    project_root = os.path.dirname(os.path.dirname(__file__))
    os.chdir(project_root)
    
    # Run tests
    exit_code = run_all_tests(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()