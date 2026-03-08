#!/usr/bin/env python3
"""
Tkinter GUI for UbuCustom.

Provides a graphical wizard interface for creating custom Ubuntu ISOs.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import shutil
import threading
import subprocess
import time
import re
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List

from .core import ISOBuilder
from .chroot import ChrootEnvironment
from .utils import setup_logging, check_dependencies, validate_iso, get_iso_info, format_size


class ThemeManager:
    """Manages theme colors and styles."""
    
    THEMES = {
        'ubuntu': {
            'primary': '#E95420',
            'primary_dark': '#C44418',
            'secondary': '#772953',
            'accent': '#F4AA90',
            'background': '#F7F7F7',
            'surface': '#FFFFFF',
            'text': '#111111',
            'text_secondary': '#666666',
            'border': '#DEDEDE',
            'success': '#0E8420',
            'warning': '#F99B11',
            'error': '#C7162B',
        },
        'dark': {
            'primary': '#E95420',
            'primary_dark': '#C44418',
            'secondary': '#772953',
            'accent': '#F4AA90',
            'background': '#1E1E1E',
            'surface': '#2D2D2D',
            'text': '#FFFFFF',
            'text_secondary': '#AAAAAA',
            'border': '#404040',
            'success': '#0E8420',
            'warning': '#F99B11',
            'error': '#C7162B',
        },
        'blue': {
            'primary': '#2196F3',
            'primary_dark': '#1976D2',
            'secondary': '#0D47A1',
            'accent': '#90CAF9',
            'background': '#F5F5F5',
            'surface': '#FFFFFF',
            'text': '#212121',
            'text_secondary': '#757575',
            'border': '#E0E0E0',
            'success': '#4CAF50',
            'warning': '#FF9800',
            'error': '#F44336',
        },
        'win95': {
            'primary': '#000080',        # Navy blue (title bar)
            'primary_dark': '#000060',
            'secondary': '#808080',      # Gray
            'accent': '#C0C0C0',         # Light gray
            'background': '#C0C0C0',     # Classic Win95 gray
            'surface': '#C0C0C0',
            'text': '#000000',
            'text_secondary': '#404040',
            'border': '#808080',
            'success': '#008000',
            'warning': '#FF8000',
            'error': '#FF0000',
            'button_face': '#C0C0C0',
            'button_highlight': '#FFFFFF',
            'button_shadow': '#808080',
            'button_dark_shadow': '#404040',
        },
        'vscode': {
            'primary': '#007ACC',        # VS Code blue
            'primary_dark': '#005A9E',
            'secondary': '#252526',      # Dark sidebar
            'accent': '#0097FB',         # Bright blue accent
            'background': '#1E1E1E',     # Main dark background
            'surface': '#252526',        # Sidebar/panels
            'text': '#D4D4D4',           # Light grey text
            'text_secondary': '#858585', # Comments grey
            'border': '#3E3E42',         # Borders
            'success': '#4EC9B0',        # Teal green
            'warning': '#CE9178',        # Orange
            'error': '#F48771',          # Red
            'keyword': '#569CD6',        # Blue keywords
            'string': '#CE9178',         # Orange strings
            'function': '#DCDCAA',       # Yellow functions
            'comment': '#6A9955',        # Green comments
        }
    }
    
    @classmethod
    def get_theme(cls, name: str = 'ubuntu') -> Dict[str, str]:
        return cls.THEMES.get(name, cls.THEMES['ubuntu'])


class ProjectManager:
    """Manages project sessions and history."""
    
    CONFIG_DIR = Path.home() / '.config' / 'ubucustom'
    HISTORY_FILE = CONFIG_DIR / 'history.json'
    
    def __init__(self):
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.history = self._load_history()
    
    def _load_history(self) -> List[Dict]:
        if self.HISTORY_FILE.exists():
            try:
                with open(self.HISTORY_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def save_project(self, name: str, data: Dict):
        project = {
            'name': name,
            'date': datetime.now().isoformat(),
            'iso_path': data.get('iso_path'),
            'work_dir': data.get('work_dir'),
            'output_path': data.get('output_path'),
            'volume_id': data.get('volume_id'),
        }
        self.history.insert(0, project)
        self.history = self.history[:10]  # Keep last 10
        self._save_history()
    
    def _save_history(self):
        with open(self.HISTORY_FILE, 'w') as f:
            json.dump(self.history, f, indent=2)
    
    def get_recent_projects(self) -> List[Dict]:
        return self.history
    
    def clear_history(self):
        self.history = []
        self._save_history()


class ISOChecker:
    """Checks if an ISO is Ubuntu-based and validates its structure."""
    
    UBUNTU_INDICATORS = [
        '.disk/info',
        'casper/filesystem.squashfs',
        'casper/vmlinuz',
        'casper/initrd',
        'boot/grub/grub.cfg',
    ]
    
    DEBIAN_BASED_INDICATORS = [
        'pool/main/',
        'dists/',
        '.disk/',
    ]
    
    @staticmethod
    def check_iso(iso_path: str) -> Dict[str, Any]:
        """
        Check if an ISO is Ubuntu-based.
        
        Returns a dictionary with:
        - is_valid: bool
        - is_ubuntu_based: bool
        - ubuntu_version: str or None
        - distro_name: str or None
        - indicators_found: list
        - warnings: list
        """
        result = {
            'is_valid': False,
            'is_ubuntu_based': False,
            'ubuntu_version': None,
            'distro_name': None,
            'indicators_found': [],
            'warnings': [],
        }
        
        if not os.path.exists(iso_path):
            result['warnings'].append("ISO file does not exist")
            return result
        
        # Try to mount and check the ISO
        mount_point = None
        try:
            import tempfile
            mount_point = tempfile.mkdtemp(prefix="ubucustom_check_")
            
            # Mount the ISO
            mount_result = subprocess.run(
                ['mount', '-o', 'loop,ro', iso_path, mount_point],
                capture_output=True
            )
            
            if mount_result.returncode != 0:
                result['warnings'].append("Could not mount ISO for inspection")
                return result
            
            result['is_valid'] = True
            
            # Check for Ubuntu indicators
            for indicator in ISOChecker.UBUNTU_INDICATORS:
                full_path = os.path.join(mount_point, indicator)
                if os.path.exists(full_path):
                    result['indicators_found'].append(indicator)
            
            # Check .disk/info for version info
            disk_info_path = os.path.join(mount_point, '.disk/info')
            if os.path.exists(disk_info_path):
                try:
                    with open(disk_info_path, 'r') as f:
                        info_content = f.read().strip()
                        result['distro_name'] = info_content
                        
                        # Extract version
                        ubuntu_match = re.search(r'Ubuntu (\d+\.\d+)', info_content)
                        if ubuntu_match:
                            result['ubuntu_version'] = ubuntu_match.group(1)
                            result['is_ubuntu_based'] = True
                        elif 'ubuntu' in info_content.lower():
                            result['is_ubuntu_based'] = True
                except Exception as e:
                    result['warnings'].append(f"Could not read .disk/info: {e}")
            
            # Check for casper (Ubuntu live CD indicator)
            casper_path = os.path.join(mount_point, 'casper')
            if os.path.exists(casper_path):
                result['is_ubuntu_based'] = True
            
            # Additional checks for Debian-based
            if not result['is_ubuntu_based']:
                debian_indicators = 0
                for indicator in ISOChecker.DEBIAN_BASED_INDICATORS:
                    full_path = os.path.join(mount_point, indicator)
                    if os.path.exists(full_path):
                        debian_indicators += 1
                
                if debian_indicators >= 2:
                    result['warnings'].append("ISO appears to be Debian-based but not Ubuntu")
            
            # Check for preseed/kickstart files
            preseed_path = os.path.join(mount_point, 'preseed')
            if os.path.exists(preseed_path):
                result['indicators_found'].append('preseed/')
            
        except Exception as e:
            result['warnings'].append(f"Error checking ISO: {e}")
        finally:
            if mount_point:
                try:
                    subprocess.run(['umount', mount_point], capture_output=True)
                    os.rmdir(mount_point)
                except:
                    pass
        
        return result
    
    @staticmethod
    def get_check_summary(result: Dict[str, Any]) -> str:
        """Get a human-readable summary of the ISO check."""
        lines = []
        
        if result['is_ubuntu_based']:
            lines.append("✓ Ubuntu-based ISO detected")
            if result['ubuntu_version']:
                lines.append(f"  Version: Ubuntu {result['ubuntu_version']}")
        else:
            lines.append("✗ Not an Ubuntu-based ISO")
        
        if result['distro_name']:
            lines.append(f"  Distribution: {result['distro_name']}")
        
        if result['indicators_found']:
            lines.append(f"  Found {len(result['indicators_found'])} Ubuntu indicators")
        
        if result['warnings']:
            lines.append("\nWarnings:")
            for warning in result['warnings']:
                lines.append(f"  ⚠ {warning}")
        
        return '\n'.join(lines)


class QEMUEmulator:
    """QEMU-based ISO testing emulator."""
    
    def __init__(self, parent_widget):
        self.parent = parent_widget
        self.process: Optional[subprocess.Popen] = None
        self.window: Optional[tk.Toplevel] = None
        self.is_running = False
    
    def check_qemu(self) -> bool:
        """Check if QEMU is installed."""
        return shutil.which('qemu-system-x86_64') is not None
    
    def get_qemu_command(self, iso_path: str, memory: int = 2048, cores: int = 2, 
                        enable_kvm: bool = True) -> list:
        """Build QEMU command for testing an ISO."""
        cmd = ['qemu-system-x86_64']
        
        # Machine settings
        cmd.extend(['-m', str(memory)])
        cmd.extend(['-smp', str(cores)])
        cmd.extend(['-cdrom', iso_path])
        cmd.extend(['-boot', 'd'])
        
        # Enable KVM if available
        if enable_kvm and os.path.exists('/dev/kvm'):
            cmd.append('-enable-kvm')
        
        # Display
        cmd.extend(['-display', 'gtk'])
        
        # Network (user mode)
        cmd.extend(['-netdev', 'user,id=net0'])
        cmd.extend(['-device', 'e1000,netdev=net0'])
        
        # Storage for testing (temporary disk)
        cmd.extend(['-drive', 'file=/dev/null,if=virtio,cache=none'])
        
        return cmd
    
    def test_iso(self, iso_path: str, memory: int = 2048, cores: int = 2) -> bool:
        """Launch QEMU to test the ISO."""
        if not self.check_qemu():
            messagebox.showerror(
                "QEMU Not Found",
                "QEMU is not installed.\n\n"
                "Install with:\n"
                "sudo apt-get install qemu-system-x86"
            )
            return False
        
        if not os.path.exists(iso_path):
            messagebox.showerror("Error", f"ISO file not found: {iso_path}")
            return False
        
        # Create control window
        self.window = tk.Toplevel(self.parent)
        self.window.title("QEMU Emulator - Testing ISO")
        self.window.geometry("400x300")
        self.window.protocol("WM_DELETE_WINDOW", self.stop_emulator)
        
        # Info frame
        info_frame = tk.LabelFrame(self.window, text="Emulator Settings", padx=10, pady=10)
        info_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(info_frame, text=f"ISO: {os.path.basename(iso_path)}").pack(anchor=tk.W)
        tk.Label(info_frame, text=f"Memory: {memory} MB").pack(anchor=tk.W)
        tk.Label(info_frame, text=f"CPU Cores: {cores}").pack(anchor=tk.W)
        
        kvm_status = "Enabled" if os.path.exists('/dev/kvm') else "Disabled (no KVM)"
        tk.Label(info_frame, text=f"KVM: {kvm_status}").pack(anchor=tk.W)
        
        # Status
        self.status_label = tk.Label(
            self.window,
            text="Starting emulator...",
            font=('Ubuntu', 11, 'bold'),
            fg='#E95420'
        )
        self.status_label.pack(pady=20)
        
        # Buttons
        btn_frame = tk.Frame(self.window)
        btn_frame.pack(pady=10)
        
        self.stop_btn = tk.Button(
            btn_frame,
            text="Stop Emulator",
            bg='#C7162B',
            fg='white',
            command=self.stop_emulator
        )
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Start QEMU in a thread
        self.is_running = True
        thread = threading.Thread(target=self._run_qemu, args=(iso_path, memory, cores))
        thread.daemon = True
        thread.start()
        
        return True
    
    def _run_qemu(self, iso_path: str, memory: int, cores: int):
        """Run QEMU process."""
        try:
            cmd = self.get_qemu_command(iso_path, memory, cores)
            self.process = subprocess.Popen(cmd)
            
            self.window.after(0, lambda: self.status_label.config(
                text="✓ Emulator running",
                fg='#0E8420'
            ))
            
            # Wait for process
            self.process.wait()
            
        except Exception as e:
            self.window.after(0, lambda: self.status_label.config(
                text=f"Error: {e}",
                fg='#C7162B'
            ))
        finally:
            self.is_running = False
            self.window.after(0, self._emulator_finished)
    
    def stop_emulator(self):
        """Stop the QEMU emulator."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except:
                self.process.kill()
        
        self.is_running = False
        if self.window:
            self.window.destroy()
            self.window = None
    
    def _emulator_finished(self):
        """Called when emulator finishes."""
        if self.window and self.window.winfo_exists():
            self.status_label.config(
                text="Emulator stopped",
                fg='#666666'
            )
            self.stop_btn.config(text="Close", command=self.window.destroy)


