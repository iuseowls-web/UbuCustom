"""
Core module for ISO manipulation operations.

Provides the ISOBuilder class for extracting, customizing, and rebuilding Ubuntu ISOs.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, List, Dict
import logging

from .utils import run_command, check_dependencies, setup_logging

logger = logging.getLogger(__name__)


class ISOBuilder:
    """
    Main class for building custom Ubuntu ISOs.
    
    Handles ISO extraction, filesystem manipulation, and ISO rebuilding.
    """
    
    def __init__(self, work_dir: str):
        """
        Initialize ISOBuilder with a working directory.
        
        Args:
            work_dir: Path to the working directory for ISO operations
        """
        self.work_dir = Path(work_dir).resolve()
        self.iso_dir = self.work_dir / "iso"
        self.squashfs_dir = self.work_dir / "squashfs"
        self.custom_dir = self.work_dir / "custom"
        self.original_iso: Optional[Path] = None
        
        setup_logging()
        
    def create_work_structure(self) -> None:
        """Create the working directory structure."""
        logger.info(f"Creating working directory structure at {self.work_dir}")
        
        # Create directories
        self.iso_dir.mkdir(parents=True, exist_ok=True)
        self.squashfs_dir.mkdir(parents=True, exist_ok=True)
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Working directory structure created")
    
    def extract_iso(self, iso_path: str) -> bool:
        """
        Extract an ISO file to the working directory.
        
        Args:
            iso_path: Path to the source ISO file
            
        Returns:
            True if successful, False otherwise
        """
        iso_file = Path(iso_path).resolve()
        
        if not iso_file.exists():
            logger.error(f"ISO file not found: {iso_file}")
            return False
        
        self.original_iso = iso_file
        logger.info(f"Extracting ISO: {iso_file}")
        
        # Check dependencies
        if not check_dependencies(['xorriso', 'rsync']):
            return False
        
        try:
            # Create work structure
            self.create_work_structure()
            
            # Mount the ISO using xorriso
            mount_point = tempfile.mkdtemp(prefix="ubucustom_mount_")
            
            try:
                # Extract ISO contents using xorrisosfs
                logger.info("Extracting ISO contents...")
                result = run_command([
                    'xorriso', '-osirrox', 'on', '-indev', str(iso_file),
                    '-extract', '/', str(self.iso_dir)
                ])
                
                if result.returncode != 0:
                    # Fallback: use 7z or mount
                    result = run_command([
                        '7z', 'x', str(iso_file), f'-o{self.iso_dir}', '-y'
                    ])
                    
                    if result.returncode != 0:
                        # Final fallback: mount and copy
                        result = run_command([
                            'mount', '-o', 'loop,ro', str(iso_file), mount_point
                        ])
                        if result.returncode == 0:
                            run_command(['rsync', '-a', f'{mount_point}/', str(self.iso_dir)])
                            run_command(['umount', mount_point])
                
                # Find and extract squashfs
                self._extract_squashfs()
                
                logger.info("ISO extraction completed successfully")
                return True
                
            finally:
                if os.path.exists(mount_point):
                    shutil.rmtree(mount_point)
                    
        except Exception as e:
            logger.error(f"Failed to extract ISO: {e}")
            return False
    
    def _extract_squashfs(self) -> bool:
        """
        Extract the squashfs filesystem from the ISO.
        
        Returns:
            True if successful, False otherwise
        """
        logger.info("Looking for squashfs filesystem...")
        
        # Common locations for squashfs in Ubuntu ISOs
        possible_paths = [
            self.iso_dir / "casper" / "filesystem.squashfs",
            self.iso_dir / "live" / "filesystem.squashfs",
            self.iso_dir / "casper" / "squashfs",
        ]
        
        squashfs_file = None
        for path in possible_paths:
            if path.exists():
                squashfs_file = path
                break
        
        if not squashfs_file:
            # Search for any squashfs file
            for root, dirs, files in os.walk(self.iso_dir):
                for file in files:
                    if file.endswith('.squashfs') or file == 'squashfs':
                        squashfs_file = Path(root) / file
                        break
                if squashfs_file:
                    break
        
        if not squashfs_file:
            logger.error("No squashfs filesystem found in ISO")
            return False
        
        logger.info(f"Found squashfs: {squashfs_file}")
        
        # Extract squashfs
        logger.info("Extracting squashfs filesystem...")
        result = run_command([
            'unsquashfs', '-f', '-d', str(self.squashfs_dir), str(squashfs_file)
        ])
        
        if result.returncode != 0:
            logger.error("Failed to extract squashfs")
            return False
        
        # Backup original squashfs
        backup_path = squashfs_file.with_suffix('.squashfs.original')
        shutil.copy2(squashfs_file, backup_path)
        
        logger.info("Squashfs extracted successfully")
        return True
    
    def rebuild_squashfs(self, compression: str = "xz") -> bool:
        """
        Rebuild the squashfs filesystem from the customized directory.
        
        Args:
            compression: Compression algorithm (xz, gzip, lzo, lz4, zstd)
            
        Returns:
            True if successful, False otherwise
        """
        logger.info("Rebuilding squashfs filesystem...")
        
        # Find original squashfs location
        squashfs_dest = None
        possible_paths = [
            self.iso_dir / "casper" / "filesystem.squashfs",
            self.iso_dir / "live" / "filesystem.squashfs",
        ]
        
        for path in possible_paths:
            if path.exists() or path.with_suffix('.squashfs.original').exists():
                squashfs_dest = path
                break
        
        if not squashfs_dest:
            logger.error("Could not find squashfs destination")
            return False
        
        # Remove old squashfs
        if squashfs_dest.exists():
            squashfs_dest.unlink()
        
        # Build new squashfs
        comp_args = {
            'xz': ['-comp', 'xz', '-Xbcj', 'x86'],
            'gzip': ['-comp', 'gzip'],
            'lzo': ['-comp', 'lzo'],
            'lz4': ['-comp', 'lz4'],
            'zstd': ['-comp', 'zstd'],
        }
        
        cmd = [
            'mksquashfs', str(self.squashfs_dir), str(squashfs_dest),
            '-noappend', '-wildcards', '-no-recovery'
        ]
        cmd.extend(comp_args.get(compression, ['-comp', 'xz']))
        
        result = run_command(cmd)
        
        if result.returncode != 0:
            logger.error("Failed to rebuild squashfs")
            return False
        
        logger.info("Squashfs rebuilt successfully")
        return True
    
    def update_manifest(self) -> bool:
        """
        Update the filesystem manifest to reflect current packages.
        
        Returns:
            True if successful, False otherwise
        """
        logger.info("Updating filesystem manifest...")
        
        manifest_paths = [
            self.iso_dir / "casper" / "filesystem.manifest",
            self.iso_dir / "live" / "filesystem.manifest",
        ]
        
        manifest_file = None
        for path in manifest_paths:
            if path.exists() or path.with_suffix('.manifest.original').exists():
                manifest_file = path
                break
        
        if not manifest_file:
            logger.warning("No manifest file found, skipping")
            return True
        
        try:
            # Generate new manifest from chroot
            dpkg_path = self.squashfs_dir / "usr" / "bin" / "dpkg-query"
            if dpkg_path.exists():
                result = run_command([
                    'chroot', str(self.squashfs_dir),
                    'dpkg-query', '-W', '--showformat=${Package} ${Version}\n'
                ], capture_output=True)
                
                if result.returncode == 0:
                    manifest_file.write_text(result.stdout)
                    logger.info("Manifest updated successfully")
                    return True
            
            logger.warning("Could not update manifest")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update manifest: {e}")
            return False
    
    def calculate_checksums(self) -> bool:
        """
        Calculate MD5 checksums for all files in the ISO.
        
        Returns:
            True if successful, False otherwise
        """
        logger.info("Calculating checksums...")
        
        md5sum_file = self.iso_dir / "md5sum.txt"
        
        try:
            # Generate MD5 checksums
            files = []
            for item in self.iso_dir.rglob('*'):
                if item.is_file() and item.name != 'md5sum.txt':
                    files.append(item.relative_to(self.iso_dir))
            
            if not files:
                logger.warning("No files to checksum")
                return True
            
            # Write file list and generate checksums
            checksums = []
            for file in files:
                file_path = self.iso_dir / file
                result = run_command(['md5sum', str(file_path)], capture_output=True)
                if result.returncode == 0:
                    # Adjust path in checksum output
                    checksum_line = result.stdout.strip()
                    checksums.append(checksum_line)
            
            md5sum_file.write_text('\n'.join(checksums) + '\n')
            logger.info("Checksums calculated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to calculate checksums: {e}")
            return False
    
    def rebuild_iso(self, output_path: str, volume_id: Optional[str] = None) -> bool:
        """
        Rebuild the ISO file from the working directory.
        
        Args:
            output_path: Path for the output ISO file
            volume_id: Volume ID for the ISO (default: auto-generated)
            
        Returns:
            True if successful, False otherwise
        """
        output_file = Path(output_path).resolve()
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Rebuilding ISO: {output_file}")
        
        # Rebuild squashfs first
        if not self.rebuild_squashfs():
            return False
        
        # Update manifest
        self.update_manifest()
        
        # Calculate checksums
        self.calculate_checksums()
        
        # Determine volume ID
        if not volume_id:
            volume_id = "UbuCustom"
        
        # Build ISO using xorriso
        logger.info("Creating ISO image...")
        
        cmd = [
            'xorriso', '-as', 'mkisofs',
            '-r', '-V', volume_id,
            '-o', str(output_file),
            '-J', '-J', '-joliet-long',
            '-cache-inodes',
            '-isohybrid-mbr', str(self.iso_dir / 'isolinux' / 'isohdpfx.bin') 
            if (self.iso_dir / 'isolinux' / 'isohdpfx.bin').exists() else None,
            '-b', 'isolinux/isolinux.bin',
            '-c', 'isolinux/boot.cat',
            '-boot-load-size', '4',
            '-boot-info-table',
            '-no-emul-boot',
            '-eltorito-alt-boot',
            '-e', 'boot/grub/efi.img',
            '-no-emul-boot',
            '-isohybrid-gpt-basdat',
            str(self.iso_dir)
        ]
        
        # Remove None values
        cmd = [arg for arg in cmd if arg is not None]
        
        # If isohdpfx.bin doesn't exist, use simpler command
        if not (self.iso_dir / 'isolinux' / 'isohdpfx.bin').exists():
            cmd = [
                'xorriso', '-as', 'mkisofs',
                '-r', '-V', volume_id,
                '-o', str(output_file),
                '-J', '-joliet-long',
                str(self.iso_dir)
            ]
        
        result = run_command(cmd)
        
        if result.returncode != 0:
            logger.error("Failed to create ISO")
            return False
        
        # Make ISO hybrid (bootable from USB)
        run_command(['isohybrid', str(output_file)])
        
        logger.info(f"ISO created successfully: {output_file}")
        return True
    
    def clean(self) -> None:
        """Clean up the working directory."""
        logger.info(f"Cleaning up {self.work_dir}")
        
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir)
            logger.info("Working directory cleaned")
    
    def get_squashfs_dir(self) -> Path:
        """Get the path to the squashfs directory for customization."""
        return self.squashfs_dir
    
    def get_iso_dir(self) -> Path:
        """Get the path to the ISO directory."""
        return self.iso_dir
