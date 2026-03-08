"""
Utility functions for UbuCustom.

Provides common utilities for command execution, logging, validation,
and other helper functions used throughout the package.
"""

import os
import sys
import shutil
import subprocess
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from functools import wraps
import time


# Default logging configuration
DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DEFAULT_LOG_LEVEL = logging.INFO


def setup_logging(level: int = DEFAULT_LOG_LEVEL, 
                  format_str: str = DEFAULT_LOG_FORMAT,
                  log_file: Optional[str] = None) -> logging.Logger:
    """
    Set up logging configuration.
    
    Args:
        level: Logging level
        format_str: Log message format
        log_file: Optional file path for logging to file
        
    Returns:
        Logger instance
    """
    logger = logging.getLogger('ubucustom')
    logger.setLevel(level)
    
    # Remove existing handlers
    logger.handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(format_str)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(format_str)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


def run_command(cmd: List[str], 
                capture_output: bool = False,
                text: bool = True,
                check: bool = False,
                cwd: Optional[str] = None,
                env: Optional[Dict[str, str]] = None,
                timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """
    Run a shell command with proper error handling.
    
    Args:
        cmd: Command and arguments as a list
        capture_output: Whether to capture stdout/stderr
        text: Whether to return output as text (vs bytes)
        check: Whether to raise exception on non-zero exit
        cwd: Working directory for the command
        env: Environment variables for the command
        timeout: Timeout in seconds
        
    Returns:
        CompletedProcess instance
    """
    logger = logging.getLogger('ubucustom')
    logger.debug(f"Running command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=text,
            check=check,
            cwd=cwd,
            env=env,
            timeout=timeout
        )
        
        if result.returncode != 0 and not check:
            logger.warning(f"Command failed with code {result.returncode}: {' '.join(cmd)}")
            if capture_output and result.stderr:
                logger.debug(f"stderr: {result.stderr}")
        
        return result
        
    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out after {timeout}s: {' '.join(cmd)}")
        raise
    except Exception as e:
        logger.error(f"Failed to run command {' '.join(cmd)}: {e}")
        raise


def check_dependencies(dependencies: List[str]) -> bool:
    """
    Check if required dependencies are installed.
    
    Args:
        dependencies: List of command names to check
        
    Returns:
        True if all dependencies are available, False otherwise
    """
    logger = logging.getLogger('ubucustom')
    missing = []
    
    for dep in dependencies:
        if shutil.which(dep) is None:
            missing.append(dep)
    
    if missing:
        logger.error(f"Missing dependencies: {', '.join(missing)}")
        logger.error("Please install the missing packages and try again.")
        return False
    
    return True


def check_root() -> bool:
    """
    Check if running as root.
    
    Returns:
        True if running as root, False otherwise
    """
    return os.geteuid() == 0


def require_root() -> None:
    """
    Check if running as root and exit if not.
    """
    if not check_root():
        logger = logging.getLogger('ubucustom')
        logger.error("This operation requires root privileges. Please run with sudo.")
        sys.exit(1)


def get_file_size(path: str) -> int:
    """
    Get the size of a file in bytes.
    
    Args:
        path: Path to the file
        
    Returns:
        File size in bytes
    """
    return Path(path).stat().st_size


def format_size(size_bytes: int) -> str:
    """
    Format byte size to human-readable string.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Human-readable size string (e.g., "1.5 GB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def ensure_dir(path: str) -> Path:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        path: Path to the directory
        
    Returns:
        Path object for the directory
    """
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def safe_remove(path: str) -> bool:
    """
    Safely remove a file or directory.
    
    Args:
        path: Path to remove
        
    Returns:
        True if successful or path doesn't exist, False otherwise
    """
    try:
        file_path = Path(path)
        if not file_path.exists():
            return True
        
        if file_path.is_file():
            file_path.unlink()
        elif file_path.is_dir():
            shutil.rmtree(file_path)
        
        return True
        
    except Exception as e:
        logger = logging.getLogger('ubucustom')
        logger.error(f"Failed to remove {path}: {e}")
        return False


def copy_tree(src: str, dst: str, symlinks: bool = False) -> bool:
    """
    Copy a directory tree.
    
    Args:
        src: Source directory
        dst: Destination directory
        symlinks: Whether to copy symlinks as symlinks
        
    Returns:
        True if successful, False otherwise
    """
    try:
        if Path(dst).exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, symlinks=symlinks)
        return True
    except Exception as e:
        logger = logging.getLogger('ubucustom')
        logger.error(f"Failed to copy tree from {src} to {dst}: {e}")
        return False