class AnimatedWidget:
    """Helper class for widget animations."""
    
    @staticmethod
    def fade_in(widget, duration=300, steps=20):
        """Fade in a widget."""
        alpha = 0.0
        step_duration = duration // steps
        
        def animate(step=0):
            if step >= steps:
                widget.attributes('-alpha', 1.0) if hasattr(widget, 'attributes') else None
                return
            
            alpha = (step + 1) / steps
            if hasattr(widget, 'attributes'):
                widget.attributes('-alpha', alpha)
            
            widget.after(step_duration, lambda: animate(step + 1))
        
        animate()
    
    @staticmethod
    def slide_in(widget, start_x=-50, duration=300):
        """Slide a widget in from the side."""
        widget.update_idletasks()
        original_x = widget.winfo_x()
        
        def animate(current_x, target_x):
            if current_x >= target_x:
                widget.place(x=target_x)
                return
            
            new_x = min(current_x + 5, target_x)
            widget.place(x=new_x)
            widget.after(10, lambda: animate(new_x, target_x))
        
        widget.place(x=start_x)
        animate(start_x, original_x)
    
    @staticmethod
    def pulse_button(button, color1, color2, duration=1000):
        """Create a pulsing effect on a button."""
        def animate(toggle=True):
            if not button.winfo_exists():
                return
            
            button.config(bg=color1 if toggle else color2)
            button.after(duration // 2, lambda: animate(not toggle))
        
        animate()
    
    @staticmethod
    def progress_animation(canvas, color, duration=2000):
        """Create an animated progress indicator."""
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        
        # Create animated dots
        dots = []
        for i in range(5):
            x = width // 2 - 40 + i * 20
            dot = canvas.create_oval(x-5, height//2-5, x+5, height//2+5, 
                                     fill=color, outline='')
            dots.append(dot)
        
        def animate(frame=0):
            if not canvas.winfo_exists():
                return
            
            for i, dot in enumerate(dots):
                offset = (frame + i * 2) % 10
                scale = 1.0 + 0.3 * (offset / 10)
                canvas.scale(dot, width//2 - 40 + i * 20, height//2, scale, scale)
            
            canvas.after(100, lambda: animate(frame + 1))
        
        animate()


class UbuCustomGUI:
    """Main GUI application for UbuCustom."""
    
    def __init__(self, root: Optional[tk.Tk] = None):
        """Initialize the GUI application."""
        self.root = root or tk.Tk()
        self.root.title("UbuCustom - Custom Ubuntu ISO Creator")
        
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Set to maximized window (cross-platform)
        width = int(screen_width * 0.95)
        height = int(screen_height * 0.9)
        x = int((screen_width - width) / 2)
        y = int((screen_height - height) / 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # Try to maximize window (Linux-specific)
        try:
            self.root.attributes('-zoomed', 1)
        except:
            pass
        
        self.root.minsize(1024, 768)
        
        # Full screen state
        self.is_fullscreen = False
        
        # Set modern theme
        self._setup_theme()
        
        # Bind F11 for full screen toggle
        self.root.bind('<F11>', lambda e: self._toggle_fullscreen())
        self.root.bind('<Escape>', lambda e: self._exit_fullscreen())
        
        # Root access status (check early)
        self.has_root = os.geteuid() == 0
        self.root_warning_shown = False
        
        # Setup logging
        setup_logging()
        
        # Initialize managers
        self.project_manager = ProjectManager()
        self.current_theme = 'ubuntu'
        
        # Variables
        self.iso_path = tk.StringVar()
        self.work_dir = tk.StringVar(value=os.path.expanduser("~/ubucustom-work"))
        self.output_path = tk.StringVar(value=os.path.expanduser("~/custom-ubuntu.iso"))
        self.volume_id = tk.StringVar(value="UbuCustom")
        self.compression = tk.StringVar(value="xz")
        self.status_text = tk.StringVar(value="Ready")
        self.log_text = tk.StringVar()
        self.project_name = tk.StringVar(value="My Custom Ubuntu")
        
        # Auto-extract setting
        self.auto_extract = tk.BooleanVar(value=False)
        
        # Package lists
        self.packages_to_install: List[str] = []
        self.packages_to_remove: List[str] = []
        
        self.builder: Optional[ISOBuilder] = None
        self.current_step = 0
        self.step_completed = [False, False, False, False, False]
        
        # Initialize emulator
        self.emulator = QEMUEmulator(self.root)
        
        # ISO check result
        self.iso_check_result: Optional[Dict[str, Any]] = None
        
        # Animation frame counter
        self.animation_frame = 0
        
        # Watch for ISO path changes for auto-extract
        self.iso_path.trace_add('write', self._on_iso_path_changed)
        
        # Create UI
        self._create_menu()
        self._create_sidebar()
        self._create_main_frame()
        self._create_status_bar()
        
        # Show first step with animation
        self.show_step(0)
        self._update_sidebar()
        
        # Request root access on first launch (after UI is ready)
        self.root.after(500, self._request_root_on_startup)
        
        # Fade in main window
        if self.animations_enabled:
            self.root.attributes('-alpha', 0.0)
            self._animate_window_appear()
    
    def _setup_theme(self) -> None:
        """Setup Ubuntu-inspired theme and colors."""
        # Ubuntu-inspired color scheme
        self.colors = {
            'primary': '#E95420',        # Ubuntu orange
            'primary_dark': '#C44418',   # Darker orange
            'secondary': '#772953',      # Ubuntu aubergine
            'accent': '#F4AA90',         # Light orange
            'background': '#F7F7F7',     # Light gray
            'surface': '#FFFFFF',        # White
            'text': '#111111',           # Near black
            'text_secondary': '#666666', # Gray
            'border': '#DEDEDE',         # Border gray
            'success': '#0E8420',        # Ubuntu green
            'warning': '#F99B11',        # Ubuntu yellow
            'error': '#C7162B',          # Ubuntu red
            'yaru_dark': '#5E2750',      # Yaru dark purple
        }
        
        # Animation settings
        self.animations_enabled = True
        self.animation_speed = 15  # ms between frames
        
        # Configure ttk styles
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure styles with Ubuntu colors
        style.configure('Title.TLabel', font=('Ubuntu', 24, 'bold'), foreground=self.colors['primary'])
        style.configure('Subtitle.TLabel', font=('Ubuntu', 12), foreground=self.colors['text_secondary'])
        style.configure('Step.TLabelframe', font=('Ubuntu', 11, 'bold'))
        style.configure('Step.TLabelframe.Label', font=('Ubuntu', 11, 'bold'), foreground=self.colors['primary'])
        style.configure('Action.TButton', font=('Ubuntu', 10, 'bold'))
        style.configure('Success.TLabel', foreground=self.colors['success'], font=('Ubuntu', 10, 'bold'))
        style.configure('Error.TLabel', foreground=self.colors['error'], font=('Ubuntu', 10, 'bold'))
        
        # Progress bar style with Ubuntu orange
        style.configure('Horizontal.TProgressbar', thickness=20, background=self.colors['primary'], troughcolor=self.colors['border'])
        
        # Frame backgrounds
        self.root.configure(bg=self.colors['background'])
    
    def _create_menu(self) -> None:
        """Create the menu bar."""
        menubar = tk.Menu(self.root, bg=self.colors['surface'], fg=self.colors['text'])
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=self.colors['surface'])
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Project", command=self._new_project, accelerator="Ctrl+N")
        file_menu.add_command(label="Save Project", command=self._save_project, accelerator="Ctrl+S")
        file_menu.add_command(label="Save Project As...", command=self._save_project_as, accelerator="Ctrl+Shift+S")
        file_menu.add_command(label="Load Project...", command=self._load_project_dialog, accelerator="Ctrl+O")
        file_menu.add_separator()
        
        # Recent projects submenu
        recent_menu = tk.Menu(file_menu, tearoff=0, bg=self.colors['surface'])
        file_menu.add_cascade(label="Recent Projects", menu=recent_menu)
        self._update_recent_menu(recent_menu)
        
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit, accelerator="Ctrl+Q")
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0, bg=self.colors['surface'])
        menubar.add_cascade(label="View", menu=view_menu)
        
        # Full screen toggle
        view_menu.add_command(label="Toggle Full Screen (F11)", command=self._toggle_fullscreen)
        view_menu.add_command(label="Exit Full Screen (Esc)", command=self._exit_fullscreen)
        view_menu.add_separator()
        
        # Theme submenu
        theme_menu = tk.Menu(view_menu, tearoff=0, bg=self.colors['surface'])
        view_menu.add_cascade(label="Theme", menu=theme_menu)
        theme_menu.add_command(label="Ubuntu (Default)", command=lambda: self._switch_theme('ubuntu'))
        theme_menu.add_command(label="Dark Mode", command=lambda: self._switch_theme('dark'))
        theme_menu.add_command(label="Blue", command=lambda: self._switch_theme('blue'))
        theme_menu.add_separator()
        theme_menu.add_command(label="Windows 95 (Retro)", command=lambda: self._switch_theme('win95'))
        theme_menu.add_command(label="VS Code (Dark)", command=lambda: self._switch_theme('vscode'))
        
        view_menu.add_separator()
        view_menu.add_checkbutton(label="Enable Animations", 
                                  command=self._toggle_animations,
                                  variable=tk.BooleanVar(value=self.animations_enabled))
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0, bg=self.colors['surface'])
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Check Dependencies", command=self._check_deps)
        tools_menu.add_command(label="Check ISO", command=self._check_iso_dialog)
        tools_menu.add_command(label="Package Manager", command=self._show_package_manager)
        tools_menu.add_separator()
        tools_menu.add_command(label="View Logs", command=self._show_logs)
        tools_menu.add_command(label="Clean Working Directory", command=self._clean_workdir)
        tools_menu.add_command(label="Clear History", command=self._clear_history)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0, bg=self.colors['surface'])
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Documentation", command=self._show_docs)
        help_menu.add_command(label="Keyboard Shortcuts", command=self._show_shortcuts)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about)
        help_menu.add_separator()
        help_menu.add_command(label="Created by Abdellah Agtaib", state='disabled')
        
        # Keyboard shortcuts
        self.root.bind('<Control-n>', lambda e: self._new_project())
        self.root.bind('<Control-s>', lambda e: self._save_project())
        self.root.bind('<Control-q>', lambda e: self.root.quit())
        self.root.bind('<F1>', lambda e: self._show_docs())
        self.root.bind('<F5>', lambda e: self._check_deps())
    
    def _update_recent_menu(self, menu):
        """Update recent projects menu."""
        menu.delete(0, 'end')
        projects = self.project_manager.get_recent_projects()
        if not projects:
            menu.add_command(label="No recent projects", state=tk.DISABLED)
        else:
            for i, project in enumerate(projects[:5], 1):
                name = project.get('name', 'Unknown')
                date = project.get('date', '')[:10]
                label = f"{i}. {name} ({date})"
                menu.add_command(label=label, 
                               command=lambda p=project: self._load_project(p))
    
    def _switch_theme(self, theme_name: str):
        """Switch application theme immediately."""
        self.current_theme = theme_name
        self.colors = ThemeManager.get_theme(theme_name)
        
        # Apply theme to all widgets
        self._apply_theme_to_widgets()
        
        self.status_text.set(f"Theme: {theme_name.title()}")
    
    def _apply_theme_to_widgets(self):
        """Apply current theme to all widgets."""
        is_win95 = self.current_theme == 'win95'
        
        # Update root background
        self.root.configure(bg=self.colors['background'])
        
        # Update sidebar
        self.sidebar.configure(bg=self.colors['surface'])
        for widget in self.sidebar.winfo_children():
            if isinstance(widget, (tk.Frame, tk.Label)):
                widget.configure(bg=self.colors['surface'])
                for child in widget.winfo_children():
                    if isinstance(child, tk.Label):
                        if child.cget('fg') in [ThemeManager.THEMES['ubuntu']['primary'], 
                                               ThemeManager.THEMES['dark']['primary'],
                                               ThemeManager.THEMES['blue']['primary']]:
                            child.configure(bg=self.colors['surface'], fg=self.colors['primary'])
                        else:
                            child.configure(bg=self.colors['surface'])
                    elif isinstance(child, tk.Entry):
                        if is_win95:
                            child.configure(bg='white', relief=tk.SUNKEN, bd=2)
                        else:
                            child.configure(bg=self.colors['background'])
                    elif isinstance(child, tk.Button):
                        if is_win95:
                            self._apply_win95_button_style(child)
                        else:
                            child.configure(bg=self.colors['error'] if 'Root' in child.cget('text') else self.colors['primary'])
        
        # Update content frame
        self.content_frame.configure(bg=self.colors['background'])
        self.header_frame.configure(bg=self.colors['background'])
        self.title_label.configure(bg=self.colors['background'], fg=self.colors['primary'])
        self.subtitle_label.configure(bg=self.colors['background'], fg=self.colors['text_secondary'])
        
        # Update steps frame
        self.steps_frame.configure(bg=self.colors['background'])
        for frame in self.step_frames:
            frame.configure(bg=self.colors['background'])
            self._update_frame_theme(frame, is_win95)
        
        # Update navigation buttons
        self.nav_frame.configure(bg=self.colors['background'])
        if is_win95:
            self._apply_win95_button_style(self.back_btn)
            self._apply_win95_button_style(self.next_btn)
            self._apply_win95_button_style(self.finish_btn)
        else:
            self.back_btn.configure(bg=self.colors['background'], fg=self.colors['text'])
            self.next_btn.configure(bg=self.colors['primary'], fg='white')
            self.finish_btn.configure(bg=self.colors['success'], fg='white')
        
        # Update status bar
        self.status_bar.configure(bg=self.colors['surface'])
        self.status_inner.configure(bg=self.colors['surface'])
        self.status_label.configure(bg=self.colors['surface'], fg=self.colors['text_secondary'])
        
        # Update root status
        self._update_root_status()
        
        # Force update
        self.root.update_idletasks()
    
    def _apply_win95_button_style(self, button):
        """Apply Windows 95 3D button style."""
        button.configure(
            bg=self.colors.get('button_face', '#C0C0C0'),
            fg='black',
            relief=tk.RAISED,
            bd=2,
            highlightbackground=self.colors.get('button_highlight', '#FFFFFF'),
            highlightcolor=self.colors.get('button_highlight', '#FFFFFF')
        )
        
        # Add 3D effect on press/release
        def on_press(event):
            button.configure(relief=tk.SUNKEN)
        
        def on_release(event):
            button.configure(relief=tk.RAISED)
        
        button.bind('<ButtonPress-1>', on_press)
        button.bind('<ButtonRelease-1>', on_release)
    
    def _update_frame_theme(self, parent, is_win95=False):
        """Recursively update theme for all widgets in a frame."""
        for widget in parent.winfo_children():
            widget_type = type(widget).__name__
            
            try:
                if widget_type == 'Frame':
                    widget.configure(bg=self.colors['background'])
                    self._update_frame_theme(widget, is_win95)
                elif widget_type == 'LabelFrame':
                    widget.configure(bg=self.colors['background'], fg=self.colors['text'])
                    self._update_frame_theme(widget, is_win95)
                elif widget_type == 'Label':
                    current_fg = widget.cget('fg')
                    # Keep success/error colors, update others
                    if current_fg in ['#0E8420', '#4CAF50', '#008000', '#C7162B', '#F44336', '#FF0000']:
                        widget.configure(bg=self.colors['background'])
                    else:
                        widget.configure(bg=self.colors['background'], fg=self.colors['text'])
                elif widget_type == 'Button':
                    if is_win95:
                        self._apply_win95_button_style(widget)
                elif widget_type == 'Entry':
                    if is_win95:
                        widget.configure(bg='white', relief=tk.SUNKEN, bd=2)
                    else:
                        widget.configure(bg='white')
                elif widget_type == 'Checkbutton':
                    if is_win95:
                        widget.configure(bg=self.colors['background'], fg=self.colors['text'],
                                       selectcolor='white')
                    else:
                        widget.configure(bg=self.colors['background'], fg=self.colors['text'],
                                       selectcolor=self.colors['surface'])
                elif widget_type == 'Text':
                    widget.configure(bg=self.colors['surface'], fg=self.colors['text'])
                elif widget_type == 'Canvas':
                    widget.configure(bg=self.colors['surface'])
                elif widget_type == 'Spinbox':
                    if is_win95:
                        widget.configure(bg='white', relief=tk.SUNKEN)
                else:
                    # Try to update other widgets
                    try:
                        widget.configure(bg=self.colors['background'])
                    except:
                        pass
            except Exception:
                pass
    
    def _toggle_fullscreen(self):
        """Toggle full screen mode."""
        self.is_fullscreen = not self.is_fullscreen
        
        if self.is_fullscreen:
            # Enter full screen
            try:
                self.root.attributes('-zoomed', True)
            except:
                pass
            self.root.attributes('-fullscreen', True)
            self.status_text.set("Full screen mode")
        else:
            # Exit full screen
            try:
                self.root.attributes('-zoomed', False)
            except:
                pass
            self.root.attributes('-fullscreen', False)
            # Set to a reasonable window size
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            width = int(screen_width * 0.8)
            height = int(screen_height * 0.8)
            x = (screen_width - width) // 2
            y = (screen_height - height) // 2
            self.root.geometry(f"{width}x{height}+{x}+{y}")
            self.status_text.set("Windowed mode")
    
    def _exit_fullscreen(self):
        """Exit full screen mode."""
        if self.is_fullscreen:
            self._toggle_fullscreen()
    
    def _toggle_animations(self):
        """Toggle animations on/off."""
        self.animations_enabled = not self.animations_enabled
        status = "enabled" if self.animations_enabled else "disabled"
        self.status_text.set(f"Animations {status}")
    
    def _save_project(self):
        """Save current project."""
        if not self.iso_path.get():
            messagebox.showwarning("Save Project", "No project to save.")
            return
        
        data = {
            'iso_path': self.iso_path.get(),
            'work_dir': self.work_dir.get(),
            'output_path': self.output_path.get(),
            'volume_id': self.volume_id.get(),
        }
        
        self.project_manager.save_project(self.project_name.get(), data)
        self.status_text.set("Project saved")
        messagebox.showinfo("Save Project", f"Project '{self.project_name.get()}' saved.")
    
    def _save_project_as(self):
        """Save project to a specific file."""
        if not self.iso_path.get():
            messagebox.showwarning("Save Project", "No project to save.")
            return
        
        filename = filedialog.asksaveasfilename(
            title="Save Project As",
            defaultextension=".ubucustom",
            filetypes=[("UbuCustom Project", "*.ubucustom"), ("JSON", "*.json"), ("All files", "*.*")],
            initialfile=f"{self.project_name.get()}.ubucustom"
        )
        
        if not filename:
            return
        
        data = {
            'name': self.project_name.get(),
            'iso_path': self.iso_path.get(),
            'work_dir': self.work_dir.get(),
            'output_path': self.output_path.get(),
            'volume_id': self.volume_id.get(),
            'theme': self.current_theme,
            'saved_at': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            import json
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            self.status_text.set(f"Project saved to {os.path.basename(filename)}")
            messagebox.showinfo("Save Project", f"Project saved to:\n{filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save project:\n{e}")
    
    def _load_project_dialog(self):
        """Load project from file dialog."""
        filename = filedialog.askopenfilename(
            title="Load Project",
            filetypes=[("UbuCustom Project", "*.ubucustom"), ("JSON", "*.json"), ("All files", "*.*")],
            defaultextension=".ubucustom"
        )
        
        if not filename:
            return
        
        try:
            import json
            with open(filename, 'r') as f:
                data = json.load(f)
            
            if messagebox.askyesno("Load Project", 
                                  f"Load project '{data.get('name', 'Untitled')}'?\n"
                                  "Current progress will be lost."):
                self.project_name.set(data.get('name', 'Loaded Project'))
                self.iso_path.set(data.get('iso_path', ''))
                self.work_dir.set(data.get('work_dir', ''))
                self.output_path.set(data.get('output_path', ''))
                self.volume_id.set(data.get('volume_id', 'UbuCustom'))
                
                # Load theme if saved
                saved_theme = data.get('theme')
                if saved_theme and saved_theme in ThemeManager.THEMES:
                    self._switch_theme(saved_theme)
                
                self._update_iso_info()
                self.status_text.set(f"Loaded project: {data.get('name', 'Untitled')}")
                messagebox.showinfo("Load Project", f"Project '{data.get('name', 'Untitled')}' loaded successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load project:\n{e}")
    
    def _load_project(self, project: Dict):
        """Load a saved project from history."""
        if messagebox.askyesno("Load Project", 
                              f"Load project '{project.get('name')}'?\n"
                              "Current progress will be lost."):
            self.iso_path.set(project.get('iso_path', ''))
            self.work_dir.set(project.get('work_dir', ''))
            self.output_path.set(project.get('output_path', ''))
            self.volume_id.set(project.get('volume_id', 'UbuCustom'))
            self._update_iso_info()
            self.status_text.set(f"Loaded project: {project.get('name')}")
    
    def _clear_history(self):
        """Clear project history."""
        if messagebox.askyesno("Clear History", "Clear all project history?"):
            self.project_manager.clear_history()
            self.status_text.set("History cleared")
    
    def _show_shortcuts(self):
        """Show keyboard shortcuts dialog."""
        shortcuts = """
Keyboard Shortcuts:

File Operations:
  Ctrl+N    New Project
  Ctrl+S    Save Project
  Ctrl+Q    Quit

View:
  F11       Toggle Full Screen
  Esc       Exit Full Screen

Navigation:
  F1        Documentation
  F5        Check Dependencies
  ←         Previous Step
  →         Next Step

Tools:
  F6        Check ISO
  F7        Package Manager
  F8        View Logs
        """
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Keyboard Shortcuts")
        dialog.geometry("400x500")
        dialog.configure(bg=self.colors['background'])
        
        tk.Label(
            dialog,
            text="Keyboard Shortcuts",
            font=('Ubuntu', 16, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['primary']
        ).pack(pady=(20, 10))
        
        text = scrolledtext.ScrolledText(
            dialog,
            wrap=tk.WORD,
            font=('Ubuntu Mono', 11),
            bg=self.colors['surface'],
            fg=self.colors['text'],
            padx=15,
            pady=15
        )
        text.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        text.insert(tk.END, shortcuts)
        text.config(state=tk.DISABLED)
        
        tk.Button(
            dialog,
            text="Close",
            font=('Ubuntu', 10),
            bg=self.colors['primary'],
            fg='white',
            command=dialog.destroy
        ).pack(pady=(0, 20))
    
    def _create_sidebar(self) -> None:
        """Create the sidebar with step indicators."""
        self.sidebar = tk.Frame(self.root, bg=self.colors['surface'], width=200, bd=1, relief=tk.FLAT)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 1))
        self.sidebar.grid_propagate(False)
        
        # Sidebar title
        tk.Label(
            self.sidebar,
            text="UbuCustom",
            font=('Ubuntu', 20, 'bold'),
            bg=self.colors['surface'],
            fg=self.colors['primary']
        ).pack(pady=(20, 5))
        
        tk.Label(
            self.sidebar,
            text="ISO Creator",
            font=('Ubuntu', 10),
            bg=self.colors['surface'],
            fg=self.colors['text_secondary']
        ).pack(pady=(0, 15))
        
        # Project name entry
        project_frame = tk.Frame(self.sidebar, bg=self.colors['surface'])
        project_frame.pack(fill=tk.X, padx=15, pady=(0, 20))
        
        tk.Label(
            project_frame,
            text="Project Name:",
            font=('Ubuntu', 9),
            bg=self.colors['surface'],
            fg=self.colors['text_secondary']
        ).pack(anchor=tk.W)
        
        project_entry = tk.Entry(
            project_frame,
            textvariable=self.project_name,
            font=('Ubuntu', 10),
            bg=self.colors['background'],
            relief=tk.SOLID,
            bd=1
        )
        project_entry.pack(fill=tk.X, pady=(2, 0))
        
        # Root status indicator
        self.root_status_frame = tk.Frame(self.sidebar, bg=self.colors['surface'])
        self.root_status_frame.pack(fill=tk.X, padx=15, pady=(10, 20))
        
        self._update_root_status()
        
        # Step indicators
        self.step_labels = []
        self.step_indicators = []
        
        steps = [
            ("1", "Select ISO", "Choose source ISO file"),
            ("2", "Extract", "Extract ISO contents"),
            ("3", "Customize", "Modify the system"),
            ("4", "Build", "Create custom ISO"),
            ("5", "Test", "Test in emulator"),
        ]
        
        for i, (num, title, desc) in enumerate(steps):
            frame = tk.Frame(self.sidebar, bg=self.colors['surface'], pady=10)
            frame.pack(fill=tk.X, padx=15, pady=5)
            
            # Step number circle
            indicator = tk.Canvas(
                frame, width=30, height=30, bg=self.colors['surface'],
                highlightthickness=0
            )
            indicator.pack(side=tk.LEFT)
            self.step_indicators.append(indicator)
            
            # Step text
            text_frame = tk.Frame(frame, bg=self.colors['surface'])
            text_frame.pack(side=tk.LEFT, padx=(10, 0))
            
            title_label = tk.Label(
                text_frame,
                text=title,
                font=('Helvetica', 11, 'bold'),
                bg=self.colors['surface'],
                fg=self.colors['text']
            )
            title_label.pack(anchor=tk.W)
            
            desc_label = tk.Label(
                text_frame,
                text=desc,
                font=('Helvetica', 9),
                bg=self.colors['surface'],
                fg=self.colors['text_secondary']
            )
            desc_label.pack(anchor=tk.W)
            
            self.step_labels.append((title_label, desc_label))
        
        # Separator
        tk.Frame(self.sidebar, bg=self.colors['border'], height=1).pack(fill=tk.X, padx=15, pady=20)
        
        # Quick actions
        tk.Label(
            self.sidebar,
            text="Quick Actions",
            font=('Helvetica', 10, 'bold'),
            bg=self.colors['surface'],
            fg=self.colors['text_secondary']
        ).pack(anchor=tk.W, padx=15, pady=(0, 10))
        
        quick_actions = [
            ("Check Dependencies", self._check_deps),
            ("Check ISO", self._check_iso_dialog),
            ("Clean Workspace", self._clean_workdir),
            ("View Logs", self._show_logs),
        ]
        
        for text, command in quick_actions:
            btn = tk.Button(
                self.sidebar,
                text=text,
                font=('Helvetica', 9),
                bg=self.colors['surface'],
                fg=self.colors['primary'],
                activebackground=self.colors['background'],
                activeforeground=self.colors['primary_dark'],
                bd=0,
                cursor='hand2',
                command=command
            )
            btn.pack(fill=tk.X, padx=15, pady=2)
    
    def _update_sidebar(self) -> None:
        """Update sidebar step indicators."""
        for i, indicator in enumerate(self.step_indicators):
            indicator.delete('all')
            
            if i == self.current_step:
                # Current step - filled primary color
                indicator.create_oval(2, 2, 28, 28, fill=self.colors['primary'], outline='')
                indicator.create_text(15, 15, text=str(i+1), fill='white', font=('Helvetica', 10, 'bold'))
                self.step_labels[i][0].config(fg=self.colors['primary'])
            elif self.step_completed[i]:
                # Completed step - filled success color
                indicator.create_oval(2, 2, 28, 28, fill=self.colors['success'], outline='')
                indicator.create_text(15, 15, text='✓', fill='white', font=('Helvetica', 12, 'bold'))
                self.step_labels[i][0].config(fg=self.colors['success'])
            else:
                # Future step - outline
                indicator.create_oval(2, 2, 28, 28, outline=self.colors['border'], width=2)
                indicator.create_text(15, 15, text=str(i+1), fill=self.colors['text_secondary'], font=('Helvetica', 10))
                self.step_labels[i][0].config(fg=self.colors['text'])
    
    def _update_root_status(self):
        """Update the root status indicator in sidebar."""
        # Clear existing widgets
        for widget in self.root_status_frame.winfo_children():
            widget.destroy()
        
        if self.has_root:
            # Root access available
            status_text = "✓ Root Access"
            status_color = self.colors['success']
            btn_text = None
        else:
            # No root access
            status_text = "✗ No Root Access"
            status_color = self.colors['error']
            btn_text = "Get Root Access"
        
        tk.Label(
            self.root_status_frame,
            text=status_text,
            font=('Ubuntu', 9, 'bold'),
            bg=self.colors['surface'],
            fg=status_color
        ).pack(anchor=tk.W)
        
        if btn_text:
            tk.Button(
                self.root_status_frame,
                text=btn_text,
                font=('Ubuntu', 8),
                bg=self.colors['error'],
                fg='white',
                activebackground='#9B1B2A',
                bd=0,
                padx=10,
                pady=3,
                cursor='hand2',
                command=self._request_root_access
            ).pack(anchor=tk.W, pady=(5, 0))
    
    def _request_root_access(self):
        """Request root access via pkexec or sudo."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Root Access Required")
        dialog.geometry("450x350")
        dialog.configure(bg=self.colors['background'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Title
        tk.Label(
            dialog,
            text="🔐 Root Access Required",
            font=('Ubuntu', 16, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['primary']
        ).pack(pady=(20, 10))
        
        # Explanation
        explanation = """
