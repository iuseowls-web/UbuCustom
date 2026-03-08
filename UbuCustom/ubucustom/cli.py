#!/usr/bin/env python3
"""
Command-line interface for UbuCustom.

Provides commands for extracting ISOs, managing chroot environments,
and building custom Ubuntu ISO images.
"""

import argparse
import logging
import shutil
import sys
import os
import textwrap
from pathlib import Path
from typing import Optional, List

from .core import ISOBuilder
from .chroot import ChrootEnvironment
from .utils import (
    setup_logging, check_dependencies, require_root,
    validate_iso, get_iso_info, format_size
)


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog='ubucustom',
        description='UbuCustom - Custom Ubuntu ISO Creator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent('''
            Examples:
              # Extract an ISO
              ubucustom extract ubuntu.iso ./workdir
              
              # Enter chroot for customization
              sudo ubucustom chroot ./workdir
              
              # Install packages in chroot
              sudo ubucustom exec ./workdir -- apt-get install -y vim
              
              # Build custom ISO
              ubucustom build ./workdir ./custom-ubuntu.iso
              
              # Run wizard mode
              ubucustom wizard
              
              # Clean up working directory
              ubucustom clean ./workdir
        ''')
    )
    
    parser.add_argument(
        '-v', '--version',
        action='version',
        version='%(prog)s 1.0.0'
    )
    
    parser.add_argument(
        '-d', '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Extract command
    extract_parser = subparsers.add_parser(
        'extract',
        help='Extract an ISO file to working directory'
    )
    extract_parser.add_argument(
        'iso',
        help='Path to the source ISO file'
    )
    extract_parser.add_argument(
        'workdir',
        help='Path to the working directory'
    )
    
    # Chroot command
    chroot_parser = subparsers.add_parser(
        'chroot',
        help='Enter chroot environment for customization'
    )
    chroot_parser.add_argument(
        'workdir',
        help='Path to the working directory'
    )
    chroot_parser.add_argument(
        '--command', '-c',
        nargs=argparse.REMAINDER,
        help='Command to run in chroot (default: interactive shell)'
    )
    
    # Exec command
    exec_parser = subparsers.add_parser(
        'exec',
        help='Execute a command in the chroot environment'
    )
    exec_parser.add_argument(
        'workdir',
        help='Path to the working directory'
    )
    exec_parser.add_argument(
        'command',
        nargs=argparse.REMAINDER,
        help='Command to execute'
    )
    
    # Install command
    install_parser = subparsers.add_parser(
        'install',
        help='Install packages in the chroot environment'
    )
    install_parser.add_argument(
        'workdir',
        help='Path to the working directory'
    )
    install_parser.add_argument(
        'packages',
        nargs='+',
        help='Packages to install'
    )
    
    # Remove command
    remove_parser = subparsers.add_parser(
        'remove',
        help='Remove packages from the chroot environment'
    )
    remove_parser.add_argument(
        'workdir',
        help='Path to the working directory'
    )
    remove_parser.add_argument(
        'packages',
        nargs='+',
        help='Packages to remove'
    )
    
    # Build command
    build_parser = subparsers.add_parser(
        'build',
        help='Build custom ISO from working directory'
    )
    build_parser.add_argument(
        'workdir',
        help='Path to the working directory'
    )
    build_parser.add_argument(
        'output',
        help='Path for the output ISO file'
    )
    build_parser.add_argument(
        '--volume-id', '-V',
        default='UbuCustom',
        help='Volume ID for the ISO (default: UbuCustom)'
    )
    build_parser.add_argument(
        '--compression',
        default='xz',
        choices=['xz', 'gzip', 'lzo', 'lz4', 'zstd'],
        help='Squashfs compression algorithm (default: xz)'
    )
    
    # Info command
    info_parser = subparsers.add_parser(
        'info',
        help='Show information about an ISO file'
    )
    info_parser.add_argument(
        'iso',
        help='Path to the ISO file'
    )
    
    # Clean command
    clean_parser = subparsers.add_parser(
        'clean',
        help='Clean up working directory'
    )
    clean_parser.add_argument(
        'workdir',
        help='Path to the working directory'
    )
    clean_parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Skip confirmation'
    )
    
    # Wizard command
    wizard_parser = subparsers.add_parser(
        'wizard',
        help='Run interactive wizard mode'
    )
    wizard_parser.add_argument(
        '--workdir',
        default='./ubucustom-work',
        help='Default working directory'
    )
    
    # Check command
    check_parser = subparsers.add_parser(
        'check',
        help='Check dependencies and system readiness'
    )
    
    return parser


def cmd_extract(args) -> int:
    """Handle the extract command."""
    # Validate ISO
    if not validate_iso(args.iso):
        print(f"Error: Invalid or missing ISO file: {args.iso}", file=sys.stderr)
        return 1
    
    # Show ISO info
    info = get_iso_info(args.iso)
    print(f"ISO: {info['path']}")
    print(f"Size: {info['size_human']}")
    if info['volume_id']:
        print(f"Volume ID: {info['volume_id']}")
    print()
    
    # Check dependencies
    deps = ['xorriso', 'unsquashfs', 'mksquashfs', 'rsync']
    if not check_dependencies(deps):
        return 1
    
    # Extract
    builder = ISOBuilder(args.workdir)
    if builder.extract_iso(args.iso):
        print(f"\nISO extracted successfully to: {args.workdir}")
        print(f"Squashfs directory: {builder.get_squashfs_dir()}")
        return 0
    else:
        print("\nError: Failed to extract ISO", file=sys.stderr)
        return 1


def cmd_chroot(args) -> int:
    """Handle the chroot command."""
    require_root()
    
    workdir = Path(args.workdir)
    squashfs_dir = workdir / 'squashfs'
    
    if not squashfs_dir.exists():
        print(f"Error: Squashfs directory not found: {squashfs_dir}", file=sys.stderr)
        print("Did you run 'extract' first?", file=sys.stderr)
        return 1
    
    chroot = ChrootEnvironment(str(squashfs_dir))
    
    command = args.command if args.command else None
    exit_code = chroot.enter_chroot(command)
    
    return exit_code


def cmd_exec(args) -> int:
    """Handle the exec command."""
    require_root()
    
    workdir = Path(args.workdir)
    squashfs_dir = workdir / 'squashfs'
    
    if not squashfs_dir.exists():
        print(f"Error: Squashfs directory not found: {squashfs_dir}", file=sys.stderr)
        return 1
    
    if not args.command:
        print("Error: No command specified", file=sys.stderr)
        return 1
    
    chroot = ChrootEnvironment(str(squashfs_dir))
    
    try:
        result = chroot.execute(args.command)
        return result.returncode
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        chroot.cleanup()


def cmd_install(args) -> int:
    """Handle the install command."""
    require_root()
    
    workdir = Path(args.workdir)
    squashfs_dir = workdir / 'squashfs'
    
    if not squashfs_dir.exists():
        print(f"Error: Squashfs directory not found: {squashfs_dir}", file=sys.stderr)
        return 1
    
    chroot = ChrootEnvironment(str(squashfs_dir))
    
    try:
        if chroot.install_packages(args.packages):
            print(f"Packages installed successfully: {', '.join(args.packages)}")
            return 0
        else:
            print("Error: Failed to install packages", file=sys.stderr)
            return 1
    finally:
        chroot.cleanup()


def cmd_remove(args) -> int:
    """Handle the remove command."""
    require_root()
    
    workdir = Path(args.workdir)
    squashfs_dir = workdir / 'squashfs'
    
    if not squashfs_dir.exists():
        print(f"Error: Squashfs directory not found: {squashfs_dir}", file=sys.stderr)
        return 1
    
    chroot = ChrootEnvironment(str(squashfs_dir))
    
    try:
        if chroot.remove_packages(args.packages):
            print(f"Packages removed successfully: {', '.join(args.packages)}")
            return 0
        else:
            print("Error: Failed to remove packages", file=sys.stderr)
            return 1
    finally:
        chroot.cleanup()


def cmd_build(args) -> int:
    """Handle the build command."""
    workdir = Path(args.workdir)
    
    if not workdir.exists():
        print(f"Error: Working directory not found: {workdir}", file=sys.stderr)
        return 1
    
    deps = ['xorriso', 'mksquashfs', 'isohybrid']
    if not check_dependencies(deps):
        return 1
    
    builder = ISOBuilder(args.workdir)
    
    if builder.rebuild_iso(args.output, args.volume_id):
        print(f"\nCustom ISO created successfully: {args.output}")
        
        # Show output file info
        output_path = Path(args.output)
        if output_path.exists():
            size = format_size(output_path.stat().st_size)
            print(f"Size: {size}")
        return 0
    else:
        print("\nError: Failed to build ISO", file=sys.stderr)
        return 1


def cmd_info(args) -> int:
    """Handle the info command."""
    if not validate_iso(args.iso):
        print(f"Error: Invalid or missing ISO file: {args.iso}", file=sys.stderr)
        return 1
    
    info = get_iso_info(args.iso)
    
    print("ISO Information:")
    print(f"  Path: {info['path']}")
    print(f"  Valid: {'Yes' if info['valid'] else 'No'}")
    print(f"  Size: {info['size_human']} ({info['size']:,} bytes)")
    
    if info['volume_id']:
        print(f"  Volume ID: {info['volume_id']}")
    if info['publisher']:
        print(f"  Publisher: {info['publisher']}")
    if info['creation_date']:
        print(f"  Creation Date: {info['creation_date']}")
    
    return 0


def cmd_clean(args) -> int:
    """Handle the clean command."""
    workdir = Path(args.workdir)
    
    if not workdir.exists():
        print(f"Working directory does not exist: {workdir}")
        return 0
    
    if not args.yes:
        response = input(f"Remove {workdir} and all its contents? [y/N] ")
        if response.lower() != 'y':
            print("Cancelled")
            return 0
    
    builder = ISOBuilder(args.workdir)
    builder.clean()
    print(f"Cleaned up: {workdir}")
    return 0


def cmd_wizard(args) -> int:
    """Run interactive wizard mode."""
    print("=" * 60)
    print("UbuCustom - Interactive Wizard")
    print("=" * 60)
    print()
    
    # Step 1: Select ISO
    print("Step 1: Select Ubuntu ISO")
    print("-" * 40)
    
    while True:
        iso_path = input("Enter path to Ubuntu ISO: ").strip()
        
        if not iso_path:
            print("Please enter a valid path.")
            continue
        
        if not validate_iso(iso_path):
            print(f"Invalid ISO file: {iso_path}")
            continue
        
        info = get_iso_info(iso_path)
        print(f"\nSelected: {info['path']}")
        print(f"Size: {info['size_human']}")
        if info['volume_id']:
            print(f"Volume ID: {info['volume_id']}")
        
        confirm = input("\nIs this correct? [Y/n] ").strip().lower()
        if confirm in ('', 'y', 'yes'):
            break
    
    print()
    
    # Step 2: Working directory
    print("Step 2: Working Directory")
    print("-" * 40)
    
    workdir = input(f"Enter working directory [{args.workdir}]: ").strip()
    if not workdir:
        workdir = args.workdir
    
    workdir = os.path.abspath(workdir)
    print(f"Working directory: {workdir}")
    
    if Path(workdir).exists():
        response = input("Directory exists. Remove it? [y/N] ").strip().lower()
        if response == 'y':
            import shutil
            shutil.rmtree(workdir)
    
    print()
    
    # Step 3: Extract ISO
    print("Step 3: Extracting ISO")
    print("-" * 40)
    
    deps = ['xorriso', 'unsquashfs', 'mksquashfs', 'rsync']
    if not check_dependencies(deps):
        print("\nPlease install missing dependencies and try again.")
        return 1
    
    builder = ISOBuilder(workdir)
    
    if not builder.extract_iso(iso_path):
        print("\nFailed to extract ISO.")
        return 1
    
    print("\nISO extracted successfully!")
    print(f"Squashfs directory: {builder.get_squashfs_dir()}")
    
    print()
    
    # Step 4: Customize
    print("Step 4: Customize")
    print("-" * 40)
    print("You can now customize the ISO by:")
    print(f"  1. Entering chroot: sudo ubucustom chroot {workdir}")
    print(f"  2. Installing packages: sudo ubucustom install {workdir} <packages>")
    print(f"  3. Running commands: sudo ubucustom exec {workdir} -- <command>")
    print()
    
    customize = input("Enter chroot now? [Y/n] ").strip().lower()
    if customize in ('', 'y', 'yes'):
        if os.geteuid() != 0:
            print("Root privileges required. Run: sudo ubucustom chroot {workdir}")
        else:
            chroot = ChrootEnvironment(str(builder.get_squashfs_dir()))
            chroot.enter_chroot()
    
    print()
    
    # Step 5: Build ISO
    print("Step 5: Build Custom ISO")
    print("-" * 40)
    
    build = input("Build custom ISO now? [Y/n] ").strip().lower()
    if build in ('', 'y', 'yes'):
        default_output = "./custom-ubuntu.iso"
        output = input(f"Output ISO path [{default_output}]: ").strip()
        if not output:
            output = default_output
        
        output = os.path.abspath(output)
        
        volume_id = input("Volume ID [UbuCustom]: ").strip()
        if not volume_id:
            volume_id = "UbuCustom"
        
        print("\nBuilding ISO...")
        
        if builder.rebuild_iso(output, volume_id):
            print(f"\nSuccess! Custom ISO created: {output}")
            
            output_path = Path(output)
            if output_path.exists():
                size = format_size(output_path.stat().st_size)
                print(f"Size: {size}")
        else:
            print("\nFailed to build ISO.")
            return 1
    
    print()
    print("=" * 60)
    print("Wizard completed!")
    print("=" * 60)
    
    return 0


def cmd_check(args) -> int:
    """Check dependencies and system readiness."""
    print("UbuCustom - System Check")
    print("=" * 40)
    
    # Check Python version
    print("\nPython Version:")
    print(f"  {sys.version}")
    
    # Check for required dependencies
    print("\nRequired Dependencies:")
    required = ['xorriso', 'unsquashfs', 'mksquashfs', 'isohybrid', 'rsync']
    
    all_found = True
    for dep in required:
        found = shutil.which(dep) is not None
        status = "✓" if found else "✗"
        print(f"  {status} {dep}")
        if not found:
            all_found = False
    
    # Check for optional dependencies
    print("\nOptional Dependencies:")
    optional = ['isoinfo', '7z', 'dpkg-query']
    
    for dep in optional:
        found = shutil.which(dep) is not None
        status = "✓" if found else "○"
        print(f"  {status} {dep}")
    
    # Check root privileges
    print("\nPrivileges:")
    if os.geteuid() == 0:
        print("  ✓ Running as root")
    else:
        print("  ○ Not running as root (required for chroot)")
    
    print()
    
    if all_found:
        print("All required dependencies are installed!")
        return 0
    else:
        print("Some required dependencies are missing.")
        print("Install them with: sudo apt-get install xorriso squashfs-tools grub-pc-bin")
        return 1


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for the CLI."""
    parser = create_parser()
    parsed_args = parser.parse_args(args)
    
    # Setup logging
    log_level = 'DEBUG' if parsed_args.debug else 'INFO'
    setup_logging(level=getattr(logging, log_level))
    
    # Dispatch to command handler
    if parsed_args.command == 'extract':
        return cmd_extract(parsed_args)
    elif parsed_args.command == 'chroot':
        return cmd_chroot(parsed_args)
    elif parsed_args.command == 'exec':
        return cmd_exec(parsed_args)
    elif parsed_args.command == 'install':
        return cmd_install(parsed_args)
    elif parsed_args.command == 'remove':
        return cmd_remove(parsed_args)
    elif parsed_args.command == 'build':
        return cmd_build(parsed_args)
    elif parsed_args.command == 'info':
        return cmd_info(parsed_args)
    elif parsed_args.command == 'clean':
        return cmd_clean(parsed_args)
    elif parsed_args.command == 'wizard':
        return cmd_wizard(parsed_args)
    elif parsed_args.command == 'check':
        return cmd_check(parsed_args)
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    import logging
    sys.exit(main())
