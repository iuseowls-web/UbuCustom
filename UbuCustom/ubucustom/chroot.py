"""
Chroot environment management module.

Provides functionality to enter, customize, and manage chroot environments
for the extracted squashfs filesystem.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Callable
import logging

from .utils import run_command, setup_logging

logger = logging.getLogger(__name__)


class ChrootEnvironment:
    """
    Manages a chroot environment for customizing the squashfs filesystem.
    
    Handles mounting/unmounting of virtual filesystems and execution of
    commands within the chroot.
    """
    
    def __init__(self, chroot_dir: str):
        """
        Initialize the chroot environment.
        
        Args:
            chroot_dir: Path to the directory to chroot into
        """
        self.chroot_dir = Path(chroot_dir).resolve()
        self.mounted = False
        self.mount_points: List[Path] = []
        
        setup_logging()
        
    def _mount_virtual_filesystems(self) -> bool:
        """
        Mount virtual filesystems needed for chroot operation.
        
        Returns:
            True if successful, False otherwise
        """
        logger.info("Mounting virtual filesystems...")
        
        mounts = [
            ('proc', '/proc', 'proc'),
            ('sysfs', '/sys', 'sysfs'),
            ('udev', '/dev', 'devtmpfs'),
            ('devpts', '/dev/pts', 'devpts'),
            ('tmpfs', '/run', 'tmpfs'),
        ]
        
        for fs_type, mount_point, fs_name in mounts:
            target = self.chroot_dir / mount_point.lstrip('/')
            target.mkdir(parents=True, exist_ok=True)
            
            # Check if already mounted
            if self._is_mounted(target):
                logger.debug(f"{target} already mounted")
                continue
            
            result = run_command(['mount', '-t', fs_name, fs_type, str(target)])
            
            if result.returncode != 0:
                logger.error(f"Failed to mount {fs_name} at {target}")
                self._unmount_virtual_filesystems()
                return False
            
            self.mount_points.append(target)
            logger.debug(f"Mounted {fs_name} at {target}")
        
        # Mount special devices
        dev_dir = self.chroot_dir / 'dev'
        for device in ['null', 'zero', 'random', 'urandom', 'tty']:
            src = Path('/') / 'dev' / device
            dst = dev_dir / device
            if src.exists() and not dst.exists():
                run_command(['cp', '-a', str(src), str(dst)])
        
        self.mounted = True
        logger.info("Virtual filesystems mounted successfully")
        return True
    
    def _unmount_virtual_filesystems(self) -> None:
        """Unmount all virtual filesystems."""
        logger.info("Unmounting virtual filesystems...")
        
        # Unmount in reverse order
        for mount_point in reversed(self.mount_points):
            if self._is_mounted(mount_point):
                result = run_command(['umount', '-l', str(mount_point)])
                if result.returncode != 0:
                    logger.warning(f"Failed to unmount {mount_point}")
                else:
                    logger.debug(f"Unmounted {mount_point}")
        
        self.mount_points = []
        self.mounted = False
        logger.info("Virtual filesystems unmounted")
    
    def _is_mounted(self, path: Path) -> bool:
        """Check if a path is currently mounted."""
        try:
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    if str(path) in line:
                        return True
            return False
        except Exception:
            return False
    
    def _copy_dns_config(self) -> None:
        """Copy DNS configuration into chroot for network access."""
        resolv_src = Path('/etc/resolv.conf')
        resolv_dst = self.chroot_dir / 'etc' / 'resolv.conf'
        
        if resolv_src.exists():
            resolv_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(resolv_src, resolv_dst)
            logger.debug("Copied DNS configuration")
    
    def _copy_host_config(self) -> None:
        """Copy host configuration files into chroot."""
        # Copy hosts file
        hosts_src = Path('/etc/hosts')
        hosts_dst = self.chroot_dir / 'etc' / 'hosts'
        if hosts_src.exists():
            shutil.copy2(hosts_src, hosts_dst)
        
        # Copy hostname
        hostname_src = Path('/etc/hostname')
        hostname_dst = self.chroot_dir / 'etc' / 'hostname'
        if hostname_src.exists():
            shutil.copy2(hostname_src, hostname_dst)
    
    def enter_chroot(self, command: Optional[List[str]] = None) -> int:
        """
        Enter the chroot environment.
        
        Args:
            command: Optional command to run in chroot. If None, starts a shell.
            
        Returns:
            Exit code from the chroot command
        """
        if not self.chroot_dir.exists():
            logger.error(f"Chroot directory does not exist: {self.chroot_dir}")
            return 1
        
        # Mount virtual filesystems
        if not self._mount_virtual_filesystems():
            return 1
        
        # Copy configuration files
        self._copy_dns_config()
        self._copy_host_config()
        
        try:
            # Prepare the command
            if command:
                cmd = ['chroot', str(self.chroot_dir)] + command
            else:
                # Start an interactive shell
                shell = os.environ.get('SHELL', '/bin/bash')
                cmd = ['chroot', str(self.chroot_dir), shell]
            
            logger.info(f"Entering chroot: {' '.join(cmd)}")
            
            # Execute the command
            result = subprocess.run(cmd)
            return result.returncode
            
        except Exception as e:
            logger.error(f"Error in chroot: {e}")
            return 1
        finally:
            self._unmount_virtual_filesystems()
    
    def execute(self, command: List[str], capture_output: bool = False) -> subprocess.CompletedProcess:
        """
        Execute a command in the chroot environment.
        
        Args:
            command: Command and arguments to execute
            capture_output: Whether to capture stdout/stderr
            
        Returns:
            CompletedProcess instance with returncode and output
        """
        if not self.mounted:
            if not self._mount_virtual_filesystems():
                raise RuntimeError("Failed to mount virtual filesystems")
        
        try:
            cmd = ['chroot', str(self.chroot_dir)] + command
            logger.debug(f"Executing in chroot: {' '.join(cmd)}")
            
            if capture_output:
                result = subprocess.run(cmd, capture_output=True, text=True)
            else:
                result = subprocess.run(cmd, capture_output=False)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to execute command in chroot: {e}")
            raise
    
    def install_packages(self, packages: List[str]) -> bool:
        """
        Install packages in the chroot environment.
        
        Args:
            packages: List of package names to install
            
        Returns:
            True if successful, False otherwise
        """
        if not packages:
            return True
        
        logger.info(f"Installing packages: {', '.join(packages)}")
        
        try:
            # Update package list
            self.execute(['apt-get', 'update'])
            
            # Install packages
            cmd = ['apt-get', 'install', '-y'] + packages
            result = self.execute(cmd)
            
            if result.returncode == 0:
                logger.info("Packages installed successfully")
                return True
            else:
                logger.error("Failed to install packages")
                return False
                
        except Exception as e:
            logger.error(f"Error installing packages: {e}")
            return False
    
    def remove_packages(self, packages: List[str]) -> bool:
        """
        Remove packages from the chroot environment.
        
        Args:
            packages: List of package names to remove
            
        Returns:
            True if successful, False otherwise
        """
        if not packages:
            return True
        
        logger.info(f"Removing packages: {', '.join(packages)}")
        
        try:
            cmd = ['apt-get', 'remove', '-y'] + packages
            result = self.execute(cmd)
            
            if result.returncode == 0:
                logger.info("Packages removed successfully")
                return True
            else:
                logger.error("Failed to remove packages")
                return False
                
        except Exception as e:
            logger.error(f"Error removing packages: {e}")
            return False
    
    def add_repository(self, repo_line: str) -> bool:
        """
        Add a PPA or repository to the chroot.
        
        Args:
            repo_line: Repository line to add
            
        Returns:
            True if successful, False otherwise
        """
        sources_dir = self.chroot_dir / 'etc' / 'apt' / 'sources.list.d'
        sources_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Create a new sources file
            repo_name = repo_line.split(':')[0].replace('/', '-')
            sources_file = sources_dir / f'{repo_name}.list'
            sources_file.write_text(repo_line + '\n')
            
            logger.info(f"Added repository: {repo_line}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add repository: {e}")
            return False
    
    def run_script(self, script_path: str) -> bool:
        """
        Run a script inside the chroot environment.
        
        Args:
            script_path: Path to the script to run
            
        Returns:
            True if successful, False otherwise
        """
        script = Path(script_path)
        
        if not script.exists():
            logger.error(f"Script not found: {script}")
            return False
        
        try:
            # Copy script to chroot
            chroot_script = self.chroot_dir / 'tmp' / 'ubucustom_script.sh'
            chroot_script.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(script, chroot_script)
            chroot_script.chmod(0o755)
            
            # Run the script
            result = self.execute(['/tmp/ubucustom_script.sh'])
            
            # Clean up
            if chroot_script.exists():
                chroot_script.unlink()
            
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Error running script: {e}")
            return False
    
    def cleanup(self) -> None:
        """Clean up the chroot environment."""
        if self.mounted:
            self._unmount_virtual_filesystems()
        
        # Clean up temporary files
        tmp_dir = self.chroot_dir / 'tmp'
        if tmp_dir.exists():
            for item in tmp_dir.iterdir():
                if item.name.startswith('ubucustom'):
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
        
        logger.info("Chroot environment cleaned up")


def is_running_in_chroot() -> bool:
    """Check if currently running inside a chroot environment."""
    try:
        stat_root = os.stat('/')
        stat_init = os.stat('/proc/1/root/.')
        return stat_root.st_ino != stat_init.st_ino
    except Exception:
        return False