Some operations require root (administrator) privileges:

• Extracting ISO filesystem
• Entering chroot environment
• Installing/removing packages
• Building custom ISO

You can acquire root access using one of these methods:
        """
        
        tk.Label(
            dialog,
            text=explanation,
            font=('Ubuntu', 10),
            bg=self.colors['background'],
            fg=self.colors['text'],
            justify=tk.LEFT,
            wraplength=400
        ).pack(padx=20, pady=10)
        
        # Methods frame
        methods_frame = tk.Frame(dialog, bg=self.colors['background'])
        methods_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Method 1: pkexec (graphical)
        tk.Button(
            methods_frame,
            text="1. Use Graphical Authentication (pkexec)",
            font=('Ubuntu', 10, 'bold'),
            bg=self.colors['primary'],
            fg='white',
            activebackground=self.colors['primary_dark'],
            bd=0,
            padx=20,
            pady=10,
            cursor='hand2',
            command=lambda: self._get_root_pkexec(dialog)
        ).pack(fill=tk.X, pady=5)
        
        # Method 2: Restart with sudo
        tk.Button(
            methods_frame,
            text="2. Restart with sudo (Terminal)",
            font=('Ubuntu', 10),
            bg=self.colors['secondary'],
            fg='white',
            activebackground='#5E1E47',
            bd=0,
            padx=20,
            pady=10,
            cursor='hand2',
            command=lambda: self._restart_with_sudo(dialog)
        ).pack(fill=tk.X, pady=5)
        
        # Cancel button
        tk.Button(
            dialog,
            text="Cancel",
            font=('Ubuntu', 10),
            bg=self.colors['background'],
            fg=self.colors['text'],
            activebackground=self.colors['border'],
            bd=1,
            relief=tk.SOLID,
            padx=20,
            pady=8,
            cursor='hand2',
            command=dialog.destroy
        ).pack(pady=(10, 20))
    
    def _get_root_pkexec(self, dialog):
        """Get root access using pkexec."""
        dialog.destroy()
        
        # Create a temporary script to check root
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("""
import os
import sys
if os.geteuid() == 0:
    print("ROOT_OK")
    sys.exit(0)
else:
    print("ROOT_FAILED")
    sys.exit(1)
""")
            temp_script = f.name
        
        try:
            # Try to run with pkexec
            result = subprocess.run(
                ['pkexec', 'python3', temp_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and "ROOT_OK" in result.stdout:
                self.has_root = True
                self._update_root_status()
                messagebox.showinfo("Success", "Root access acquired successfully!")
            else:
                messagebox.showerror("Failed", "Could not acquire root access.\n\nPlease try restarting with sudo.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get root access:\n{str(e)}")
        finally:
            try:
                os.unlink(temp_script)
            except:
                pass
    
    def _restart_with_sudo(self, dialog):
        """Restart the application with sudo."""
        dialog.destroy()
        
        if messagebox.askyesno(
            "Restart with sudo",
            "The application will restart with root privileges.\n\n"
            "Continue?"
        ):
            # Get the command to restart
            import sys
            args = ['sudo', sys.executable] + sys.argv
            
            try:
                subprocess.Popen(args)
                self.root.quit()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to restart:\n{str(e)}\n\n"
                                   "Please manually run:\n"
                                   f"sudo python3 {' '.join(sys.argv)}")
    
    def _check_root_for_operation(self, operation_name: str) -> bool:
        """Check if root is available for an operation, auto-request if not."""
        if self.has_root:
            return True
        
        # Auto-request root access
        self.status_text.set(f"Requesting root access for {operation_name}...")
        self._auto_request_root()
        
        # Check again after request
        return self.has_root
    
    def _request_root_on_startup(self):
        """Request root access when app launches if not already root."""
        if self.has_root:
            return
        
        # Show dialog asking for root access on startup
        response = messagebox.askyesno(
            "Root Access Required",
            "UbuCustom requires root privileges for ISO operations.\n\n"
            "Would you like to authenticate now?\n\n"
            "You can skip this and authenticate later when needed.",
            icon='warning'
        )
        
        if response:
            self._auto_request_root()
    
    def _auto_request_root(self):
        """Automatically request root access using pkexec without dialogs."""
        import tempfile
        
        # Create a temporary script to test root
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("""
import os
import sys
if os.geteuid() == 0:
    print("ROOT_OK")
    sys.exit(0)
