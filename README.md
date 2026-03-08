# UbuCustom

A powerful Python-based tool for customizing Ubuntu ISOs, inspired by Cubic. Create your own personalized Ubuntu distribution with ease.

![UbuCustom](website/assets/screenshot.png)

## Features

- **ISO Extraction & Rebuilding**: Extract Ubuntu ISOs, customize the filesystem, and rebuild bootable ISOs
- **Chroot Environment**: Full chroot support for installing packages and making system changes
- **QEMU Integration**: Test your custom ISO without burning it to physical media
- **ISO Validation**: Built-in checker to verify Ubuntu authenticity and compatibility
- **Modern GUI**: Beautiful, Ubuntu-inspired interface with multiple themes
- **CLI Support**: Command-line interface for automation and scripting
- **Project Management**: Save and load project configurations
- **Multiple Themes**: Choose from 5 different UI themes (Ubuntu, Dark, Blue, Windows 95, VS Code)

## Requirements

### System Requirements
- Ubuntu 20.04 or later (recommended)
- Root privileges for ISO operations
- At least 10GB free disk space
- QEMU (optional, for ISO testing)

### Dependencies
```bash
sudo apt install python3 python3-tk squashfs-tools xorriso qemu-system-x86
```

## Installation

### From Source

1. Clone the repository:
```bash
git clone https://github.com/iuseowls-web/UbuCustom.git
cd UbuCustom
```

2. Make the script executable:
```bash
chmod +x ubucustom.py
```

3. Run with root privileges:
```bash
sudo ./ubucustom.py
```

### Using the Tool

**GUI Mode:**
```bash
sudo ./ubucustom.py
```

**CLI Mode:**
```bash
sudo ./ubucustom.py cli --iso /path/to/ubuntu.iso --output /path/to/custom.iso
```

## Usage

### Graphical Interface

1. **Launch the Application**: Run `sudo ./ubucustom.py`
2. **Select ISO**: Choose an Ubuntu ISO file to customize
3. **Extract**: Click "Extract ISO" to unpack the contents
4. **Customize**: Use the chroot terminal to install packages, modify settings, etc.
5. **Build**: Click "Build ISO" to create your custom ISO
6. **Test**: Optionally test with QEMU before deployment

### Command Line

```bash
# Basic usage
sudo ./ubucustom.py cli --iso ubuntu-22.04.iso --output custom.iso

# With custom working directory
sudo ./ubucustom.py cli --iso ubuntu.iso --work-dir /tmp/ubucustom-work --output custom.iso

# Show help
sudo ./ubucustom.py --help
```

### Customization Options

Inside the chroot environment, you can:

- Install/remove packages with `apt`
- Add custom files and configurations
- Modify system settings
- Change wallpapers and themes
- Add preseed scripts for automated installation
- Configure GRUB bootloader
- Customize user accounts and permissions

## Project Structure

```
UbuCustom/
├── ubucustom/
│   ├── __init__.py          # Package initialization
│   ├── core.py              # ISO building logic
│   ├── chroot.py            # Chroot environment management
│   ├── gui.py               # Graphical user interface
│   ├── cli.py               # Command-line interface
│   ├── emulator.py          # QEMU integration
│   ├── checker.py           # ISO validation
│   ├── utils.py             # Utility functions
│   └── themes.py            # Theme definitions
├── website/                  # Documentation website
├── ubucustom.py             # Main entry point
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Themes

UbuCustom includes 5 built-in themes:

1. **Ubuntu** - Default orange and white theme
2. **Dark** - Dark mode with light text
3. **Blue** - Professional blue gradient
4. **Windows 95** - Retro grey 3D styling
5. **VS Code** - Developer-friendly dark theme

Switch themes anytime from the menu bar → Themes.

## Safety Notes

⚠️ **Important**: This tool requires root privileges. Always:
- Use trusted ISO files
- Verify downloaded packages
- Test custom ISOs in a VM before deployment
- Backup important data

## Troubleshooting

### Common Issues

**"Failed to extract ISO"**
- Ensure `squashfs-tools` is installed
- Check that you have sufficient disk space
- Verify the ISO file is not corrupted

**"Chroot terminal not working"**
- Make sure virtual filesystems are mounted
- Try cleaning up chroot environment and retry
- Check terminal emulator availability

**"QEMU fails to start"**
- Install `qemu-system-x86` package
- Ensure KVM is available (`kvm-ok`)
- Check if virtualization is enabled in BIOS

## Development

### Running Tests

```bash
python3 -m pytest tests/
```

### Building from Source

The project uses standard Python 3.8+ with no external dependencies beyond the system packages.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Credits

**Created by**: Abdellah Agtaib

**Inspired by**: Cubic (Custom Ubuntu ISO Creator)

**Thanks to**: The Ubuntu community and all open-source contributors

## Support

- Issues: Report bugs on GitHub Issues
- Questions: Open a discussion on GitHub Discussions

## Changelog

### Version 1.0.0
- Initial release
- GUI and CLI interfaces
- QEMU integration
- ISO validation
- Multiple themes
- Project save/load functionality
- Chroot terminal with proper cleanup

---

Made with ❤️ for the Ubuntu community