def find_files(directory: str, pattern: str = '*') -> List[Path]:
    """
    Find files matching a pattern in a directory.
    
    Args:
        directory: Directory to search
        pattern: Glob pattern to match
        
    Returns:
        List of matching Path objects
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        return []
    
    return list(dir_path.rglob(pattern))


def get_disk_usage(path: str) -> Tuple[int, int, int]:
    """
    Get disk usage statistics.
    
    Args:
        path: Path to check
        
    Returns:
        Tuple of (total, used, free) in bytes
    """
    stat = shutil.disk_usage(path)
    return stat.total, stat.used, stat.free


def validate_iso(path: str) -> bool:
    """
    Validate that a file is a valid ISO image.
    
    Args:
        path: Path to the file
        
    Returns:
        True if valid ISO, False otherwise
    """
    file_path = Path(path)
    
    if not file_path.exists():
        return False
    
    if not file_path.is_file():
        return False
    
    # Check file extension
    if file_path.suffix.lower() not in ['.iso', '.img']:
        # Check file magic number
        try:
            with open(file_path, 'rb') as f:
                magic = f.read(5)
                # ISO 9660 magic number
                if magic == b'CD001':
                    return True
        except Exception:
            pass
        return False
    
    return True


def get_iso_info(path: str) -> Dict[str, Any]:
    """
    Get information about an ISO file.
    
    Args:
        path: Path to the ISO file
        
    Returns:
        Dictionary with ISO information
    """
    info = {
        'path': path,
        'size': 0,
        'size_human': '',
        'valid': False,
        'volume_id': '',
        'publisher': '',
        'creation_date': ''
    }
    
    file_path = Path(path)
    if not file_path.exists():
        return info
    
    info['size'] = file_path.stat().st_size
    info['size_human'] = format_size(info['size'])
    info['valid'] = validate_iso(path)
    
    # Try to get more info using isoinfo
    if shutil.which('isoinfo'):
        try:
            result = run_command(['isoinfo', '-d', '-i', path], capture_output=True)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Volume id:' in line:
                        info['volume_id'] = line.split(':', 1)[1].strip()
                    elif 'Publisher id:' in line:
                        info['publisher'] = line.split(':', 1)[1].strip()
                    elif 'Creation Date:' in line:
                        info['creation_date'] = line.split(':', 1)[1].strip()
        except Exception:
            pass
    
    return info


def retry_on_failure(max_attempts: int = 3, delay: float = 1.0):
    """
    Decorator to retry a function on failure.
    
    Args:
        max_attempts: Maximum number of attempts
        delay: Delay between attempts in seconds
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger('ubucustom')
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts:
                        raise
                    logger.warning(f"Attempt {attempt} failed: {e}. Retrying...")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator


def progress_bar(current: int, total: int, width: int = 50) -> str:
    """
    Create a text progress bar.
    
    Args:
        current: Current progress value
        total: Total value
        width: Width of the progress bar
        
    Returns:
        Progress bar string
    """
    if total == 0:
        return '[' + ' ' * width + '] 0%'
    
    percent = current / total
    filled = int(width * percent)
    bar = '=' * filled + ' ' * (width - filled)
    return f'[{bar}] {percent*100:.1f}%'


class Timer:
    """Simple timer context manager for performance measurement."""
    
    def __init__(self, name: str = "Operation"):
        self.name = name
        self.start_time = None
        self.end_time = None
        self.logger = logging.getLogger('ubucustom')
    
    def __enter__(self):
        self.start_time = time.time()
        self.logger.debug(f"Starting {self.name}...")
        return self
    
    def __exit__(self, *args):
        self.end_time = time.time()
        elapsed = self.end_time - self.start_time
        self.logger.debug(f"{self.name} completed in {elapsed:.2f}s")
    
    @property
    def elapsed(self) -> float:
        """Get elapsed time in seconds."""
        if self.end_time:
            return self.end_time - self.start_time
        if self.start_time:
            return time.time() - self.start_time
        return 0.0