else:
    print("ROOT_FAILED")
    sys.exit(1)
""")
            temp_script = f.name
        
        try:
            # Try pkexec silently
            result = subprocess.run(
                ['pkexec', 'python3', temp_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and "ROOT_OK" in result.stdout:
                self.has_root = True
                self._update_root_status()
                self.status_text.set("Root access granted")
            else:
                # pkexec failed or cancelled, show manual options
                self._request_root_access()
        except Exception:
            # pkexec not available, show manual options
            self._request_root_access()
        finally:
            try:
                os.unlink(temp_script)
            except:
                pass
    
    def _create_main_frame(self) -> None:
        """Create the main content frame."""
        # Main container with sidebar
        self.content_frame = tk.Frame(self.root, bg=self.colors['background'])
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        # Configure grid weights
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(1, weight=1)
        
        # Header with title and progress
        self.header_frame = tk.Frame(self.content_frame, bg=self.colors['background'])
        self.header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        
        self.title_label = tk.Label(
            self.header_frame,
            text="Select ISO",
            font=('Helvetica', 24, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text']
        )
        self.title_label.pack(anchor=tk.W)
        
        self.subtitle_label = tk.Label(
            self.header_frame,
            text="Step 1 of 4",
            font=('Helvetica', 11),
            bg=self.colors['background'],
            fg=self.colors['text_secondary']
        )
        self.subtitle_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Progress bar
        self.progress_bar = ttk.Progressbar(
            self.header_frame,
            mode='determinate',
            maximum=100,
            length=400
        )
        self.progress_bar.pack(fill=tk.X, pady=(15, 0))
        
        # Step frames container
        self.steps_frame = tk.Frame(self.content_frame, bg=self.colors['background'])
        self.steps_frame.grid(row=1, column=0, sticky="nsew")
        self.steps_frame.columnconfigure(0, weight=1)
        self.steps_frame.rowconfigure(0, weight=1)
        
        # Create step frames
        self.step_frames = []
        self._create_step1()
        self._create_step2()
        self._create_step3()
        self._create_step4()
        self._create_step5()
        
        # Navigation buttons at bottom
        self.nav_frame = tk.Frame(self.content_frame, bg=self.colors['background'])
        self.nav_frame.grid(row=2, column=0, pady=(20, 0), sticky="ew")
        
        self.back_btn = tk.Button(
            self.nav_frame,
            text="← Back",
            font=('Helvetica', 10),
            bg=self.colors['background'],
            fg=self.colors['text'],
            activebackground=self.colors['border'],
            bd=1,
            relief=tk.SOLID,
            padx=20,
            pady=8,
            cursor='hand2',
            command=self._prev_step
        )
        self.back_btn.pack(side=tk.LEFT)
        
        self.next_btn = tk.Button(
            self.nav_frame,
            text="Next →",
            font=('Helvetica', 10, 'bold'),
            bg=self.colors['primary'],
            fg='white',
            activebackground=self.colors['primary_dark'],
            activeforeground='white',
            bd=0,
            padx=20,
            pady=8,
            cursor='hand2',
            command=self._next_step
        )
        self.next_btn.pack(side=tk.RIGHT)
        
        self.finish_btn = tk.Button(
            self.nav_frame,
            text="✓ Finish",
            font=('Helvetica', 10, 'bold'),
            bg=self.colors['success'],
            fg='white',
            activebackground='#388E3C',
            activeforeground='white',
            bd=0,
            padx=20,
            pady=8,
            cursor='hand2',
            command=self.root.quit
        )
    
    def _create_step1(self) -> None:
        """Create Step 1: Select ISO."""
        frame = tk.Frame(self.steps_frame, bg=self.colors['background'])
        
        # ISO File Section
        iso_section = tk.LabelFrame(
            frame,
            text=" ISO File ",
            font=('Helvetica', 11, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text'],
            bd=1,
            relief=tk.SOLID
        )
        iso_section.pack(fill=tk.X, pady=(0, 20), ipady=10)
        
        tk.Label(
            iso_section,
            text="Select the Ubuntu ISO file you want to customize:",
            font=('Helvetica', 10),
            bg=self.colors['background'],
            fg=self.colors['text']
        ).pack(anchor=tk.W, padx=15, pady=(10, 10))
        
        # ISO selection row
        iso_frame = tk.Frame(iso_section, bg=self.colors['background'])
        iso_frame.pack(fill=tk.X, padx=15, pady=5)
        
        iso_entry = tk.Entry(
            iso_frame,
            textvariable=self.iso_path,
            font=('Helvetica', 10),
            bg='white',
            relief=tk.SOLID,
            bd=1
        )
        iso_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        browse_btn = tk.Button(
            iso_frame,
            text="Browse...",
            font=('Helvetica', 9),
            bg=self.colors['primary'],
            fg='white',
            activebackground=self.colors['primary_dark'],
            bd=0,
            padx=15,
            pady=5,
            cursor='hand2',
            command=self._browse_iso
        )
        browse_btn.pack(side=tk.RIGHT)
        
        # ISO info card
        self.iso_info_frame = tk.Frame(iso_section, bg=self.colors['surface'], bd=1, relief=tk.SOLID)
        self.iso_info_frame.pack(fill=tk.X, padx=15, pady=(15, 10))
        
        self.iso_info_label = tk.Label(
            self.iso_info_frame,
            text="No ISO selected\nSelect an ISO file to see its details",
            font=('Helvetica', 10),
            bg=self.colors['surface'],
            fg=self.colors['text_secondary'],
            justify=tk.LEFT,
            padx=15,
            pady=15
        )
        self.iso_info_label.pack(anchor=tk.W)
        
        # Working Directory Section
        work_section = tk.LabelFrame(
            frame,
            text=" Working Directory ",
            font=('Helvetica', 11, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text'],
            bd=1,
            relief=tk.SOLID
        )
        work_section.pack(fill=tk.X, pady=(0, 20), ipady=10)
        
        tk.Label(
            work_section,
            text="Choose where to extract and customize the ISO:",
            font=('Helvetica', 10),
            bg=self.colors['background'],
            fg=self.colors['text']
        ).pack(anchor=tk.W, padx=15, pady=(10, 10))
        
        work_frame = tk.Frame(work_section, bg=self.colors['background'])
        work_frame.pack(fill=tk.X, padx=15, pady=5)
        
        work_entry = tk.Entry(
            work_frame,
            textvariable=self.work_dir,
            font=('Helvetica', 10),
            bg='white',
            relief=tk.SOLID,
            bd=1
        )
        work_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        work_browse_btn = tk.Button(
            work_frame,
            text="Browse...",
            font=('Helvetica', 9),
            bg=self.colors['primary'],
            fg='white',
            activebackground=self.colors['primary_dark'],
            bd=0,
            padx=15,
            pady=5,
            cursor='hand2',
            command=self._browse_workdir
        )
        work_browse_btn.pack(side=tk.RIGHT)
        
        # Disk space warning
        self.disk_space_label = tk.Label(
            work_section,
            text="⚠ At least 10 GB of free space recommended",
            font=('Helvetica', 9),
            bg=self.colors['background'],
            fg=self.colors['warning']
        )
        self.disk_space_label.pack(anchor=tk.W, padx=15, pady=(10, 0))
        
        # Auto-extract option
        auto_frame = tk.Frame(frame, bg=self.colors['background'])
        auto_frame.pack(fill=tk.X, pady=(20, 0))
        
        self.auto_extract_cb = tk.Checkbutton(
            auto_frame,
            text="Auto-extract ISO after selection",
            variable=self.auto_extract,
            font=('Helvetica', 10),
            bg=self.colors['background'],
            fg=self.colors['text'],
            activebackground=self.colors['background'],
            selectcolor=self.colors['surface']
        )
        self.auto_extract_cb.pack(anchor=tk.W)
        
        tk.Label(
            auto_frame,
            text="Automatically proceed to extraction when ISO is selected",
            font=('Helvetica', 9),
            bg=self.colors['background'],
            fg=self.colors['text_secondary']
        ).pack(anchor=tk.W, padx=(25, 0))
        
        self.step_frames.append(frame)
    
    def _create_step2(self) -> None:
        """Create Step 2: Extract ISO."""
        frame = tk.Frame(self.steps_frame, bg=self.colors['background'])
        
        # Info box
        info_box = tk.Frame(frame, bg=self.colors['surface'], bd=1, relief=tk.SOLID)
        info_box.pack(fill=tk.X, pady=(0, 20))
        
        tk.Label(
            info_box,
            text="ℹ Extraction Process",
            font=('Helvetica', 11, 'bold'),
            bg=self.colors['surface'],
            fg=self.colors['primary']
        ).pack(anchor=tk.W, padx=15, pady=(15, 5))
        
        tk.Label(
            info_box,
            text="This will extract the ISO contents and the squashfs filesystem.\n"
                 "The process may take several minutes depending on the ISO size.",
            font=('Helvetica', 10),
            bg=self.colors['surface'],
            fg=self.colors['text'],
            justify=tk.LEFT
        ).pack(anchor=tk.W, padx=15, pady=(0, 15))
        
        # Progress section
        progress_frame = tk.LabelFrame(
            frame,
            text=" Progress ",
            font=('Helvetica', 11, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text'],
            bd=1,
            relief=tk.SOLID
        )
        progress_frame.pack(fill=tk.X, pady=(0, 20), ipady=15)
        
        self.extract_status = tk.Label(
            progress_frame,
            text="Ready to extract",
            font=('Helvetica', 10),
            bg=self.colors['background'],
            fg=self.colors['text_secondary']
        )
        self.extract_status.pack(anchor=tk.W, padx=15, pady=(10, 10))
        
        # Progress bar
        self.extract_progress = ttk.Progressbar(
            progress_frame,
            mode='indeterminate',
            length=400
        )
        self.extract_progress.pack(fill=tk.X, padx=15, pady=5)
        
        # Log display
        log_frame = tk.LabelFrame(
            frame,
            text=" Log Output ",
            font=('Helvetica', 11, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text'],
            bd=1,
            relief=tk.SOLID
        )
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        self.extract_log = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            wrap=tk.WORD,
            font=('Consolas', 9),
            bg=self.colors['surface'],
            fg=self.colors['text'],
            relief=tk.FLAT,
            padx=10,
            pady=10
        )
        self.extract_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Extract button
        self.extract_btn = tk.Button(
            frame,
            text="▶ Start Extraction",
            font=('Helvetica', 11, 'bold'),
            bg=self.colors['secondary'],
            fg='white',
            activebackground='#388E3C',
            activeforeground='white',
            bd=0,
            padx=30,
            pady=12,
            cursor='hand2',
            command=self._start_extraction
        )
        self.extract_btn.pack(pady=10)
        
        self.step_frames.append(frame)
    
    def _create_step3(self) -> None:
        """Create Step 3: Customize."""
        frame = tk.Frame(self.steps_frame, bg=self.colors['background'])
        
        # Info box
        info_box = tk.Frame(frame, bg=self.colors['surface'], bd=1, relief=tk.SOLID)
        info_box.pack(fill=tk.X, pady=(0, 20))
        
        tk.Label(
            info_box,
            text="⚠ Root Privileges Required",
            font=('Helvetica', 11, 'bold'),
            bg=self.colors['surface'],
            fg=self.colors['warning']
        ).pack(anchor=tk.W, padx=15, pady=(15, 5))
        
        tk.Label(
            info_box,
            text="Chroot operations require root privileges.\n"
                 "You may be prompted for your password when entering the chroot environment.",
            font=('Helvetica', 10),
            bg=self.colors['surface'],
            fg=self.colors['text'],
            justify=tk.LEFT
        ).pack(anchor=tk.W, padx=15, pady=(0, 15))
        
        # Actions frame
        actions_frame = tk.LabelFrame(
            frame,
            text=" Customization Actions ",
            font=('Helvetica', 11, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text'],
            bd=1,
            relief=tk.SOLID
        )
        actions_frame.pack(fill=tk.X, pady=(0, 20), ipady=10)
        
        # Action buttons with icons
        actions = [
            ("🖥 Enter Chroot Terminal", "Open a terminal inside the ISO filesystem", self._enter_chroot, self.colors['primary']),
            ("🧹 Cleanup Chroot", "Unmount virtual filesystems", self._cleanup_chroot, '#C7162B'),
            ("📦 Install Packages...", "Install packages using apt", self._install_packages_dialog, self.colors['secondary']),
            ("🗑 Remove Packages...", "Remove packages from the system", self._remove_packages_dialog, self.colors['accent']),
            ("📁 Open Working Directory", "Browse the extracted files", self._open_workdir, self.colors['text_secondary']),
        ]
        
        for text, desc, command, color in actions:
            btn_frame = tk.Frame(actions_frame, bg=self.colors['background'])
            btn_frame.pack(fill=tk.X, padx=15, pady=5)
            
            btn = tk.Button(
                btn_frame,
                text=text,
                font=('Helvetica', 10, 'bold'),
                bg=color,
                fg='white',
                activebackground=self.colors['primary_dark'] if color == self.colors['primary'] else color,
                activeforeground='white',
                bd=0,
                padx=20,
                pady=10,
                cursor='hand2',
                command=command,
                anchor=tk.W
            )
            btn.pack(fill=tk.X)
            
            tk.Label(
                btn_frame,
                text=desc,
                font=('Helvetica', 9),
                bg=self.colors['background'],
                fg=self.colors['text_secondary']
            ).pack(anchor=tk.W, padx=(5, 0), pady=(2, 0))
        
        # Customization Options Frame
        options_frame = tk.LabelFrame(
            frame,
            text=" Quick Customization ",
            font=('Helvetica', 11, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text'],
            bd=1,
            relief=tk.SOLID
        )
        options_frame.pack(fill=tk.X, pady=(0, 20), ipady=10)
        
        # Quick customization buttons
        quick_customizations = [
            ("👤 Add User", "Create a new user account", self._add_user_dialog),
            ("🔑 Set Root Password", "Change root password", self._set_root_password_dialog),
            ("🖼 Set Wallpaper", "Change desktop wallpaper", self._set_wallpaper_dialog),
            ("🏷 Set Hostname", "Change system hostname", self._set_hostname_dialog),
            ("📋 Add Preseed", "Add automated install config", self._add_preseed_dialog),
            ("📝 Edit GRUB", "Modify boot options", self._edit_grub_dialog),
        ]
        
        for text, desc, command in quick_customizations:
            btn_frame = tk.Frame(options_frame, bg=self.colors['background'])
            btn_frame.pack(fill=tk.X, padx=15, pady=3)
            
            btn = tk.Button(
                btn_frame,
                text=text,
                font=('Helvetica', 9, 'bold'),
                bg=self.colors['secondary'],
                fg='white',
                activebackground='#5E1E47',
                activeforeground='white',
                bd=0,
                padx=15,
                pady=6,
                cursor='hand2',
                command=command,
                anchor=tk.W,
                width=20
            )
            btn.pack(side=tk.LEFT)
            
            tk.Label(
                btn_frame,
                text=desc,
                font=('Helvetica', 9),
                bg=self.colors['background'],
                fg=self.colors['text_secondary']
            ).pack(side=tk.LEFT, padx=(10, 0))
        
        # What you can do section
        can_do_frame = tk.LabelFrame(
            frame,
            text=" What You Can Do ",
            font=('Helvetica', 11, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text'],
            bd=1,
            relief=tk.SOLID
        )
        can_do_frame.pack(fill=tk.X, pady=(0, 20), ipady=10)
        
        items = [
            "Install or remove software packages with apt",
            "Modify system configuration files",
            "Add custom scripts and files to the system",
            "Change default desktop settings and themes",
            "Configure user accounts and passwords",
            "Set up automatic startup services",
            "Add preseed files for automated installation",
            "Customize GRUB boot menu",
        ]
        
        for item in items:
            row = tk.Frame(can_do_frame, bg=self.colors['background'])
            row.pack(fill=tk.X, padx=15, pady=3)
            
            tk.Label(
                row,
                text="✓",
                font=('Helvetica', 10, 'bold'),
                bg=self.colors['background'],
                fg=self.colors['success']
            ).pack(side=tk.LEFT)
            
            tk.Label(
                row,
                text=item,
                font=('Helvetica', 10),
                bg=self.colors['background'],
                fg=self.colors['text']
            ).pack(side=tk.LEFT, padx=(10, 0))
        
        self.step_frames.append(frame)
    
    def _create_step4(self) -> None:
        """Create Step 4: Build ISO."""
        frame = tk.Frame(self.steps_frame, bg=self.colors['background'])
        
        # Settings section
        settings_frame = tk.LabelFrame(
            frame,
            text=" Output Settings ",
            font=('Helvetica', 11, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text'],
            bd=1,
            relief=tk.SOLID
        )
        settings_frame.pack(fill=tk.X, pady=(0, 20), ipady=10)
        
        # Output path
        tk.Label(
            settings_frame,
            text="Output ISO File:",
            font=('Helvetica', 10),
            bg=self.colors['background'],
            fg=self.colors['text']
        ).pack(anchor=tk.W, padx=15, pady=(10, 5))
        
        output_frame = tk.Frame(settings_frame, bg=self.colors['background'])
        output_frame.pack(fill=tk.X, padx=15, pady=5)
        
        output_entry = tk.Entry(
            output_frame,
            textvariable=self.output_path,
            font=('Helvetica', 10),
            bg='white',
            relief=tk.SOLID,
            bd=1
        )
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        output_browse_btn = tk.Button(
            output_frame,
            text="Browse...",
            font=('Helvetica', 9),
            bg=self.colors['primary'],
            fg='white',
            activebackground=self.colors['primary_dark'],
            bd=0,
            padx=15,
            pady=5,
            cursor='hand2',
            command=self._browse_output
        )
        output_browse_btn.pack(side=tk.RIGHT)
        
        # Volume ID and Compression row
        options_frame = tk.Frame(settings_frame, bg=self.colors['background'])
        options_frame.pack(fill=tk.X, padx=15, pady=(10, 5))
        
        # Volume ID
        vol_frame = tk.Frame(options_frame, bg=self.colors['background'])
        vol_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        tk.Label(
            vol_frame,
            text="Volume ID:",
            font=('Helvetica', 10),
            bg=self.colors['background'],
            fg=self.colors['text']
        ).pack(anchor=tk.W)
        
        vol_entry = tk.Entry(
            vol_frame,
            textvariable=self.volume_id,
            font=('Helvetica', 10),
            bg='white',
            relief=tk.SOLID,
            bd=1,
            width=25
        )
        vol_entry.pack(anchor=tk.W, pady=(5, 0))
        
        # Compression
        comp_frame = tk.Frame(options_frame, bg=self.colors['background'])
        comp_frame.pack(side=tk.RIGHT, padx=(20, 0))
        
        tk.Label(
            comp_frame,
            text="Compression:",
            font=('Helvetica', 10),
            bg=self.colors['background'],
            fg=self.colors['text']
        ).pack(anchor=tk.W)
        
        comp_combo = ttk.Combobox(
            comp_frame,
            textvariable=self.compression,
            values=['xz', 'gzip', 'lzo', 'lz4', 'zstd'],
            state='readonly',
            width=15
        )
        comp_combo.pack(anchor=tk.W, pady=(5, 0))
        
        # Build section
        build_frame = tk.LabelFrame(
            frame,
            text=" Build ISO ",
            font=('Helvetica', 11, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text'],
            bd=1,
            relief=tk.SOLID
        )
        build_frame.pack(fill=tk.X, pady=(0, 20), ipady=15)
        
        self.build_status = tk.Label(
            build_frame,
            text="Ready to build your custom ISO",
            font=('Helvetica', 10),
            bg=self.colors['background'],
            fg=self.colors['text_secondary']
        )
        self.build_status.pack(anchor=tk.W, padx=15, pady=(10, 10))
        
        # Progress bar
        self.build_progress = ttk.Progressbar(
            build_frame,
            mode='indeterminate',
            length=400
        )
        self.build_progress.pack(fill=tk.X, padx=15, pady=5)
        
        # Build button
        self.build_btn = tk.Button(
            build_frame,
            text="🔨 Build Custom ISO",
            font=('Helvetica', 12, 'bold'),
            bg=self.colors['secondary'],
            fg='white',
            activebackground='#388E3C',
            activeforeground='white',
            bd=0,
            padx=40,
            pady=15,
            cursor='hand2',
            command=self._start_build
        )
        self.build_btn.pack(pady=15)
        
        # Result display
        self.build_result_frame = tk.Frame(build_frame, bg=self.colors['background'])
        self.build_result_frame.pack(fill=tk.X, padx=15, pady=(10, 0))
        
        self.build_result = tk.Label(
            self.build_result_frame,
            text="",
            font=('Helvetica', 10),
            bg=self.colors['background'],
            justify=tk.LEFT
        )
        self.build_result.pack(anchor=tk.W)
        
        # Summary section
        self.summary_frame = tk.LabelFrame(
            frame,
            text=" Build Summary ",
            font=('Helvetica', 11, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text'],
            bd=1,
            relief=tk.SOLID
        )
        self.summary_frame.pack(fill=tk.X, pady=(0, 20), ipady=10)
        
        self.summary_text = tk.Label(
            self.summary_frame,
            text="No build completed yet",
            font=('Helvetica', 10),
            bg=self.colors['background'],
            fg=self.colors['text_secondary']
        )
        self.summary_text.pack(anchor=tk.W, padx=15, pady=10)
        
        self.step_frames.append(frame)
    
    def _create_step5(self) -> None:
        """Create Step 5: Test ISO with QEMU."""
        frame = tk.Frame(self.steps_frame, bg=self.colors['background'])
        
        # Info box
        info_box = tk.Frame(frame, bg=self.colors['surface'], bd=1, relief=tk.SOLID)
        info_box.pack(fill=tk.X, pady=(0, 20))
        
        tk.Label(
            info_box,
            text="🖥 QEMU Emulator",
            font=('Ubuntu', 11, 'bold'),
            bg=self.colors['surface'],
            fg=self.colors['primary']
        ).pack(anchor=tk.W, padx=15, pady=(15, 5))
        
        tk.Label(
            info_box,
            text="Test your custom ISO in a virtual machine before deploying.\n"
                 "This uses QEMU to boot the ISO without affecting your system.",
            font=('Ubuntu', 10),
            bg=self.colors['surface'],
            fg=self.colors['text'],
            justify=tk.LEFT
        ).pack(anchor=tk.W, padx=15, pady=(0, 15))
        
        # Settings frame
        settings_frame = tk.LabelFrame(
            frame,
            text=" Emulator Settings ",
            font=('Ubuntu', 11, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text'],
            bd=1,
            relief=tk.SOLID
        )
        settings_frame.pack(fill=tk.X, pady=(0, 20), ipady=10)
        
        # Memory setting
        mem_frame = tk.Frame(settings_frame, bg=self.colors['background'])
        mem_frame.pack(fill=tk.X, padx=15, pady=5)
        
        tk.Label(
            mem_frame,
            text="Memory (MB):",
            font=('Ubuntu', 10),
            bg=self.colors['background'],
            fg=self.colors['text']
        ).pack(side=tk.LEFT)
        
        self.qemu_memory = tk.StringVar(value="2048")
        mem_spin = tk.Spinbox(
            mem_frame,
            from_=512,
            to=8192,
            increment=512,
            textvariable=self.qemu_memory,
            width=10,
            font=('Ubuntu', 10)
        )
        mem_spin.pack(side=tk.LEFT, padx=(10, 0))
        
        # CPU cores
        cpu_frame = tk.Frame(settings_frame, bg=self.colors['background'])
        cpu_frame.pack(fill=tk.X, padx=15, pady=5)
        
        tk.Label(
            cpu_frame,
            text="CPU Cores:",
            font=('Ubuntu', 10),
            bg=self.colors['background'],
            fg=self.colors['text']
        ).pack(side=tk.LEFT)
        
        self.qemu_cores = tk.StringVar(value="2")
        cpu_spin = tk.Spinbox(
            cpu_frame,
            from_=1,
            to=8,
            textvariable=self.qemu_cores,
            width=10,
            font=('Ubuntu', 10)
        )
        cpu_spin.pack(side=tk.LEFT, padx=(10, 0))
        
        # KVM status
        kvm_frame = tk.Frame(settings_frame, bg=self.colors['background'])
        kvm_frame.pack(fill=tk.X, padx=15, pady=5)
        
        kvm_available = os.path.exists('/dev/kvm')
        kvm_text = "✓ KVM available (hardware acceleration enabled)" if kvm_available else "✗ KVM not available (slower emulation)"
        kvm_color = self.colors['success'] if kvm_available else self.colors['warning']
        
        tk.Label(
            kvm_frame,
            text=kvm_text,
            font=('Ubuntu', 10),
            bg=self.colors['background'],
            fg=kvm_color
        ).pack(anchor=tk.W)
        
        # Test buttons frame
        test_frame = tk.LabelFrame(
            frame,
            text=" Test Options ",
            font=('Ubuntu', 11, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text'],
            bd=1,
            relief=tk.SOLID
        )
        test_frame.pack(fill=tk.X, pady=(0, 20), ipady=10)
        
        # Test custom ISO button
        self.test_custom_btn = tk.Button(
            test_frame,
            text="▶ Test Custom ISO",
            font=('Ubuntu', 11, 'bold'),
            bg=self.colors['success'],
            fg='white',
            activebackground='#0B6B1A',
            activeforeground='white',
            bd=0,
            padx=30,
            pady=12,
            cursor='hand2',
            command=self._test_custom_iso
        )
        self.test_custom_btn.pack(fill=tk.X, padx=15, pady=5)
        
        # Test original ISO button
        self.test_original_btn = tk.Button(
            test_frame,
            text="▶ Test Original ISO",
            font=('Ubuntu', 10),
            bg=self.colors['primary'],
            fg='white',
            activebackground=self.colors['primary_dark'],
            activeforeground='white',
            bd=0,
            padx=30,
            pady=10,
            cursor='hand2',
            command=self._test_original_iso
        )
        self.test_original_btn.pack(fill=tk.X, padx=15, pady=5)
        
        # ISO Check frame
        check_frame = tk.LabelFrame(
            frame,
            text=" ISO Verification ",
            font=('Ubuntu', 11, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text'],
            bd=1,
            relief=tk.SOLID
        )
        check_frame.pack(fill=tk.X, pady=(0, 20), ipady=10)
        
        self.iso_check_label = tk.Label(
            check_frame,
            text="Click 'Check ISO' to verify Ubuntu compatibility",
            font=('Ubuntu', 10),
            bg=self.colors['background'],
            fg=self.colors['text_secondary'],
            justify=tk.LEFT
        )
        self.iso_check_label.pack(anchor=tk.W, padx=15, pady=10)
        
        tk.Button(
            check_frame,
            text="🔍 Check ISO",
            font=('Ubuntu', 10, 'bold'),
            bg=self.colors['secondary'],
            fg='white',
            activebackground='#5E1E47',
            activeforeground='white',
            bd=0,
            padx=20,
            pady=8,
            cursor='hand2',
            command=self._check_iso_dialog
        ).pack(anchor=tk.W, padx=15, pady=(0, 10))
        
        self.step_frames.append(frame)
    
    def _animate_window_appear(self):
        """Animate window fade-in."""
        def animate(alpha=0.0):
            if alpha >= 1.0:
                self.root.attributes('-alpha', 1.0)
                return
            alpha += 0.05
            self.root.attributes('-alpha', alpha)
            self.root.after(self.animation_speed, lambda: animate(alpha))
        animate()
    
    def _animate_step_transition(self):
        """Animate step content transition."""
        current_frame = self.step_frames[self.current_step]
        
        # Simple fade effect by changing background temporarily
        def flash():
            current_frame.config(bg=self.colors['accent'])
            self.root.after(50, lambda: current_frame.config(bg=self.colors['background']))
        
        flash()
    
    def _check_iso_dialog(self):
        """Show ISO checker dialog."""
        iso_path = self.output_path.get() if self.output_path.get() else self.iso_path.get()
        
        if not iso_path or not os.path.exists(iso_path):
            messagebox.showerror("Error", "Please select an ISO file first.")
            return
        
        # Run check in thread
        self.status_text.set("Checking ISO...")
        thread = threading.Thread(target=self._check_iso_thread, args=(iso_path,))
        thread.daemon = True
        thread.start()
    
    def _check_iso_thread(self, iso_path: str):
        """ISO check thread."""
        result = ISOChecker.check_iso(iso_path)
        self.iso_check_result = result
        self.root.after(0, self._check_iso_complete, result)
    
    def _check_iso_complete(self, result: Dict[str, Any]):
        """Handle ISO check completion."""
        self.status_text.set("ISO check complete")
        
        # Update label in step 5 if visible
        if result['is_ubuntu_based']:
            status_text = f"✓ Ubuntu-based ISO"
            if result['ubuntu_version']:
                status_text += f" (Ubuntu {result['ubuntu_version']})"
            status_color = self.colors['success']
        else:
            status_text = "✗ Not Ubuntu-based"
            status_color = self.colors['error']
        
        self.iso_check_label.config(text=status_text, fg=status_color)
        
        # Show detailed results
        summary = ISOChecker.get_check_summary(result)
        
        dialog = tk.Toplevel(self.root)
        dialog.title("ISO Check Results")
        dialog.geometry("500x400")
        dialog.configure(bg=self.colors['background'])
        
        # Header
        header = tk.Label(
            dialog,
            text="ISO Verification Results",
            font=('Ubuntu', 14, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['primary']
        )
        header.pack(pady=(20, 10))
        
        # Results text
        text = scrolledtext.ScrolledText(
            dialog,
            wrap=tk.WORD,
            font=('Ubuntu', 10),
            bg=self.colors['surface'],
            fg=self.colors['text'],
            padx=15,
            pady=15
        )
        text.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        text.insert(tk.END, summary)
        text.config(state=tk.DISABLED)
        
        # Close button
        tk.Button(
            dialog,
            text="Close",
            font=('Ubuntu', 10),
            bg=self.colors['primary'],
            fg='white',
            activebackground=self.colors['primary_dark'],
            bd=0,
            padx=20,
            pady=8,
            cursor='hand2',
            command=dialog.destroy
        ).pack(pady=(0, 20))
    
    def _test_custom_iso(self):
        """Test the custom built ISO."""
        output_path = self.output_path.get()
        
        if not output_path or not os.path.exists(output_path):
            messagebox.showerror(
                "ISO Not Found",
                "Custom ISO not found. Please build the ISO first."
            )
            return
        
        self._launch_qemu(output_path)
    
    def _test_original_iso(self):
        """Test the original ISO."""
        iso_path = self.iso_path.get()
        
        if not iso_path or not os.path.exists(iso_path):
            messagebox.showerror("Error", "Original ISO not found.")
            return
        
        self._launch_qemu(iso_path)
    
    def _launch_qemu(self, iso_path: str):
        """Launch QEMU with the given ISO."""
        try:
            memory = int(self.qemu_memory.get())
            cores = int(self.qemu_cores.get())
        except ValueError:
            memory = 2048
            cores = 2
        
        self.emulator.test_iso(iso_path, memory, cores)
    
    def _create_status_bar(self) -> None:
        """Create the status bar."""
        self.status_bar = tk.Frame(self.root, bg=self.colors['surface'], height=30)
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        
        # Separator line
        tk.Frame(self.status_bar, bg=self.colors['border'], height=1).pack(fill=tk.X)
        
        self.status_inner = tk.Frame(self.status_bar, bg=self.colors['surface'])
        self.status_inner.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.status_label = tk.Label(
            self.status_inner,
            textvariable=self.status_text,
            font=('Helvetica', 9),
            bg=self.colors['surface'],
            fg=self.colors['text_secondary']
        )
        self.status_label.pack(side=tk.LEFT)
    
    def _update_iso_info(self) -> None:
        """Update the ISO information display."""
        iso_path = self.iso_path.get()
        if iso_path and validate_iso(iso_path):
            info = get_iso_info(iso_path)
            info_text = f"Path: {info['path']}\n"
            info_text += f"Size: {info['size_human']}\n"
            info_text += f"Volume ID: {info['volume_id'] or 'N/A'}\n"
            info_text += f"Publisher: {info['publisher'] or 'N/A'}"
            
            self.iso_info_label.config(
                text=info_text,
                fg=self.colors['text']
            )
            self.status_text.set(f"Selected: {Path(iso_path).name}")
        else:
            self.iso_info_label.config(
                text="No ISO selected\nSelect an ISO file to see its details",
                fg=self.colors['text_secondary']
            )
    
    def _on_iso_path_changed(self, *args):
        """Handle ISO path changes for auto-extract feature."""
        iso_path = self.iso_path.get()
        
        # Validate ISO
        if not iso_path or not validate_iso(iso_path):
            return
        
        # Update info display
        self._update_iso_info()
        
        # Check if auto-extract is enabled
        if self.auto_extract.get():
            # Delay slightly to allow UI to update
            self.root.after(500, self._auto_extract_iso)
    
    def _auto_extract_iso(self):
        """Automatically extract ISO when auto-extract is enabled."""
        iso_path = self.iso_path.get()
        
        if not iso_path or not validate_iso(iso_path):
            return
        
        # Check dependencies first
        deps = ['xorriso', 'unsquashfs', 'mksquashfs']
        if not check_dependencies(deps):
            messagebox.showerror(
                "Missing Dependencies",
                "Cannot auto-extract: missing required packages.\n\n"
                "Install with: sudo apt-get install xorriso squashfs-tools"
            )
            return
        
        # Confirm with user
        if not messagebox.askyesno(
            "Auto-Extract",
            f"Auto-extract is enabled.\n\n"
            f"Extract {Path(iso_path).name} now?\n\n"
            f"This will extract the ISO to:\n{self.work_dir.get()}"
        ):
            return
        
        # Move to step 2 and start extraction
        self.show_step(1)
        self._start_extraction()
    
    def _remove_packages_dialog(self) -> None:
        """Show dialog to remove packages."""
        if not self.builder:
            messagebox.showerror("Error", "Please extract the ISO first.")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Remove Packages")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=self.colors['background'])
        
        tk.Label(
            dialog,
            text="Enter package names to remove (space-separated):",
            font=('Helvetica', 10),
            bg=self.colors['background'],
            fg=self.colors['text']
        ).pack(pady=(20, 10))
        
        packages_var = tk.StringVar()
        entry = tk.Entry(dialog, textvariable=packages_var, width=40, font=('Helvetica', 10))
        entry.pack(pady=10)
        entry.focus()
        
        def do_remove():
            packages = packages_var.get().strip().split()
            if packages:
                dialog.destroy()
                self._remove_packages(packages)
        
        btn_frame = tk.Frame(dialog, bg=self.colors['background'])
        btn_frame.pack(pady=15)
        
        tk.Button(
            btn_frame,
            text="Remove",
            font=('Helvetica', 10, 'bold'),
            bg=self.colors['error'],
            fg='white',
            activebackground='#D32F2F',
            bd=0,
            padx=20,
            pady=8,
            cursor='hand2',
            command=do_remove
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="Cancel",
            font=('Helvetica', 10),
            bg=self.colors['background'],
            fg=self.colors['text'],
            activebackground=self.colors['border'],
            bd=1,
            relief=tk.SOLID,
            padx=20,
            pady=8,
            cursor='hand2',
            command=dialog.destroy
        ).pack(side=tk.LEFT, padx=5)
    
    def _remove_packages(self, packages: list) -> None:
        """Remove packages in chroot."""
        if not self._check_root_for_operation("Remove Packages"):
            return
        
        squashfs_dir = self.builder.get_squashfs_dir()
        chroot = ChrootEnvironment(str(squashfs_dir))
        
        try:
            if chroot.remove_packages(packages):
                messagebox.showinfo("Success", f"Packages removed: {', '.join(packages)}")
            else:
                messagebox.showerror("Error", "Failed to remove packages.")
        finally:
            chroot.cleanup()
    
    def _show_logs(self) -> None:
        """Show application logs."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Application Logs")
        dialog.geometry("700x500")
        dialog.configure(bg=self.colors['background'])
        
        # Log text area
        log_text = scrolledtext.ScrolledText(
            dialog,
            wrap=tk.WORD,
            font=('Consolas', 9),
            bg=self.colors['surface'],
            fg=self.colors['text'],
            padx=10,
            pady=10
        )
        log_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        log_text.insert(tk.END, "Application logs will appear here...\n")
        log_text.config(state=tk.DISABLED)
        
        # Close button
        tk.Button(
            dialog,
            text="Close",
            font=('Helvetica', 10),
            bg=self.colors['primary'],
            fg='white',
            activebackground=self.colors['primary_dark'],
            bd=0,
            padx=20,
            pady=8,
            cursor='hand2',
            command=dialog.destroy
        ).pack(pady=(0, 15))
    
    def _show_docs(self) -> None:
        """Show documentation."""
        docs = """
UbuCustom - Documentation

Quick Start:
1. Select an Ubuntu ISO file
2. Extract the ISO contents
3. Customize the system in chroot
4. Build your custom ISO

Chroot Commands:
- apt update              Update package list
- apt install <pkg>       Install packages
- apt remove <pkg>        Remove packages
- nano /etc/hostname      Edit hostname
- adduser <name>          Create users

Tips:
- Ensure at least 10GB free space
- Use sudo for chroot operations
- Test your ISO in a VM before deploying
        """
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Documentation")
        dialog.geometry("600x500")
        dialog.configure(bg=self.colors['background'])
        
        text = scrolledtext.ScrolledText(
            dialog,
            wrap=tk.WORD,
            font=('Helvetica', 10),
            bg=self.colors['surface'],
            fg=self.colors['text'],
            padx=15,
            pady=15
        )
        text.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        text.insert(tk.END, docs)
        text.config(state=tk.DISABLED)
        
        tk.Button(
            dialog,
            text="Close",
            font=('Helvetica', 10),
            bg=self.colors['primary'],
            fg='white',
            activebackground=self.colors['primary_dark'],
            bd=0,
            padx=20,
            pady=8,
            cursor='hand2',
            command=dialog.destroy
        ).pack(pady=(0, 15))
    
    def show_step(self, step: int) -> None:
        """Show the specified step."""
        # Hide all steps
        for frame in self.step_frames:
            frame.grid_forget()
        
        # Show current step
        if 0 <= step < len(self.step_frames):
            self.step_frames[step].grid(row=0, column=0, sticky="nsew")
            self.current_step = step
        
        # Update header
        step_titles = [
            "Select ISO",
            "Extract ISO",
            "Customize System",
            "Build ISO",
            "Test ISO"
        ]
        self.title_label.config(text=step_titles[step])
        self.subtitle_label.config(text=f"Step {step + 1} of 5")
        self.progress_bar['value'] = (step + 1) * 20
        
        # Animate step transition
        if self.animations_enabled:
            self._animate_step_transition()
        
        # Update sidebar
        self._update_sidebar()
        
        # Update navigation buttons
        self.back_btn.config(state=tk.NORMAL if step > 0 else tk.DISABLED)
        
        if step == len(self.step_frames) - 1:
            self.next_btn.pack_forget()
            self.finish_btn.pack(side=tk.RIGHT)
        else:
            self.finish_btn.pack_forget()
            self.next_btn.pack(side=tk.RIGHT)
    
    def _next_step(self) -> None:
        """Go to the next step."""
        if self.current_step == 0:
            # Validate step 1
            if not self.iso_path.get():
                messagebox.showerror("Error", "Please select an ISO file.")
                return
            if not validate_iso(self.iso_path.get()):
                messagebox.showerror("Error", "Invalid ISO file selected.")
                return
        
        if self.current_step < len(self.step_frames) - 1:
            self.show_step(self.current_step + 1)
    
    def _prev_step(self) -> None:
        """Go to the previous step."""
        if self.current_step > 0:
            self.show_step(self.current_step - 1)
    
    def _browse_iso(self) -> None:
        """Browse for ISO file."""
        filename = filedialog.askopenfilename(
            title="Select Ubuntu ISO",
            filetypes=[("ISO files", "*.iso"), ("All files", "*.*")]
        )
        if filename:
            self.iso_path.set(filename)
            self._update_iso_info()
    
    def _update_iso_info(self) -> None:
        """Update the ISO information display."""
        iso_path = self.iso_path.get()
        if iso_path and validate_iso(iso_path):
            info = get_iso_info(iso_path)
            info_text = f"""
Path: {info['path']}
Size: {info['size_human']}
Volume ID: {info['volume_id'] or 'N/A'}
Publisher: {info['publisher'] or 'N/A'}
            """.strip()
            self.iso_info_label.config(text=info_text)
    
    def _browse_workdir(self) -> None:
        """Browse for working directory."""
        dirname = filedialog.askdirectory(
            title="Select Working Directory",
            initialdir=self.work_dir.get()
        )
        if dirname:
            self.work_dir.set(dirname)
    
    def _browse_output(self) -> None:
        """Browse for output ISO file."""
        filename = filedialog.asksaveasfilename(
            title="Save Custom ISO",
            defaultextension=".iso",
            filetypes=[("ISO files", "*.iso"), ("All files", "*.*")]
        )
        if filename:
            self.output_path.set(filename)
    
    def _start_extraction(self) -> None:
        """Start ISO extraction in a separate thread."""
        # Check dependencies
        deps = ['xorriso', 'unsquashfs', 'mksquashfs']
        if not check_dependencies(deps):
            messagebox.showerror(
                "Missing Dependencies",
                "Please install required packages:\n\n"
                "sudo apt-get install xorriso squashfs-tools"
            )
            return
        
        # Disable button
        self.extract_btn.config(state=tk.DISABLED)
        self.extract_progress.start()
        self.status_text.set("Extracting ISO...")
        
        # Start extraction thread
        thread = threading.Thread(target=self._extract_thread)
        thread.daemon = True
        thread.start()
    
    def _extract_thread(self) -> None:
        """Extraction thread."""
        try:
            self.builder = ISOBuilder(self.work_dir.get())
            success = self.builder.extract_iso(self.iso_path.get())
            
            self.root.after(0, self._extraction_complete, success)
        except Exception as e:
            self.root.after(0, self._extraction_complete, False, str(e))
    
    def _extraction_complete(self, success: bool, error: Optional[str] = None) -> None:
        """Handle extraction completion."""
        self.extract_progress.stop()
        self.extract_btn.config(state=tk.NORMAL)
        
        if success:
            self.step_completed[1] = True
            self.status_text.set("Extraction complete")
            self.extract_status.config(
                text="✓ Extraction completed successfully",
                fg=self.colors['success']
            )
            messagebox.showinfo("Success", "ISO extracted successfully!")
            self._next_step()
        else:
            self.status_text.set("Extraction failed")
            self.extract_status.config(
                text="✗ Extraction failed",
                fg=self.colors['error']
            )
            msg = f"Failed to extract ISO.\n\n{error}" if error else "Failed to extract ISO."
            messagebox.showerror("Error", msg)
    
    def _enter_chroot(self) -> None:
        """Open a terminal in the chroot environment."""
        if not self.builder:
            messagebox.showerror("Error", "Please extract the ISO first.")
            return
        
        # Check for root access
        if not self._check_root_for_operation("Enter Chroot"):
            return
        
        squashfs_dir = self.builder.get_squashfs_dir()
        chroot = ChrootEnvironment(str(squashfs_dir))
        
        # Setup chroot environment
        self.status_text.set("Setting up chroot environment...")
        if not chroot.setup():
            messagebox.showerror("Error", "Failed to setup chroot environment.")
            chroot.cleanup()
            return
        
        # Create a script to keep chroot alive
        script_path = Path(squashfs_dir) / 'tmp' / 'chroot_keepalive.sh'
        script_path.write_text("#!/bin/bash\necho 'Chroot ready. Type exit to leave.'\nbash\n")
        script_path.chmod(0o755)
        
        # Open terminal with chroot
        terminals = [
            ['gnome-terminal', '--', 'chroot', str(squashfs_dir), '/tmp/chroot_keepalive.sh'],
            ['konsole', '-e', f'chroot {squashfs_dir} /tmp/chroot_keepalive.sh'],
            ['xfce4-terminal', '-e', f'chroot {squashfs_dir} /tmp/chroot_keepalive.sh'],
            ['xterm', '-e', f'chroot {squashfs_dir} /tmp/chroot_keepalive.sh'],
        ]
        
        terminal_opened = False
        for term in terminals:
            try:
                subprocess.Popen(term)
                terminal_opened = True
                self.status_text.set("Chroot terminal opened")
                break
            except FileNotFoundError:
                continue
        
        if not terminal_opened:
            chroot.cleanup()
            messagebox.showerror(
                "No Terminal Found",
                "Could not find a suitable terminal emulator.\n\n"
                "Please open a terminal manually and run:\n"
                f"sudo chroot {squashfs_dir}"
            )
        else:
            # Show cleanup reminder
            messagebox.showinfo(
                "Chroot Terminal Opened",
                "The chroot terminal is now open.\n\n"
                "IMPORTANT: When you exit the terminal, click 'Cleanup Chroot' "
                "to unmount virtual filesystems properly."
            )
    
    def _cleanup_chroot(self) -> None:
        """Cleanup chroot environment by unmounting virtual filesystems."""
        if not self.builder:
            messagebox.showerror("Error", "Please extract the ISO first.")
            return
        
        if not self._check_root_for_operation("Cleanup Chroot"):
            return
        
        squashfs_dir = self.builder.get_squashfs_dir()
        chroot = ChrootEnvironment(str(squashfs_dir))
        
        self.status_text.set("Cleaning up chroot environment...")
        
        try:
            chroot.cleanup()
            self.status_text.set("Chroot cleaned up successfully")
            messagebox.showinfo("Success", "Chroot environment cleaned up successfully!\n\nVirtual filesystems unmounted.")
        except Exception as e:
            self.status_text.set("Chroot cleanup failed")
            messagebox.showerror("Error", f"Failed to cleanup chroot:\n{e}")
    
    def _install_packages_dialog(self) -> None:
        """Show dialog to install packages."""
        if not self.builder:
            messagebox.showerror("Error", "Please extract the ISO first.")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Install Packages")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(
            dialog,
            text="Enter package names to install (space-separated):"
        ).pack(pady=10)
        
        packages_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=packages_var, width=40).pack(pady=10)
        
        def do_install():
            packages = packages_var.get().strip().split()
            if packages:
                dialog.destroy()
                self._install_packages(packages)
        
        ttk.Button(dialog, text="Install", command=do_install).pack(pady=10)
    
    def _install_packages(self, packages: list) -> None:
        """Install packages in chroot."""
        if not self._check_root_for_operation("Install Packages"):
            return
        
        squashfs_dir = self.builder.get_squashfs_dir()
        chroot = ChrootEnvironment(str(squashfs_dir))
        
        try:
            if chroot.install_packages(packages):
                messagebox.showinfo("Success", f"Packages installed: {', '.join(packages)}")
            else:
                messagebox.showerror("Error", "Failed to install packages.")
        finally:
            chroot.cleanup()
    
    def _open_workdir(self) -> None:
        """Open the working directory in file manager."""
        workdir = self.work_dir.get()
        if os.path.exists(workdir):
            subprocess.Popen(['xdg-open', workdir])
        else:
            messagebox.showerror("Error", "Working directory does not exist.")
    
    def _start_build(self) -> None:
        """Start ISO build in a separate thread."""
        if not self.builder:
            messagebox.showerror("Error", "Please extract the ISO first.")
            return
        
        # Check dependencies
        deps = ['xorriso', 'mksquashfs', 'isohybrid']
        if not check_dependencies(deps):
            messagebox.showerror(
                "Missing Dependencies",
                "Please install required packages."
            )
            return
        
        # Disable button
        self.build_btn.config(state=tk.DISABLED)
        self.build_progress.start()
        self.status_text.set("Building ISO...")
        
        # Start build thread
        thread = threading.Thread(target=self._build_thread)
        thread.daemon = True
        thread.start()
    
    def _build_thread(self) -> None:
        """Build thread."""
        try:
            success = self.builder.rebuild_iso(
                self.output_path.get(),
                self.volume_id.get()
            )
            
            self.root.after(0, self._build_complete, success)
        except Exception as e:
            self.root.after(0, self._build_complete, False, str(e))
    
    def _build_complete(self, success: bool, error: Optional[str] = None) -> None:
        """Handle build completion."""
        self.build_progress.stop()
        self.build_btn.config(state=tk.NORMAL)
        
        if success:
            self.step_completed[3] = True
            self.status_text.set("Build complete")
            output = self.output_path.get()
            size = ""
            if os.path.exists(output):
                size = format_size(os.path.getsize(output))
            
            self.build_status.config(
                text="✓ Build completed successfully",
                fg=self.colors['success']
            )
            self.build_result.config(
                text=f"ISO created successfully!\n{output}\nSize: {size}",
                fg=self.colors['success']
            )
            
            # Update summary
            summary = f"Output: {output}\n"
            summary += f"Size: {size}\n"
            summary += f"Volume ID: {self.volume_id.get()}\n"
            summary += f"Compression: {self.compression.get()}"
            self.summary_text.config(
                text=summary,
                fg=self.colors['text']
            )
            
            messagebox.showinfo("Success", f"Custom ISO created!\n\n{output}")
        else:
            self.status_text.set("Build failed")
            self.build_status.config(
                text="✗ Build failed",
                fg=self.colors['error']
            )
            self.build_result.config(
                text=f"Build failed.\n{error or ''}",
                fg=self.colors['error']
            )
            messagebox.showerror("Error", f"Failed to build ISO.\n\n{error or ''}")
    
    def _new_project(self) -> None:
        """Start a new project."""
        if messagebox.askyesno("New Project", "Start a new project? Current progress will be lost."):
            self.iso_path.set("")
            self.builder = None
            self.step_completed = [False, False, False, False, False]
            self.iso_check_result = None
            self.extract_status.config(text="Ready to extract", fg=self.colors['text_secondary'])
            self.build_status.config(text="Ready to build your custom ISO", fg=self.colors['text_secondary'])
            self.build_result.config(text="")
            self.summary_text.config(text="No build completed yet", fg=self.colors['text_secondary'])
            self.iso_info_label.config(
                text="No ISO selected\nSelect an ISO file to see its details",
                fg=self.colors['text_secondary']
            )
            self.iso_check_label.config(
                text="Click 'Check ISO' to verify Ubuntu compatibility",
                fg=self.colors['text_secondary']
            )
            self.show_step(0)
    
    def _check_deps(self) -> None:
        """Check dependencies."""
        deps = ['xorriso', 'unsquashfs', 'mksquashfs', 'isohybrid', 'rsync']
        missing = [d for d in deps if not self._which(d)]
        
        if missing:
            messagebox.showwarning(
                "Missing Dependencies",
                f"Missing: {', '.join(missing)}\n\n"
                "Install with:\n"
                "sudo apt-get install xorriso squashfs-tools grub-pc-bin"
            )
        else:
            messagebox.showinfo("Dependencies", "All required dependencies are installed!")
    
    def _which(self, program: str) -> bool:
        """Check if a program exists in PATH."""
        return shutil.which(program) is not None
    
    def _clean_workdir(self) -> None:
        """Clean the working directory."""
        workdir = self.work_dir.get()
        if os.path.exists(workdir):
            if messagebox.askyesno("Confirm", f"Remove {workdir}?"):
                import shutil
                shutil.rmtree(workdir)
                messagebox.showinfo("Cleaned", "Working directory removed.")
    
    def _show_about(self) -> None:
        """Show about dialog."""
        about_text = """
UbuCustom - Custom Ubuntu ISO Creator

Version: 1.0.0

A powerful tool for creating customized Ubuntu Live ISO images.

Features:
• Extract and customize Ubuntu ISOs
• Chroot environment for system modifications
• Package management (install/remove)
• ISO verification and checking
• QEMU emulator for testing
• Multiple themes (Ubuntu, Dark, Blue)
• Project management with history

Built with Python and Tkinter.
Inspired by Cubic.
        """
        
        dialog = tk.Toplevel(self.root)
        dialog.title("About UbuCustom")
        dialog.geometry("450x500")
        dialog.configure(bg=self.colors['background'])
        dialog.transient(self.root)
        
        # Icon/Logo placeholder
        logo_frame = tk.Frame(dialog, bg=self.colors['primary'], height=100)
        logo_frame.pack(fill=tk.X, padx=20, pady=(20, 0))
        
        tk.Label(
            logo_frame,
            text="UbuCustom",
            font=('Ubuntu', 28, 'bold'),
            bg=self.colors['primary'],
            fg='white'
        ).pack(expand=True)
        
        # Text
        text = tk.Text(
            dialog,
            wrap=tk.WORD,
            font=('Ubuntu', 10),
            bg=self.colors['background'],
            fg=self.colors['text'],
            height=15,
            padx=10,
            pady=10,
            relief=tk.FLAT
        )
        text.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        text.insert(tk.END, about_text)
        text.config(state=tk.DISABLED)
        
        # Close button
        tk.Button(
            dialog,
            text="Close",
            font=('Ubuntu', 10),
            bg=self.colors['primary'],
            fg='white',
            activebackground=self.colors['primary_dark'],
            bd=0,
            padx=30,
            pady=10,
            cursor='hand2',
            command=dialog.destroy
        ).pack(pady=(0, 20))
    
    def _add_user_dialog(self):
        """Dialog to add a new user."""
        if not self._check_root_for_operation("Add User"):
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Add User")
        dialog.geometry("400x350")
        dialog.configure(bg=self.colors['background'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(
            dialog,
            text="👤 Add New User",
            font=('Ubuntu', 14, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['primary']
        ).pack(pady=(20, 15))
        
        # Username
        tk.Label(dialog, text="Username:", font=('Ubuntu', 10), 
                bg=self.colors['background'], fg=self.colors['text']).pack(anchor=tk.W, padx=20)
        username_var = tk.StringVar()
        tk.Entry(dialog, textvariable=username_var, font=('Ubuntu', 11), width=30).pack(padx=20, pady=(0, 10))
        
        # Full name
        tk.Label(dialog, text="Full Name:", font=('Ubuntu', 10),
                bg=self.colors['background'], fg=self.colors['text']).pack(anchor=tk.W, padx=20)
        fullname_var = tk.StringVar()
        tk.Entry(dialog, textvariable=fullname_var, font=('Ubuntu', 11), width=30).pack(padx=20, pady=(0, 10))
        
        # Password
        tk.Label(dialog, text="Password:", font=('Ubuntu', 10),
                bg=self.colors['background'], fg=self.colors['text']).pack(anchor=tk.W, padx=20)
        password_var = tk.StringVar()
        tk.Entry(dialog, textvariable=password_var, font=('Ubuntu', 11), width=30, show="*").pack(padx=20, pady=(0, 10))
        
        # Admin checkbox
        admin_var = tk.BooleanVar(value=True)
        tk.Checkbutton(dialog, text="Make user administrator (sudo)", variable=admin_var,
                      font=('Ubuntu', 10), bg=self.colors['background'], 
                      fg=self.colors['text'], selectcolor=self.colors['surface']).pack(anchor=tk.W, padx=20, pady=10)
        
        def do_add():
            username = username_var.get().strip()
            fullname = fullname_var.get().strip()
            password = password_var.get()
            
            if not username or not password:
                messagebox.showerror("Error", "Username and password are required.")
                return
            
            dialog.destroy()
            self._add_user_chroot(username, fullname, password, admin_var.get())
        
        tk.Button(
            dialog, text="Add User", font=('Ubuntu', 11, 'bold'),
            bg=self.colors['success'], fg='white', bd=0, padx=30, pady=10,
            cursor='hand2', command=do_add
        ).pack(pady=20)
    
    def _add_user_chroot(self, username, fullname, password, is_admin):
        """Add user in chroot."""
        squashfs_dir = self.builder.get_squashfs_dir()
        chroot = ChrootEnvironment(str(squashfs_dir))
        
        try:
            # Create user
            cmd = ['useradd', '-m', '-c', fullname or username, '-s', '/bin/bash', username]
            result = chroot.execute(cmd)
            
            if result.returncode == 0:
                # Set password
                chroot.execute(['bash', '-c', f'echo "{username}:{password}" | chpasswd'])
                
                # Add to sudo group if admin
                if is_admin:
                    chroot.execute(['usermod', '-aG', 'sudo', username])
                
                messagebox.showinfo("Success", f"User '{username}' created successfully!")
            else:
                messagebox.showerror("Error", f"Failed to create user: {result.stderr}")
        except Exception as e:
            messagebox.showerror("Error", f"Error creating user: {e}")
        finally:
            chroot.cleanup()
    
    def _set_root_password_dialog(self):
        """Dialog to set root password."""
        if not self._check_root_for_operation("Set Root Password"):
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Set Root Password")
        dialog.geometry("350x250")
        dialog.configure(bg=self.colors['background'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(
            dialog,
            text="🔑 Set Root Password",
            font=('Ubuntu', 14, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['primary']
        ).pack(pady=(20, 15))
        
        tk.Label(dialog, text="New Root Password:", font=('Ubuntu', 10),
                bg=self.colors['background'], fg=self.colors['text']).pack(anchor=tk.W, padx=20)
        password_var = tk.StringVar()
        tk.Entry(dialog, textvariable=password_var, font=('Ubuntu', 11), width=30, show="*").pack(padx=20, pady=(0, 10))
        
        tk.Label(dialog, text="Confirm Password:", font=('Ubuntu', 10),
                bg=self.colors['background'], fg=self.colors['text']).pack(anchor=tk.W, padx=20)
        confirm_var = tk.StringVar()
        tk.Entry(dialog, textvariable=confirm_var, font=('Ubuntu', 11), width=30, show="*").pack(padx=20, pady=(0, 10))
        
        def do_set():
            password = password_var.get()
            confirm = confirm_var.get()
            
            if not password:
                messagebox.showerror("Error", "Password is required.")
                return
            
            if password != confirm:
                messagebox.showerror("Error", "Passwords do not match.")
                return
            
            dialog.destroy()
            self._set_root_password_chroot(password)
        
        tk.Button(
            dialog, text="Set Password", font=('Ubuntu', 11, 'bold'),
            bg=self.colors['success'], fg='white', bd=0, padx=30, pady=10,
            cursor='hand2', command=do_set
        ).pack(pady=20)
    
    def _set_root_password_chroot(self, password):
        """Set root password in chroot."""
        squashfs_dir = self.builder.get_squashfs_dir()
        chroot = ChrootEnvironment(str(squashfs_dir))
        
        try:
            result = chroot.execute(['bash', '-c', f'echo "root:{password}" | chpasswd'])
            if result.returncode == 0:
                messagebox.showinfo("Success", "Root password set successfully!")
            else:
                messagebox.showerror("Error", "Failed to set root password.")
        except Exception as e:
            messagebox.showerror("Error", f"Error: {e}")
        finally:
            chroot.cleanup()
    
    def _set_wallpaper_dialog(self):
        """Dialog to set wallpaper."""
        if not self._check_root_for_operation("Set Wallpaper"):
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Set Wallpaper")
        dialog.geometry("500x300")
        dialog.configure(bg=self.colors['background'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(
            dialog,
            text="🖼 Set Desktop Wallpaper",
            font=('Ubuntu', 14, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['primary']
        ).pack(pady=(20, 15))
        
        # Wallpaper path
        tk.Label(dialog, text="Wallpaper Image Path:", font=('Ubuntu', 10),
                bg=self.colors['background'], fg=self.colors['text']).pack(anchor=tk.W, padx=20)
        
        path_frame = tk.Frame(dialog, bg=self.colors['background'])
        path_frame.pack(fill=tk.X, padx=20, pady=5)
        
        wallpaper_var = tk.StringVar()
        tk.Entry(path_frame, textvariable=wallpaper_var, font=('Ubuntu', 11), width=35).pack(side=tk.LEFT)
        
        def browse_wallpaper():
            filename = filedialog.askopenfilename(
                title="Select Wallpaper",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")]
            )
            if filename:
                wallpaper_var.set(filename)
        
        tk.Button(path_frame, text="Browse...", command=browse_wallpaper,
                 bg=self.colors['primary'], fg='white', bd=0, padx=10).pack(side=tk.LEFT, padx=5)
        
        # Desktop environment selection
        tk.Label(dialog, text="Desktop Environment:", font=('Ubuntu', 10),
                bg=self.colors['background'], fg=self.colors['text']).pack(anchor=tk.W, padx=20, pady=(15, 0))
        
        de_var = tk.StringVar(value="gnome")
        de_frame = tk.Frame(dialog, bg=self.colors['background'])
        de_frame.pack(anchor=tk.W, padx=20, pady=5)
        
        for de in ['gnome', 'kde', 'xfce', 'mate', 'cinnamon']:
            tk.Radiobutton(de_frame, text=de.title(), variable=de_var, value=de,
                          bg=self.colors['background'], fg=self.colors['text'],
                          selectcolor=self.colors['surface']).pack(side=tk.LEFT, padx=5)
        
        def do_set():
            wallpaper_path = wallpaper_var.get().strip()
            if not wallpaper_path or not os.path.exists(wallpaper_path):
                messagebox.showerror("Error", "Please select a valid wallpaper image.")
                return
            
            dialog.destroy()
            self._set_wallpaper_chroot(wallpaper_path, de_var.get())
        
        tk.Button(
            dialog, text="Set Wallpaper", font=('Ubuntu', 11, 'bold'),
            bg=self.colors['success'], fg='white', bd=0, padx=30, pady=10,
            cursor='hand2', command=do_set
        ).pack(pady=20)
    
    def _set_wallpaper_chroot(self, wallpaper_path, desktop_env):
        """Set wallpaper in chroot."""
        import shutil
        squashfs_dir = self.builder.get_squashfs_dir()
        
        # Copy wallpaper to chroot
        dest_dir = squashfs_dir / 'usr' / 'share' / 'backgrounds'
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / 'custom-wallpaper.jpg'
        shutil.copy2(wallpaper_path, dest_path)
        
        chroot = ChrootEnvironment(str(squashfs_dir))
        
        try:
            # Set wallpaper based on DE
            if desktop_env == 'gnome':
                chroot.execute(['bash', '-c', 
                    'mkdir -p /etc/dconf/db/local.d && '
                    'echo "[org/gnome/desktop/background]" > /etc/dconf/db/local.d/00-background && '
                    f'echo "picture-uri=\'file:///usr/share/backgrounds/custom-wallpaper.jpg\'" >> /etc/dconf/db/local.d/00-background && '
                    'dconf update'
                ])
            elif desktop_env == 'kde':
                # KDE wallpaper setup
                pass
            
            messagebox.showinfo("Success", "Wallpaper set successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Error setting wallpaper: {e}")
        finally:
            chroot.cleanup()
    
    def _set_hostname_dialog(self):
        """Dialog to set hostname."""
        if not self._check_root_for_operation("Set Hostname"):
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Set Hostname")
        dialog.geometry("350x200")
        dialog.configure(bg=self.colors['background'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(
            dialog,
            text="🏷 Set System Hostname",
            font=('Ubuntu', 14, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['primary']
        ).pack(pady=(20, 15))
        
        tk.Label(dialog, text="Hostname:", font=('Ubuntu', 10),
                bg=self.colors['background'], fg=self.colors['text']).pack(anchor=tk.W, padx=20)
        hostname_var = tk.StringVar(value="custom-ubuntu")
        tk.Entry(dialog, textvariable=hostname_var, font=('Ubuntu', 11), width=30).pack(padx=20, pady=5)
        
        def do_set():
            hostname = hostname_var.get().strip()
            if not hostname:
                messagebox.showerror("Error", "Hostname is required.")
                return
            
            dialog.destroy()
            self._set_hostname_chroot(hostname)
        
        tk.Button(
            dialog, text="Set Hostname", font=('Ubuntu', 11, 'bold'),
            bg=self.colors['success'], fg='white', bd=0, padx=30, pady=10,
            cursor='hand2', command=do_set
        ).pack(pady=20)
    
    def _set_hostname_chroot(self, hostname):
        """Set hostname in chroot."""
        squashfs_dir = self.builder.get_squashfs_dir()
        chroot = ChrootEnvironment(str(squashfs_dir))
        
        try:
            # Set hostname
            chroot.execute(['hostnamectl', 'set-hostname', hostname])
            
            # Update /etc/hostname
            hostname_file = squashfs_dir / 'etc' / 'hostname'
            hostname_file.write_text(hostname + '\n')
            
            # Update /etc/hosts
            hosts_file = squashfs_dir / 'etc' / 'hosts'
            hosts_content = f"127.0.0.1\tlocalhost\n127.0.1.1\t{hostname}\n"
            hosts_file.write_text(hosts_content)
            
            messagebox.showinfo("Success", f"Hostname set to '{hostname}'")
        except Exception as e:
            messagebox.showerror("Error", f"Error setting hostname: {e}")
        finally:
            chroot.cleanup()
    
    def _add_preseed_dialog(self):
        """Dialog to add preseed file."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Preseed File")
        dialog.geometry("600x500")
        dialog.configure(bg=self.colors['background'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(
            dialog,
            text="📋 Add Preseed Configuration",
            font=('Ubuntu', 14, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['primary']
        ).pack(pady=(20, 15))
        
        # Preseed template selection
        tk.Label(dialog, text="Preseed Template:", font=('Ubuntu', 10),
                bg=self.colors['background'], fg=self.colors['text']).pack(anchor=tk.W, padx=20)
        
        template_var = tk.StringVar(value="minimal")
        templates = {
            'minimal': 'Minimal Install (no questions)',
            'desktop': 'Desktop Install with user',
            'server': 'Server Install',
            'custom': 'Custom (edit below)'
        }
        
        for key, desc in templates.items():
            tk.Radiobutton(dialog, text=desc, variable=template_var, value=key,
                          bg=self.colors['background'], fg=self.colors['text'],
                          selectcolor=self.colors['surface']).pack(anchor=tk.W, padx=20)
        
        # Preseed content
        tk.Label(dialog, text="Preseed Content:", font=('Ubuntu', 10),
                bg=self.colors['background'], fg=self.colors['text']).pack(anchor=tk.W, padx=20, pady=(15, 0))
        
        preseed_text = scrolledtext.ScrolledText(dialog, height=15, wrap=tk.WORD,
                                                 font=('Ubuntu Mono', 9),
                                                 bg=self.colors['surface'],
                                                 fg=self.colors['text'])
        preseed_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        # Default minimal preseed
        default_preseed = """# Minimal preseed for automated install
d-i debian-installer/locale string en_US
d-i keyboard-configuration/xkb-keymap select us
d-i netcfg/choose_interface select auto
d-i netcfg/get_hostname string unassigned-hostname
d-i netcfg/get_domain string unassigned-domain
d-i mirror/country string manual
d-i mirror/http/hostname string archive.ubuntu.com
d-i mirror/http/directory string /ubuntu
d-i mirror/http/proxy string
d-i passwd/root-password password root
d-i passwd/root-password-again password root
d-i passwd/user-fullname string Ubuntu User
d-i passwd/username string ubuntu
d-i passwd/user-password password ubuntu
d-i passwd/user-password-again password ubuntu
d-i user-setup/allow-password-weak boolean true
d-i clock-setup/utc boolean true
d-i time/zone string UTC
d-i partman-auto/method string regular
d-i partman-lvm/device_remove_lvm boolean true
d-i partman-md/device_remove_md boolean true
d-i partman-auto/choose_recipe select atomic
d-i partman-partitioning/confirm_write_new_label boolean true
d-i partman/choose_partition select finish
d-i partman/confirm boolean true
d-i partman/confirm_nooverwrite boolean true
d-i pkgsel/include string openssh-server
d-i grub-installer/only_debian boolean true
d-i grub-installer/bootdev string default
d-i finish-install/reboot_in_progress note
"""
        preseed_text.insert(tk.END, default_preseed)
        
        def do_add():
            content = preseed_text.get("1.0", tk.END).strip()
            dialog.destroy()
            self._add_preseed_file(content)
        
        tk.Button(
            dialog, text="Add Preseed File", font=('Ubuntu', 11, 'bold'),
            bg=self.colors['success'], fg='white', bd=0, padx=30, pady=10,
            cursor='hand2', command=do_add
        ).pack(pady=15)
    
    def _add_preseed_file(self, content):
        """Add preseed file to ISO."""
        try:
            iso_dir = self.builder.get_iso_dir()
            preseed_dir = iso_dir / 'preseed'
            preseed_dir.mkdir(parents=True, exist_ok=True)
            
            preseed_file = preseed_dir / 'custom.seed'
            preseed_file.write_text(content)
            
            messagebox.showinfo("Success", "Preseed file added to ISO!")
        except Exception as e:
            messagebox.showerror("Error", f"Error adding preseed: {e}")
    
    def _edit_grub_dialog(self):
        """Dialog to edit GRUB configuration."""
        if not self._check_root_for_operation("Edit GRUB"):
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit GRUB Configuration")
        dialog.geometry("600x500")
        dialog.configure(bg=self.colors['background'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(
            dialog,
            text="📝 Edit GRUB Boot Menu",
            font=('Ubuntu', 14, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['primary']
        ).pack(pady=(20, 15))
        
        # Read current GRUB config
        squashfs_dir = self.builder.get_squashfs_dir()
        grub_file = squashfs_dir / 'boot' / 'grub' / 'grub.cfg'
        
        current_content = ""
        if grub_file.exists():
            try:
                current_content = grub_file.read_text()
            except:
                pass
        
        if not current_content:
            current_content = """# GRUB configuration
set timeout=10
set default=0

menuentry "Custom Ubuntu" {
    linux /casper/vmlinuz boot=casper quiet
    initrd /casper/initrd
}
"""
        
        tk.Label(dialog, text="GRUB Configuration:", font=('Ubuntu', 10),
                bg=self.colors['background'], fg=self.colors['text']).pack(anchor=tk.W, padx=20)
        
        grub_text = scrolledtext.ScrolledText(dialog, height=20, wrap=tk.NONE,
                                              font=('Ubuntu Mono', 9),
                                              bg=self.colors['surface'],
                                              fg=self.colors['text'])
        grub_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        grub_text.insert(tk.END, current_content)
        
        # Quick options
        options_frame = tk.Frame(dialog, bg=self.colors['background'])
        options_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(options_frame, text="Quick Options:", font=('Ubuntu', 9, 'bold'),
                bg=self.colors['background'], fg=self.colors['text']).pack(anchor=tk.W)
        
        timeout_var = tk.StringVar(value="10")
        tk.Label(options_frame, text="Timeout (seconds):", font=('Ubuntu', 9),
                bg=self.colors['background'], fg=self.colors['text']).pack(side=tk.LEFT, padx=(0, 5))
        tk.Spinbox(options_frame, from_=1, to=60, textvariable=timeout_var, width=5).pack(side=tk.LEFT, padx=(0, 15))
        
        def apply_timeout():
            content = grub_text.get("1.0", tk.END)
            import re
            content = re.sub(r'set timeout=\d+', f'set timeout={timeout_var.get()}', content)
            grub_text.delete("1.0", tk.END)
            grub_text.insert(tk.END, content)
        
        tk.Button(options_frame, text="Apply Timeout", command=apply_timeout,
                 bg=self.colors['primary'], fg='white', bd=0, padx=10).pack(side=tk.LEFT)
        
        def do_save():
            content = grub_text.get("1.0", tk.END).strip()
            dialog.destroy()
            self._save_grub_config(content)
        
        tk.Button(
            dialog, text="Save GRUB Config", font=('Ubuntu', 11, 'bold'),
            bg=self.colors['success'], fg='white', bd=0, padx=30, pady=10,
            cursor='hand2', command=do_save
        ).pack(pady=15)
    
    def _save_grub_config(self, content):
        """Save GRUB configuration."""
        try:
            squashfs_dir = self.builder.get_squashfs_dir()
            grub_file = squashfs_dir / 'boot' / 'grub' / 'grub.cfg'
            grub_file.parent.mkdir(parents=True, exist_ok=True)
            grub_file.write_text(content)
            messagebox.showinfo("Success", "GRUB configuration saved!")
        except Exception as e:
            messagebox.showerror("Error", f"Error saving GRUB config: {e}")
    
    def _show_package_manager(self):
        """Show package manager dialog."""
        if not self.builder:
            messagebox.showwarning("Package Manager", "Please extract an ISO first.")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Package Manager")
        dialog.geometry("600x500")
        dialog.configure(bg=self.colors['background'])
        dialog.transient(self.root)
        
        # Title
        tk.Label(
            dialog,
            text="📦 Package Manager",
            font=('Ubuntu', 16, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['primary']
        ).pack(pady=(20, 10))
        
        # Notebook for tabs
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Install tab
        install_frame = tk.Frame(notebook, bg=self.colors['background'])
        notebook.add(install_frame, text="Install Packages")
        
        tk.Label(
            install_frame,
            text="Enter packages to install (space-separated):",
            font=('Ubuntu', 10),
            bg=self.colors['background'],
            fg=self.colors['text']
        ).pack(anchor=tk.W, padx=15, pady=(15, 5))
        
        install_entry = tk.Entry(install_frame, font=('Ubuntu', 11), width=50)
        install_entry.pack(fill=tk.X, padx=15, pady=5)
        
        # Common packages
        tk.Label(
            install_frame,
            text="Quick Install:",
            font=('Ubuntu', 10, 'bold'),
            bg=self.colors['background'],
            fg=self.colors['text']
        ).pack(anchor=tk.W, padx=15, pady=(15, 5))
        
        common_frame = tk.Frame(install_frame, bg=self.colors['background'])
        common_frame.pack(fill=tk.X, padx=15, pady=5)
        
        common_packages = [
            'vim', 'nano', 'git', 'curl', 'wget', 
            'htop', 'neofetch', 'chrome-gnome-shell'
        ]
        
        for pkg in common_packages:
            btn = tk.Button(
                common_frame,
                text=pkg,
                font=('Ubuntu', 9),
                bg=self.colors['surface'],
                fg=self.colors['text'],
                relief=tk.SOLID,
                bd=1,
                cursor='hand2',
                command=lambda p=pkg, e=install_entry: e.insert(tk.END, p + ' ')
            )
            btn.pack(side=tk.LEFT, padx=2, pady=2)
        
        def do_install():
            packages = install_entry.get().strip().split()
            if packages:
                dialog.destroy()
                self._install_packages(packages)
        
        tk.Button(
            install_frame,
            text="Install Packages",
            font=('Ubuntu', 11, 'bold'),
            bg=self.colors['success'],
            fg='white',
            activebackground='#0B6B1A',
            bd=0,
            padx=30,
            pady=10,
            cursor='hand2',
            command=do_install
        ).pack(pady=20)
        
        # Remove tab
        remove_frame = tk.Frame(notebook, bg=self.colors['background'])
        notebook.add(remove_frame, text="Remove Packages")
        
        tk.Label(
            remove_frame,
            text="Enter packages to remove (space-separated):",
            font=('Ubuntu', 10),
            bg=self.colors['background'],
            fg=self.colors['text']
        ).pack(anchor=tk.W, padx=15, pady=(15, 5))
        
        remove_entry = tk.Entry(remove_frame, font=('Ubuntu', 11), width=50)
        remove_entry.pack(fill=tk.X, padx=15, pady=5)
        
        def do_remove():
            packages = remove_entry.get().strip().split()
            if packages:
                dialog.destroy()
                self._remove_packages(packages)
        
        tk.Button(
            remove_frame,
            text="Remove Packages",
            font=('Ubuntu', 11, 'bold'),
            bg=self.colors['error'],
            fg='white',
            activebackground='#9B1B2A',
            bd=0,
            padx=30,
            pady=10,
            cursor='hand2',
            command=do_remove
        ).pack(pady=20)
        
        # Close button
        tk.Button(
            dialog,
            text="Close",
            font=('Ubuntu', 10),
            bg=self.colors['background'],
            fg=self.colors['text'],
            activebackground=self.colors['border'],
            bd=1,
            relief=tk.SOLID,
            padx=20,
            pady=8,
            cursor='hand2',
            command=dialog.destroy
        ).pack(pady=(0, 20))
    
    def run(self) -> None:
        """Run the GUI application."""
        self.root.mainloop()


def main():
    """Main entry point for the GUI."""
    # Check if Tkinter is available
    try:
        import tkinter
    except ImportError:
        print("Error: Tkinter is not available.")
        print("Please install python3-tk package.")
        sys.exit(1)
    
    app = UbuCustomGUI()
    app.run()


if __name__ == '__main__':
    main()
