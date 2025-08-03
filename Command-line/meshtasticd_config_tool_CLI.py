#!/usr/bin/env python3
"""
Meshtastic Configuration Tool - CLI Version
Interactive command-line interface for configuring Meshtastic daemon on Raspberry Pi
Converted from GTK GUI to SSH-compatible CLI interface with exact menu structure
FIXED VERSION - Status updates and progress spinner issues resolved
"""

import os
import sys
import subprocess

def install_dependencies():
    """Install required dependencies before main imports"""
    print("Checking and installing dependencies...")
    
    dependencies = [
        ("python3-rich-click", "rich-click"),
        ("python3-yaml", "PyYAML")
    ]
    
    for apt_package, import_name in dependencies:
        try:
            # Try to import the package first
            if import_name == "rich-click":
                import rich_click
            elif import_name == "PyYAML":
                import yaml
            print(f"✓ {import_name} is already installed")
        except ImportError:
            print(f"Installing {import_name}...")
            try:
                result = subprocess.run(
                    ["sudo", "apt", "install", "-y", apt_package],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    print(f"✓ {import_name} installed successfully")
                else:
                    print(f"✗ Failed to install {import_name}")
                    print(f"Error: {result.stderr}")
                    sys.exit(1)
            except subprocess.TimeoutExpired:
                print(f"✗ Timeout installing {import_name}")
                sys.exit(1)
            except Exception as e:
                print(f"✗ Error installing {import_name}: {e}")
                sys.exit(1)

# Install dependencies first, before any other imports
install_dependencies()

import json
import shutil
import logging
import re
import threading
import queue
import time
import select
import signal
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple, List, Callable, Any
from dataclasses import dataclass
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, Future
import contextlib

# Third-party imports (now guaranteed to be available)
import rich_click as click
import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.live import Live
from rich.layout import Layout
from rich.tree import Tree
from rich.columns import Columns
from rich.align import Align

# Configuration constants (matching original script)
REPO_DIR = "/etc/apt/sources.list.d"
GPG_DIR = "/etc/apt/trusted.gpg.d"
OS_VERSION = "Raspbian_12"
REPO_PREFIX = "network:Meshtastic"
PKG_NAME = "meshtasticd"
CONFIG_DIR = "/etc/meshtasticd"
BACKUP_DIR = "/etc/meshtasticd_backups"
LOG_FILE = "/var/log/meshtastic_installer.log"

# Initialize Rich console
console = Console()

class StatusType(Enum):
    """Status types for indicators"""
    CHECKING = "checking"
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

@dataclass
class AppConfig:
    """Centralized configuration for the application"""
    REPO_DIR: str = "/etc/apt/sources.list.d"
    GPG_DIR: str = "/etc/apt/trusted.gpg.d"
    OS_VERSION: str = "Raspbian_12"
    REPO_PREFIX: str = "network:Meshtastic"
    PKG_NAME: str = "meshtasticd"
    CONFIG_DIR: str = "/etc/meshtasticd"
    BACKUP_DIR: str = "/etc/meshtasticd_backups"
    LOG_FILE: str = "/var/log/meshtastic_installer.log"
    BOOT_CONFIG_FILE: str = "/boot/firmware/config.txt"
    DEFAULT_TIMEOUT: int = 300
    APT_TIMEOUT: int = 600
    CLI_TIMEOUT: int = 30
    MAX_RETRIES: int = 3

class OperationResult:
    """Result of an operation with success status and message"""
    def __init__(self, success: bool, message: str = "", details: str = ""):
        self.success = success
        self.message = message
        self.details = details

class MeshtasticError(Exception):
    """Base exception for Meshtastic operations"""
    pass

class ConfigurationError(MeshtasticError):
    """Configuration related errors"""
    pass

class InstallationError(MeshtasticError):
    """Installation related errors"""
    pass

class HardwareError(MeshtasticError):
    """Hardware detection errors"""
    pass

class LoggingManager:
    """Enhanced logging with queue support for CLI"""
    
    def __init__(self, log_level=logging.INFO):
        self.output_queue = queue.Queue()
        self.setup_logging(log_level)
        
    def setup_logging(self, level):
        """Setup logging configuration"""
        class QueueHandler(logging.Handler):
            def __init__(self, queue):
                super().__init__()
                self.queue = queue
                
            def emit(self, record):
                try:
                    msg = record.getMessage()
                    self.queue.put(msg)
                except Exception:
                    pass
        
        # Clear any existing handlers
        logging.getLogger().handlers.clear()
        
        # Setup logging with queue handler
        queue_handler = QueueHandler(self.output_queue)
        queue_handler.setLevel(logging.INFO)
        
        # Try to add file handler too
        handlers = [queue_handler]
        try:
            os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
            file_handler = logging.FileHandler(LOG_FILE)
            file_handler.setLevel(logging.INFO)
            file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(file_formatter)
            handlers.append(file_handler)
        except:
            pass
        
        logging.basicConfig(
            level=logging.INFO,
            handlers=handlers,
            force=True
        )
        
        logging.info("Meshtastic CLI started - logging system initialized")
    
    def get_messages(self) -> List[str]:
        """Get all pending log messages"""
        messages = []
        try:
            while True:
                try:
                    message = self.output_queue.get_nowait()
                    messages.append(message)
                except queue.Empty:
                    break
        except Exception as e:
            console.print(f"Error processing output queue: {e}")
        return messages

class HardwareDetector:
    """Handles hardware detection for Pi model and HATs"""
    
    def __init__(self):
        self.pi_model: Optional[str] = None
        self.hat_info: Optional[Dict[str, str]] = None
        self._detect_hardware()
    
    def _detect_hardware(self):
        """Detect Pi model and HAT information"""
        try:
            self._detect_pi_model()
            self._detect_hat()
        except Exception as e:
            logging.warning(f"Hardware detection error: {e}")
    
    def _detect_pi_model(self):
        """Detect Raspberry Pi model"""
        try:
            if os.path.exists("/proc/device-tree/model"):
                with open("/proc/device-tree/model", "r") as f:
                    self.pi_model = f.read().strip().replace('\x00', '')
        except Exception as e:
            logging.warning(f"Failed to detect Pi model: {e}")
    
    def _detect_hat(self):
        """Detect HAT information"""
        try:
            hat_info = {}
            if os.path.exists("/proc/device-tree/hat/product"):
                with open("/proc/device-tree/hat/product", "r") as f:
                    hat_info["product"] = f.read().strip().replace('\x00', '')
            if os.path.exists("/proc/device-tree/hat/vendor"):
                with open("/proc/device-tree/hat/vendor", "r") as f:
                    hat_info["vendor"] = f.read().strip().replace('\x00', '')
            if hat_info:
                self.hat_info = hat_info
        except Exception as e:
            logging.warning(f"Failed to detect HAT: {e}")
    
    def is_pi5(self) -> bool:
        """Check if this is a Raspberry Pi 5"""
        return self.pi_model and "Raspberry Pi 5" in self.pi_model
    
    def get_hardware_info(self) -> Dict[str, str]:
        """Get formatted hardware information"""
        return {
            "pi_model": self.pi_model or "Unknown",
            "hat_vendor": self.hat_info.get("vendor", "Unknown") if self.hat_info else "None",
            "hat_product": self.hat_info.get("product", "Unknown") if self.hat_info else "None",
        }

class SystemManager:
    """Handles all system-level operations"""
    
    def __init__(self, config: AppConfig):
        self.config = config
    
    def run_command(self, cmd: List[str], timeout: int = None, input_text: str = None) -> subprocess.CompletedProcess:
        """Run a command with proper error handling"""
        timeout = timeout or self.config.DEFAULT_TIMEOUT
        
        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=timeout,
                input=input_text
            )
            return result
        except subprocess.TimeoutExpired as e:
            raise MeshtasticError(f"Command timed out: {' '.join(cmd)}")
        except Exception as e:
            raise MeshtasticError(f"Command failed: {e}")
    
    def run_sudo_command(self, cmd: List[str], timeout: int = None, input_text: str = None) -> subprocess.CompletedProcess:
        """Run a command with sudo"""
        sudo_cmd = ["sudo"] + cmd
        return self.run_command(sudo_cmd, timeout, input_text)
    
    def check_package_installed(self, package_name: str) -> bool:
        """Check if a package is installed via dpkg"""
        try:
            result = self.run_command(["dpkg", "-l", package_name])
            return result.returncode == 0 and "ii" in result.stdout
        except:
            return False
    
    def check_service_enabled(self, service_name: str) -> bool:
        """Check if a service is enabled"""
        try:
            result = self.run_command(["systemctl", "is-enabled", service_name])
            return result.returncode == 0 and result.stdout.strip() == "enabled"
        except:
            return False
    
    def check_service_active(self, service_name: str) -> bool:
        """Check if a service is active"""
        try:
            result = self.run_command(["systemctl", "is-active", service_name])
            return result.returncode == 0 and result.stdout.strip() == "active"
        except:
            return False
    
    def backup_file(self, filepath: str) -> str:
        """Create a backup of a file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{filepath}.backup_{timestamp}"
        
        try:
            self.run_sudo_command(["cp", filepath, backup_path])
            return backup_path
        except Exception as e:
            raise ConfigurationError(f"Failed to backup {filepath}: {e}")
    
    def check_and_fix_apt_locks(self):
        """Check for and attempt to fix apt lock issues"""
        try:
            logging.info("Checking for apt lock issues...")
            
            result = self.run_command(["sudo", "dpkg", "--audit"])
            if result.returncode != 0 or result.stdout.strip():
                logging.warning("⚠️ dpkg appears to be interrupted, attempting to fix...")
                result = self.run_command(["sudo", "dpkg", "--configure", "-a"], 
                                      input_text="n\n", timeout=60)
                if result.returncode == 0:
                    logging.info("✅ dpkg configuration completed")
                else:
                    logging.warning(f"⚠️ dpkg configure had issues: {result.stderr}")
            
            lock_files = [
                "/var/lib/dpkg/lock",
                "/var/lib/dpkg/lock-frontend", 
                "/var/cache/apt/archives/lock"
            ]
            
            locks_found = []
            for lock_file in lock_files:
                if os.path.exists(lock_file):
                    try:
                        result = self.run_command(["sudo", "lsof", lock_file])
                        if result.returncode == 0 and result.stdout.strip():
                            locks_found.append(lock_file)
                            logging.warning(f"⚠️ Lock file {lock_file} is held by process")
                    except:
                        pass
            
            if locks_found:
                logging.info("Attempting to kill apt-related processes...")
                self.run_command(["sudo", "killall", "-9", "apt", "apt-get", "dpkg"])
                
                time.sleep(2)
                
                for lock_file in locks_found:
                    try:
                        result = self.run_command(["sudo", "lsof", lock_file])
                        if result.returncode != 0:
                            self.run_command(["sudo", "rm", "-f", lock_file])
                            logging.info(f"✅ Removed stale lock file: {lock_file}")
                    except:
                        pass
            
            return True
            
        except Exception as e:
            logging.error(f"Error checking/fixing apt locks: {e}")
            return False

    def safe_apt_command(self, cmd_args, timeout=300, interactive_input=None):
        """Run apt command with better error handling and lock detection"""
        max_retries = 3
        retry_delay = 10
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logging.info(f"Retry attempt {attempt + 1}/{max_retries} for apt command...")
                    self.check_and_fix_apt_locks()
                    time.sleep(retry_delay)
                
                if interactive_input:
                    result = self.run_command(cmd_args, timeout=timeout, input_text=interactive_input)
                else:
                    result = self.run_command(cmd_args, timeout=timeout)
                
                if "Could not get lock" in result.stderr or "dpkg was interrupted" in result.stderr:
                    if attempt < max_retries - 1:
                        logging.warning(f"⚠️ Lock detected on attempt {attempt + 1}, will retry...")
                        continue
                    else:
                        logging.error("❌ Failed to acquire apt lock after all retries")
                        return result
                
                return result
                
            except subprocess.TimeoutExpired:
                logging.warning(f"⚠️ Command timed out on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    self.run_command(["sudo", "killall", "-9", "apt", "apt-get", "dpkg"])
                    continue
                else:
                    logging.error("❌ Command timed out after all retries")
                    raise
                    
            except Exception as e:
                logging.error(f"Error running apt command: {e}")
                if attempt < max_retries - 1:
                    continue
                else:
                    raise
        
        return None

class StatusChecker:
    """Handles all status checking operations"""
    
    def __init__(self, config: AppConfig, system_manager: SystemManager, hardware: HardwareDetector):
        self.config = config
        self.system = system_manager
        self.hardware = hardware
    
    def check_meshtasticd_status(self) -> bool:
        """Check if meshtasticd is installed"""
        try:
            # Check via dpkg
            dpkg_installed = self.system.check_package_installed(self.config.PKG_NAME)
            
            # Check if binary exists
            binary_paths = ["/usr/sbin/meshtasticd", "/usr/bin/meshtasticd"]
            binary_exists = any(os.path.exists(path) for path in binary_paths)
            
            # Check with which command
            which_found = False
            try:
                result = self.system.run_command(["which", self.config.PKG_NAME])
                which_found = result.returncode == 0
            except:
                pass
            
            return dpkg_installed or binary_exists or which_found
        except:
            return False
    
    def check_spi_status(self) -> bool:
        """Check if SPI is enabled"""
        # Check if devices exist
        devices_exist = os.path.exists("/dev/spidev0.0") or os.path.exists("/dev/spidev0.1")
        
        # Check if configured in boot config
        config_enabled = False
        try:
            with open(self.config.BOOT_CONFIG_FILE, "r") as f:
                config_content = f.read()
            has_spi_param = "dtparam=spi=on" in config_content
            has_spi_overlay = "dtoverlay=spi0-0cs" in config_content
            config_enabled = has_spi_param and has_spi_overlay
        except:
            pass
            
        return devices_exist and config_enabled
    
    def check_i2c_status(self) -> bool:
        """Check if I2C is enabled"""
        devices_exist = any(os.path.exists(f"/dev/i2c-{i}") for i in range(0, 10))
        
        config_enabled = False
        try:
            with open(self.config.BOOT_CONFIG_FILE, "r") as f:
                config_content = f.read()
            config_enabled = "dtparam=i2c_arm=on" in config_content
        except:
            pass
            
        return devices_exist and config_enabled
    
    def check_gps_uart_status(self) -> bool:
        """Check if GPS/UART is enabled"""
        try:
            with open(self.config.BOOT_CONFIG_FILE, "r") as f:
                config_content = f.read()
            
            has_uart_enabled = "enable_uart=1" in config_content
            
            if self.hardware.is_pi5():
                has_uart0_overlay = "dtoverlay=uart0" in config_content
                return has_uart_enabled and has_uart0_overlay
            else:
                return has_uart_enabled
        except:
            return False
    
    def check_hat_specific_status(self) -> bool:
        """Check if HAT specific options are configured"""
        if not self.hardware.hat_info or self.hardware.hat_info.get('product') != 'MeshAdv Mini':
            return False
            
        try:
            with open(self.config.BOOT_CONFIG_FILE, "r") as f:
                config_content = f.read()
                
            has_gpio_config = "gpio=4=op,dh" in config_content
            has_pps_config = "pps-gpio,gpiopin=17" in config_content
            
            return has_gpio_config and has_pps_config
        except:
            return False
    
    def check_hat_config_status(self) -> bool:
        """Check if HAT config file exists"""
        config_d_dir = f"{self.config.CONFIG_DIR}/config.d"
        if not os.path.exists(config_d_dir):
            return False
            
        try:
            config_files = list(Path(config_d_dir).glob("*.yaml"))
            return len(config_files) > 0
        except:
            return False
    
    def check_config_exists(self) -> bool:
        """Check if config file exists"""
        return (os.path.exists(f"{self.config.CONFIG_DIR}/config.yaml") or 
                os.path.exists(f"{self.config.CONFIG_DIR}/config.json"))
    
    def check_python_cli_status(self) -> bool:
        """Check if Meshtastic Python CLI is installed"""
        try:
            result = self.system.run_command(["meshtastic", "--version"])
            return result.returncode == 0
        except:
            try:
                result = self.system.run_command(["pipx", "list"])
                return "meshtastic" in result.stdout
            except:
                return False
    
    def check_lora_region_status(self) -> str:
        """Check current LoRa region setting"""
        try:
            if not self.check_python_cli_status():
                return "CLI Not Available"
                
            result = self.system.run_command(
                ["meshtastic", "--host", "localhost", "--get", "lora.region"],
                timeout=10
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                logging.info(f"Raw CLI output for region: '{output}'")
                
                region_map = {
                    "0": "UNSET", "1": "US", "2": "EU_433", "3": "EU_868",
                    "4": "CN", "5": "JP", "6": "ANZ", "7": "KR", "8": "TW",
                    "9": "RU", "10": "IN", "11": "NZ_865", "12": "TH",
                    "13": "UA_433", "14": "UA_868", "15": "MY_433",
                    "16": "MY_919", "17": "SG_923"
                }
                
                valid_regions = ["UNSET", "US", "EU_868", "EU_433", "ANZ", "CN", "IN", "JP", "KR", 
                               "MY_433", "MY_919", "RU", "SG_923", "TH", "TW", "UA_433", "UA_868"]
                
                lines = output.split('\n')
                for line in lines:
                    line = line.strip()
                    
                    if not line or any(skip in line.lower() for skip in ['connected', 'requesting', 'node info']):
                        continue
                    
                    if line in valid_regions:
                        return line
                    
                    if "lora.region:" in line:
                        parts = line.split(":", 1)
                        if len(parts) > 1:
                            value = parts[1].strip()
                            if value in valid_regions:
                                return value
                            if value in region_map:
                                return region_map[value]
                    
                    if line.isdigit() and line in region_map:
                        return region_map[line]
                
                return "Unknown"
            else:
                return "Error"
        except Exception as e:
            logging.error(f"Exception checking region status: {e}")
            return "Error"
    
    def check_avahi_status(self) -> bool:
        """Check if Avahi is installed and configured"""
        try:
            avahi_installed = self.system.check_package_installed("avahi-daemon")
            if not avahi_installed:
                return False
                
            service_file = "/etc/avahi/services/meshtastic.service"
            return os.path.exists(service_file)
        except:
            return False
    
    def check_meshtasticd_boot_status(self) -> bool:
        """Check if meshtasticd is enabled to start on boot"""
        return self.system.check_service_enabled(self.config.PKG_NAME)
    
    def check_meshtasticd_service_status(self) -> bool:
        """Check if meshtasticd service is currently running"""
        return self.system.check_service_active(self.config.PKG_NAME)

class ThreadManager:
    """Manages background operations with proper cleanup"""
    
    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="MeshtasticWorker")
        self.active_futures: List[Future] = []
    
    def submit_task(self, func: Callable, *args, **kwargs) -> Future:
        """Submit a task to the thread pool"""
        future = self.executor.submit(func, *args, **kwargs)
        self.active_futures.append(future)
        
        # Clean up completed futures
        self.active_futures = [f for f in self.active_futures if not f.done()]
        
        return future
    
    def shutdown(self, wait: bool = True):
        """Shutdown the thread pool"""
        self.executor.shutdown(wait=wait)

class ProgressDots:
    """Progress indication using dots - FIXED version"""
    
    def __init__(self, message: str, max_dots: int = 3):
        self.message = message
        self.max_dots = max_dots
        self.current_dots = 0
        self.running = False
        self.thread = None
        self._initial_message_printed = False
    
    def start(self):
        """Start the progress dots animation"""
        if self.running:
            return
            
        self.running = True
        self._initial_message_printed = False
        
        def animate():
            while self.running:
                if not self._initial_message_printed:
                    # Print initial message on first run
                    print(f"{self.message}", end="", flush=True)
                    self._initial_message_printed = True
                
                # Print a dot
                print(".", end="", flush=True)
                time.sleep(0.5)
                
                # Reset line after max dots
                self.current_dots = (self.current_dots + 1) % self.max_dots
                if self.current_dots == 0 and self.running:
                    # Clear dots and restart
                    print(f"\r{self.message}", end="", flush=True)
        
        self.thread = threading.Thread(target=animate, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop the progress dots animation"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        # Print newline to finish the line
        print()

class MeshtasticCLI:
    """Main CLI application class - FIXED VERSION"""
    
    def __init__(self):
        # Initialize core components
        self.config = AppConfig()
        self.system_manager = SystemManager(self.config)
        self.thread_manager = ThreadManager()
        self.hardware = HardwareDetector()
        self.status_checker = StatusChecker(self.config, self.system_manager, self.hardware)
        self.logging_manager = LoggingManager()
        
        # CLI state
        self.running = True
        self.status_cache = {}
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        console.print("\n[yellow]Shutting down gracefully...[/yellow]")
        self.running = False
        self.thread_manager.shutdown(wait=False)
        sys.exit(0)
    
    def force_status_refresh(self):
        """Force an immediate status refresh and display update - NEW METHOD"""
        console.print("[dim]Updating status...[/dim]")
        
        # Clear the status cache to force fresh checks
        self.status_cache.clear()
        
        # Perform fresh status checks
        self.update_status_indicators()
        
        console.print("[green]✓ Status updated[/green]")
    
    def show_header(self):
        """Show application header"""
        console.clear()
        header_text = Text("Meshtasticd Configuration Tool", style="bold blue")
        subtitle_text = Text("Interactive configuration management for Raspberry Pi", style="dim")
        
        panel = Panel(
            Align.center(f"{header_text}\n{subtitle_text}"),
            title="Welcome",
            border_style="blue"
        )
        console.print(panel)
        console.print()
    
    def show_hardware_info(self):
        """Display hardware information panel"""
        hardware_info = self.hardware.get_hardware_info()
        
        table = Table(title="Hardware Information", box=None)
        table.add_column("Property", style="cyan", width=15)
        table.add_column("Value", style="green")
        
        table.add_row("Raspberry Pi", hardware_info["pi_model"])
        
        if hardware_info["hat_vendor"] != "None":
            hat_text = f"{hardware_info['hat_vendor']} {hardware_info['hat_product']}"
            table.add_row("HAT Detected", hat_text)
        else:
            table.add_row("HAT Detected", "None")
        
        console.print(table)
        console.print()
    
    def update_status_indicators(self):
        """Update all status indicators and cache them"""
        progress = ProgressDots("Checking status")
        progress.start()
        
        try:
            self.status_cache = {
                "meshtasticd": self.status_checker.check_meshtasticd_status(),
                "spi": self.status_checker.check_spi_status(),
                "i2c": self.status_checker.check_i2c_status(),
                "gps_uart": self.status_checker.check_gps_uart_status(),
                "hat_specific": self.status_checker.check_hat_specific_status(),
                "hat_config": self.status_checker.check_hat_config_status(),
                "config_exists": self.status_checker.check_config_exists(),
                "python_cli": self.status_checker.check_python_cli_status(),
                "lora_region": self.status_checker.check_lora_region_status(),
                "avahi": self.status_checker.check_avahi_status(),
                "boot_enabled": self.status_checker.check_meshtasticd_boot_status(),
                "service_running": self.status_checker.check_meshtasticd_service_status(),
            }
        finally:
            progress.stop()
    
    def get_status_symbol(self, key: str) -> str:
        """Get status symbol for a given status key"""
        if key not in self.status_cache:
            return "[yellow]?[/yellow]"
        
        status = self.status_cache[key]
        
        if key == "lora_region":
            if status == "UNSET":
                return "[red]UNSET[/red]"
            elif status in ["US", "EU_868", "EU_433", "ANZ", "CN", "IN", "JP", "KR", 
                           "MY_433", "MY_919", "RU", "SG_923", "TH", "TW", "UA_433", "UA_868"]:
                return f"[green]{status}[/green]"
            elif status == "CLI Not Available":
                return "[red]CLI Required[/red]"
            elif status == "Error":
                return "[orange3]Error[/orange3]"
            else:
                return f"[blue]{status}[/blue]"
        else:
            if isinstance(status, bool):
                return "[green]YES[/green]" if status else "[red]NO[/red]"
                #return "[green]✓[/green]" if status else "[red]✗[/red]"
            else:
                return f"[yellow]{status}[/yellow]"
    
    def show_main_menu(self):
        """Display main menu exactly matching GUI structure"""
        self.show_header()
        self.show_hardware_info()
        
        # Configuration Options (matching GUI layout)
        config_table = Table(title="Configuration Options", box=None)
        config_table.add_column("Option", style="white", width=30)
        config_table.add_column("Status", style="white", width=15)
        
        config_options = [
            ("1. Install/Remove meshtasticd", "meshtasticd"),
            ("2. Enable SPI", "spi"),
            ("3. Enable I2C", "i2c"),
            ("4. Enable GPS/UART", "gps_uart"),
            ("5. Enable HAT Specific Options", "hat_specific"),
            ("6. Set HAT Config", "hat_config"),
            ("7. Edit Config", "config_exists"),
        ]
        
        for option, status_key in config_options:
            config_table.add_row(option, self.get_status_symbol(status_key))
        
        console.print(config_table)
        console.print()
        
        # Actions (matching GUI layout)
        actions_table = Table(title="Actions", box=None)
        actions_table.add_column("Action", style="white", width=30)
        actions_table.add_column("Status", style="white", width=15)
        
        action_options = [
            ("8. Enable meshtasticd on boot", "boot_enabled"),
            ("9. Start/Stop meshtasticd", "service_running"),
            ("10. Install Python CLI", "python_cli"),
            ("11. Send Message", "python_cli"),  # Uses CLI status
            ("12. Set Region", "lora_region"),
            ("13. Enable/Disable Avahi", "avahi"),
        ]
        
        for action, status_key in action_options:
            if action.startswith("11."):  # Send Message
                status = self.get_status_symbol("python_cli")
                if status == "[green]YES[/green]":
                    status = "[green]Ready[/green]"
                else:
                    status = "[red]CLI Required[/red]"
            else:
                status = self.get_status_symbol(status_key)
            actions_table.add_row(action, status)
        
        console.print(actions_table)
        console.print()
        
        # Additional options
        console.print("14. Refresh Status")
        console.print("15. Exit")
        console.print()
    
    def get_menu_choice(self) -> int:
        """Get user menu choice with validation"""
        while True:
            try:
                choice = Prompt.ask("Select option", default="15")
                choice_int = int(choice)
                if 1 <= choice_int <= 15:
                    return choice_int
                else:
                    console.print("[red]Invalid choice. Please select 1-15.[/red]")
            except ValueError:
                console.print("[red]Please enter a valid number.[/red]")
            except (EOFError, KeyboardInterrupt):
                return 15  # Exit on Ctrl+C or EOF
    
    # FIXED HANDLER METHODS - Now check fresh status and force refresh after operations
    
    def handle_install_remove(self):
        """Handle install/remove meshtasticd (Option 1) - FIXED"""
        # Force fresh status check before making decision
        console.print("Checking current installation status...")
        
        # Get fresh status, not cached
        current_status = self.status_checker.check_meshtasticd_status()
        
        if current_status:
            console.print("Meshtasticd is currently [green]installed[/green].")
            if Confirm.ask("Do you want to remove it?"):
                self.remove_meshtasticd()
                # Force status update after operation
                self.force_status_refresh()
        else:
            console.print("Meshtasticd is currently [red]not installed[/red].")
            if Confirm.ask("Do you want to install it?"):
                self.install_meshtasticd()
                # Force status update after operation
                self.force_status_refresh()
    
    def handle_enable_spi(self):
        """Handle SPI enable/disable (Option 2) - FIXED"""
        # Check fresh status
        current_status = self.status_checker.check_spi_status()
        
        if current_status:
            console.print("[green]SPI is already enabled[/green]")
        else:
            console.print("Enabling SPI interface...")
            self._enable_spi()
            # Force status update after operation
            self.force_status_refresh()
    
    def handle_enable_i2c(self):
        """Handle I2C enable/disable (Option 3) - FIXED"""
        # Check fresh status
        current_status = self.status_checker.check_i2c_status()
        
        if current_status:
            console.print("[green]I2C is already enabled[/green]")
        else:
            console.print("Enabling I2C interface...")
            self._enable_i2c()
            # Force status update after operation
            self.force_status_refresh()
    
    def handle_enable_gps_uart(self):
        """Handle GPS/UART enable (Option 4) - FIXED"""
        # Check fresh status
        current_status = self.status_checker.check_gps_uart_status()
        
        if current_status:
            console.print("[green]GPS/UART is already enabled[/green]")
        else:
            console.print("Enabling GPS/UART interface...")
            self._enable_gps_uart()
            # Force status update after operation
            self.force_status_refresh()
    
    def handle_hat_specific(self):
        """Handle HAT specific configuration (Option 5) - FIXED"""
        if not self.hardware.hat_info or self.hardware.hat_info.get('product') != 'MeshAdv Mini':
            console.print("[red]MeshAdv Mini HAT not detected. This function is specific to MeshAdv Mini.[/red]")
            return
        
        console.print("Configuring MeshAdv Mini specific options...")
        self._configure_meshadv_mini()
        # Force status update after operation
        self.force_status_refresh()
    
    def handle_hat_config(self):
        """Handle HAT configuration (Option 6) - FIXED"""
        self._handle_hat_config()
        # Force status update after operation
        self.force_status_refresh()
    
    def handle_edit_config(self):
        """Handle config file editing (Option 7) - FIXED"""
        self._edit_config_file()
        # Force status update after operation
        self.force_status_refresh()
    
    def handle_enable_boot(self):
        """Handle enabling meshtasticd on boot (Option 8) - FIXED"""
        # Check fresh status
        current_status = self.status_checker.check_meshtasticd_boot_status()
        
        if current_status:
            console.print("[green]meshtasticd is already enabled on boot[/green]")
        else:
            console.print("Enabling meshtasticd to start on boot...")
            self._enable_boot_service()
            # Force status update after operation
            self.force_status_refresh()
    
    def handle_start_stop(self):
        """Handle starting/stopping meshtasticd service (Option 9) - FIXED"""
        # Force fresh status check before making decision
        console.print("Checking current service status...")
        
        # Get fresh status, not cached
        current_status = self.status_checker.check_meshtasticd_service_status()
        
        if current_status:
            console.print("Service is currently [green]running[/green]. Stopping...")
            self._stop_service()
        else:
            console.print("Service is currently [red]stopped[/red]. Starting...")
            self._start_service()
        
        # Force status update after operation
        self.force_status_refresh()
    
    def handle_install_python_cli(self):
        """Handle Python CLI installation (Option 10) - FIXED"""
        # Check fresh status
        current_status = self.status_checker.check_python_cli_status()
        
        if current_status:
            if Confirm.ask("Meshtastic Python CLI is already installed. Do you want to reinstall/upgrade it?"):
                self._install_python_cli()
                # Force status update after operation
                self.force_status_refresh()
            else:
                self._show_python_cli_version()
        else:
            self._install_python_cli()
            # Force status update after operation
            self.force_status_refresh()
    
    def handle_send_message(self):
        """Handle sending a message (Option 11) - FIXED"""
        # Check fresh CLI status
        if not self.status_checker.check_python_cli_status():
            console.print("[red]Meshtastic Python CLI is not installed. Please install it first using option 10.[/red]")
            return
        
        self._show_send_message_dialog()
    
    def handle_set_region(self):
        """Handle setting LoRa region (Option 12) - FIXED"""
        # Check fresh CLI status
        if not self.status_checker.check_python_cli_status():
            console.print("[red]Meshtastic Python CLI is not installed. Please install it first using option 10.[/red]")
            return
        
        self._show_region_selection_dialog()
        # Force status update after operation
        self.force_status_refresh()
    
    def handle_enable_disable_avahi(self):
        """Handle Avahi setup/removal (Option 13) - FIXED"""
        # Check fresh status
        current_status = self.status_checker.check_avahi_status()
        
        if current_status:
            if Confirm.ask("Avahi is currently enabled. Do you want to disable it?\n\nThis will:\n• Remove the Meshtastic service file\n• Stop the avahi-daemon service\n• Disable avahi-daemon from starting on boot"):
                self._disable_avahi()
                # Force status update after operation
                self.force_status_refresh()
        else:
            self._enable_avahi()
            # Force status update after operation
            self.force_status_refresh()
    
    # FIXED IMPLEMENTATION METHODS
    
    def _enable_spi(self):
        """Enable SPI interface - FIXED"""
        progress = ProgressDots("Configuring SPI")
        progress.start()
        
        try:
            logging.info("Enabling SPI interface...")
            
            # Enable SPI via raspi-config
            self.system_manager.run_sudo_command(["raspi-config", "nonint", "do_spi", "0"])
            
            # Backup and modify config file
            backup_path = self.system_manager.backup_file(self.config.BOOT_CONFIG_FILE)
            logging.info(f"Backed up config.txt to {backup_path}")
            
            # Read current config
            result = self.system_manager.run_sudo_command(["cat", self.config.BOOT_CONFIG_FILE])
            config_content = result.stdout
            
            # Add SPI configurations
            config_updated = False
            if "dtparam=spi=on" not in config_content:
                config_content += "\n# SPI Configuration\ndtparam=spi=on\n"
                config_updated = True
                logging.info("Added SPI parameter to config.txt")
            
            if "dtoverlay=spi0-0cs" not in config_content:
                if not config_updated:
                    config_content += "\n# SPI Configuration\n"
                config_content += "dtoverlay=spi0-0cs\n"
                config_updated = True
                logging.info("Added SPI overlay to config.txt")
            
            if config_updated:
                self.system_manager.run_sudo_command(["tee", self.config.BOOT_CONFIG_FILE], 
                                                   input_text=config_content)
                logging.info("SPI configuration updated in config.txt")
                console.print("[green]✓ SPI enabled successfully[/green]")
                console.print("[yellow]Reboot may be required for changes to take effect[/yellow]")
            else:
                logging.info("SPI configuration already present in config.txt")
                console.print("[green]✓ SPI configuration already present[/green]")
            
        except Exception as e:
            logging.error(f"SPI configuration error: {e}")
            console.print(f"[red]✗ SPI configuration failed: {e}[/red]")
        finally:
            progress.stop()
    
    def _enable_i2c(self):
        """Enable I2C interface - FIXED"""
        progress = ProgressDots("Configuring I2C")
        progress.start()
        
        try:
            logging.info("Enabling I2C interface...")
            
            # Enable I2C via raspi-config
            self.system_manager.run_sudo_command(["raspi-config", "nonint", "do_i2c", "0"])
            
            # Backup and modify config file
            backup_path = self.system_manager.backup_file(self.config.BOOT_CONFIG_FILE)
            logging.info(f"Backed up config.txt to {backup_path}")
            
            # Read current config
            result = self.system_manager.run_sudo_command(["cat", self.config.BOOT_CONFIG_FILE])
            config_content = result.stdout
            
            # Add I2C configuration
            if "dtparam=i2c_arm=on" not in config_content:
                config_content += "\n# I2C Configuration\ndtparam=i2c_arm=on\n"
                self.system_manager.run_sudo_command(["tee", self.config.BOOT_CONFIG_FILE], 
                                                   input_text=config_content)
                logging.info("Added I2C ARM parameter to config.txt")
                console.print("[green]✓ I2C enabled successfully[/green]")
                console.print("[yellow]Reboot may be required for changes to take effect[/yellow]")
            else:
                logging.info("I2C ARM parameter already present in config.txt")
                console.print("[green]✓ I2C configuration already present[/green]")
            
        except Exception as e:
            logging.error(f"I2C configuration error: {e}")
            console.print(f"[red]✗ I2C configuration failed: {e}[/red]")
        finally:
            progress.stop()
    
    def _enable_gps_uart(self):
        """Enable GPS/UART interface - FIXED"""
        progress = ProgressDots("Configuring GPS/UART")
        progress.start()
        
        try:
            logging.info("Enabling GPS/UART interface...")
            
            # Backup and modify config file
            backup_path = self.system_manager.backup_file(self.config.BOOT_CONFIG_FILE)
            logging.info(f"Backed up config.txt to {backup_path}")
            
            # Read current config
            result = self.system_manager.run_sudo_command(["cat", self.config.BOOT_CONFIG_FILE])
            config_content = result.stdout
            
            config_updated = False
            
            # Add enable_uart=1
            if "enable_uart=1" not in config_content:
                config_content += "\n# GPS/UART Configuration\nenable_uart=1\n"
                config_updated = True
                logging.info("Added enable_uart=1 to config.txt")
            
            # Add uart0 overlay for Pi 5
            if self.hardware.is_pi5() and "dtoverlay=uart0" not in config_content:
                if not config_updated:
                    config_content += "\n# GPS/UART Configuration\n"
                config_content += "dtoverlay=uart0\n"
                config_updated = True
                logging.info("Added uart0 overlay for Pi 5 to config.txt")
            
            if config_updated:
                self.system_manager.run_sudo_command(["tee", self.config.BOOT_CONFIG_FILE], 
                                                   input_text=config_content)
                logging.info("GPS/UART configuration written to config.txt")
                console.print("[green]✓ GPS/UART enabled successfully[/green]")
                console.print("[yellow]Reboot required for changes to take effect[/yellow]")
            else:
                console.print("[green]✓ GPS/UART configuration already present[/green]")
            
            # Disable serial console
            logging.info("Disabling serial console to prevent UART conflicts...")
            result = self.system_manager.run_sudo_command(["raspi-config", "nonint", "do_serial_cons", "1"])
            if result.returncode == 0:
                logging.info("✅ Serial console disabled successfully")
            else:
                logging.warning("⚠️ Failed to disable serial console")
            
        except Exception as e:
            logging.error(f"GPS/UART configuration error: {e}")
            console.print(f"[red]✗ GPS/UART configuration failed: {e}[/red]")
        finally:
            progress.stop()
    
    def _stop_service(self):
        """Stop meshtasticd service"""
        progress = ProgressDots("Stopping service")
        progress.start()
        
        try:
            logging.info("Stopping meshtasticd service...")
            result = self.system_manager.run_sudo_command(["systemctl", "stop", self.config.PKG_NAME])
            
            if result.returncode == 0:
                logging.info("✅ meshtasticd service stopped")
                console.print("[green]✅ meshtasticd service stopped[/green]")
            else:
                raise MeshtasticError(f"Failed to stop service: {result.stderr}")
                
        except Exception as e:
            logging.error(f"Service stop failed: {e}")
            console.print(f"[red]✗ Failed to stop service: {e}[/red]")
        finally:
            progress.stop()
    
    def _configure_meshadv_mini(self):
        """Configure MeshAdv Mini specific settings - FIXED"""
        progress = ProgressDots("Configuring MeshAdv Mini")
        progress.start()
        
        try:
            logging.info("Configuring MeshAdv Mini GPIO and PPS settings...")
            
            # Backup config file
            backup_path = self.system_manager.backup_file(self.config.BOOT_CONFIG_FILE)
            logging.info(f"Backed up config.txt to {backup_path}")
            
            # Read current config
            result = self.system_manager.run_sudo_command(["cat", self.config.BOOT_CONFIG_FILE])
            config_content = result.stdout
            
            # MeshAdv Mini specific configurations
            meshadv_config = """
# MeshAdv Mini Configuration
# GPIO 4 configuration - turn on at boot
gpio=4=op,dh

# PPS configuration for GPS on GPIO 17
dtoverlay=pps-gpio,gpiopin=17
"""
            
            # Check if already configured
            if "MeshAdv Mini Configuration" not in config_content:
                config_content += meshadv_config
                self.system_manager.run_sudo_command(["tee", self.config.BOOT_CONFIG_FILE], 
                                                   input_text=config_content)
                logging.info("MeshAdv Mini configuration added to config.txt")
                console.print("[green]✓ MeshAdv Mini configuration complete[/green]")
                console.print("[yellow]Reboot required for changes to take effect[/yellow]")
            else:
                logging.info("MeshAdv Mini configuration already present")
                console.print("[green]✓ MeshAdv Mini already configured[/green]")
            
        except Exception as e:
            logging.error(f"MeshAdv Mini configuration error: {e}")
            console.print(f"[red]✗ MeshAdv Mini configuration failed: {e}[/red]")
        finally:
            progress.stop()
    
    def _handle_hat_config(self):
        """Handle HAT configuration in meshtasticd config.d - FIXED"""
        try:
            available_dir = f"{self.config.CONFIG_DIR}/available.d"
            config_d_dir = f"{self.config.CONFIG_DIR}/config.d"
            
            # Create directories if they don't exist
            self.system_manager.run_sudo_command(["mkdir", "-p", available_dir])
            self.system_manager.run_sudo_command(["mkdir", "-p", config_d_dir])
            
            # Check for existing configs in config.d
            existing_configs = list(Path(config_d_dir).glob("*.yaml"))
            if existing_configs:
                config_names = [f.name for f in existing_configs]
                logging.info(f"Found existing configs in config.d: {', '.join(config_names)}")
                
                if not Confirm.ask(f"Found existing configuration(s): {', '.join(config_names)}\nDo you want to replace them?"):
                    logging.info("User chose not to replace existing configuration")
                    return
                
                # Remove existing configs
                for config_file in existing_configs:
                    self.system_manager.run_sudo_command(["rm", str(config_file)])
                    logging.info(f"Removed existing config: {config_file.name}")
            
            # Look for available configs
            available_configs = []
            yaml_files = list(Path(available_dir).glob("*.yaml"))
            available_configs.extend(yaml_files)
            
            folders = [d for d in Path(available_dir).iterdir() if d.is_dir()]
            available_configs.extend(folders)
            
            if not available_configs:
                logging.warning("No configuration files or folders found in available.d")
                console.print(f"[red]No configuration files or folders found in {available_dir}[/red]")
                return
            
            # Find matching configs for detected HAT
            matching_configs = []
            if self.hardware.hat_info:
                hat_product = self.hardware.hat_info.get('product', '').lower()
                hat_vendor = self.hardware.hat_info.get('vendor', '').lower()
                
                for config_item in available_configs:
                    config_name = config_item.name.lower()
                    if (hat_product in config_name or 
                        hat_vendor in config_name or
                        'meshadv' in config_name):
                        matching_configs.append(config_item)
            
            if len(matching_configs) == 1:
                # Auto-select matching config
                selected_config = matching_configs[0]
                hat_product = self.hardware.hat_info.get('product', 'Unknown') if self.hardware.hat_info else 'None'
                hat_vendor = self.hardware.hat_info.get('vendor', 'Unknown') if self.hardware.hat_info else 'Unknown'
                config_type = "Folder" if selected_config.is_dir() else "File"
                
                if Confirm.ask(f"Detected HAT: {hat_vendor} {hat_product}\n\nAuto-selected configuration: {selected_config.name} ({config_type})\n\nUse this configuration?"):
                    self._copy_config_item(selected_config, config_d_dir)
                else:
                    self._show_config_selection_menu(available_configs, config_d_dir)
            else:
                self._show_config_selection_menu(available_configs, config_d_dir)
                
        except Exception as e:
            logging.error(f"HAT configuration error: {e}")
            console.print(f"[red]HAT configuration failed: {e}[/red]")
    
    def _show_config_selection_menu(self, available_configs, config_d_dir):
        """Show configuration selection menu"""
        console.print("\n[bold]Available HAT configurations:[/bold]")
        
        config_list = []
        for i, config in enumerate(available_configs, 1):
            config_type = "Folder" if config.is_dir() else "File"
            config_list.append(config)
            console.print(f"  {i}. {config.name} ({config_type})")
        
        try:
            choice = IntPrompt.ask("Select HAT configuration", 
                                 choices=[str(i) for i in range(1, len(config_list) + 1)])
            selected_config = config_list[choice - 1]
            self._copy_config_item(selected_config, config_d_dir)
        except (ValueError, IndexError):
            console.print("[red]Invalid selection.[/red]")
    
    def _copy_config_item(self, source_item: Path, config_d_dir: str):
        """Copy configuration item with proper handling"""
        try:
            if source_item.is_file():
                # Copy single YAML file directly
                dest_path = Path(config_d_dir) / source_item.name
                self.system_manager.run_sudo_command(["cp", str(source_item), str(dest_path)])
                logging.info(f"Copied {source_item.name} to config.d")
                
            else:
                # If it's a folder, look for config files inside it
                config_files = list(source_item.glob("*.yaml"))
                if not config_files:
                    raise ConfigurationError(f"No YAML config files found in folder {source_item.name}")
                
                if len(config_files) == 1:
                    # Single config file in folder - copy it
                    config_file = config_files[0]
                    dest_path = Path(config_d_dir) / config_file.name
                    self.system_manager.run_sudo_command(["cp", str(config_file), str(dest_path)])
                    logging.info(f"Copied {config_file.name} from folder {source_item.name} to config.d")
                else:
                    # Multiple config files - show selection
                    console.print(f"\nMultiple config files found in {source_item.name}:")
                    for i, config_file in enumerate(config_files, 1):
                        console.print(f"  {i}. {config_file.name}")
                    
                    choice = IntPrompt.ask("Select config file", 
                                         choices=[str(i) for i in range(1, len(config_files) + 1)])
                    config_file = config_files[choice - 1]
                    dest_path = Path(config_d_dir) / config_file.name
                    self.system_manager.run_sudo_command(["cp", str(config_file), str(dest_path)])
                    logging.info(f"Copied {config_file.name} from folder {source_item.name} to config.d")
            
            console.print(f"[green]✓ Configuration '{source_item.name}' has been applied.[/green]")
            console.print("[yellow]Restart meshtasticd service for changes to take effect.[/yellow]")
            
        except Exception as e:
            logging.error(f"Failed to copy config item: {e}")
            console.print(f"[red]Failed to copy configuration: {e}[/red]")
    
    def _edit_config_file(self):
        """Handle config file editing - FIXED"""
        config_file = f"{self.config.CONFIG_DIR}/config.yaml"
        
        try:
            if not os.path.exists(config_file):
                if Confirm.ask(f"Config file {config_file} does not exist. Create it now?"):
                    os.makedirs(self.config.CONFIG_DIR, exist_ok=True)
                    with open(config_file, 'w') as f:
                        f.write("# Meshtastic Configuration\n")
                        f.write("# Edit this file to configure your device\n\n")
                    logging.info(f"Created new config file: {config_file}")
                else:
                    return
            
            logging.info(f"Opening config file in nano: {config_file}")
            
            terminal_commands = [
                ["x-terminal-emulator", "-e", "sudo", "nano", config_file],
                ["gnome-terminal", "--", "sudo", "nano", config_file],
                ["xterm", "-e", "sudo", "nano", config_file],
                ["lxterminal", "-e", "sudo", "nano", config_file],
                ["mate-terminal", "-e", "sudo", "nano", config_file],
                ["konsole", "-e", "sudo", "nano", config_file],
            ]
            
            success = False
            for cmd in terminal_commands:
                try:
                    if shutil.which(cmd[0]):
                        subprocess.Popen(cmd)
                        success = True
                        logging.info(f"Opened nano with: {cmd[0]}")
                        console.print(f"[green]✓ Opened config file in {cmd[0]}[/green]")
                        break
                except Exception as e:
                    logging.warning(f"Failed to open with {cmd[0]}: {e}")
                    continue
            
            if not success:
                console.print(f"[red]Could not open terminal automatically.[/red]")
                console.print(f"[yellow]Please run this command manually:[/yellow]")
                console.print(f"sudo nano {config_file}")
                
        except Exception as e:
            logging.error(f"Failed to edit config file: {e}")
            console.print(f"[red]Failed to edit config file: {e}[/red]")
    
    def _enable_boot_service(self):
        """Enable meshtasticd to start on boot"""
        progress = ProgressDots("Configuring boot service")
        progress.start()
        
        try:
            logging.info("Enabling meshtasticd to start on boot...")
            result = self.system_manager.run_sudo_command(["systemctl", "enable", self.config.PKG_NAME])
            
            if result.returncode == 0:
                logging.info("✅ meshtasticd enabled to start on boot")
                console.print("[green]✅ meshtasticd enabled to start on boot[/green]")
            else:
                raise MeshtasticError(f"Failed to enable boot service: {result.stderr}")
                
        except Exception as e:
            logging.error(f"Boot service configuration failed: {e}")
            console.print(f"[red]✗ Failed to enable boot service: {e}[/red]")
        finally:
            progress.stop()
    
    def _start_service(self):
        """Start meshtasticd service"""
        progress = ProgressDots("Starting service")
        progress.start()
        
        try:
            logging.info("Starting meshtasticd service...")
            result = self.system_manager.run_sudo_command(["systemctl", "start", self.config.PKG_NAME])
            
            if result.returncode == 0:
                logging.info("✅ meshtasticd service started")
                console.print("[green]✅ meshtasticd service started[/green]")
            else:
                raise MeshtasticError(f"Failed to start service: {result.stderr}")
                
        except Exception as e:
            logging.error(f"Service start failed: {e}")
            console.print(f"[red]✗ Failed to start service: {e}[/red]")
        finally:
            progress.stop()
    
    def _install_python_cli(self):
        """Install Meshtastic Python CLI - FIXED"""
        progress = ProgressDots("Installing Python CLI (this may take several minutes)")
        progress.start()
        
        try:
            logging.info("="*50)
            logging.info("STARTING MESHTASTIC PYTHON CLI INSTALLATION")
            logging.info("="*50)
            
            # Step 1: Install python3-full
            logging.info("Step 1/5: Installing python3-full...")
            result = self.system_manager.safe_apt_command(["sudo", "apt", "install", "-y", "python3-full"], 
                                                        timeout=self.config.DEFAULT_TIMEOUT)
            if result and result.returncode == 0:
                logging.info("✅ python3-full installed successfully")
            else:
                logging.warning("⚠️ python3-full installation had issues, continuing...")
            
            # Step 2: Install pytap2 via pip3
            logging.info("Step 2/5: Installing pytap2 via pip3...")
            try:
                result = self.system_manager.run_command(
                    ["pip3", "install", "--upgrade", "pytap2", "--break-system-packages"],
                    timeout=self.config.DEFAULT_TIMEOUT
                )
                if result.returncode == 0:
                    logging.info("✅ pytap2 installed successfully")
                else:
                    logging.warning(f"⚠️ pytap2 installation warning, continuing...")
            except Exception as e:
                logging.warning(f"⚠️ pytap2 installation issue: {e}, continuing...")
            
            # Step 3: Install pipx
            logging.info("Step 3/5: Installing pipx...")
            result = self.system_manager.safe_apt_command(["sudo", "apt", "install", "-y", "pipx"], 
                                                        timeout=self.config.DEFAULT_TIMEOUT)
            if not result or result.returncode != 0:
                raise InstallationError("Failed to install pipx")
            logging.info("✅ pipx installed successfully")
            
            # Step 4: Install meshtastic CLI via pipx
            logging.info("Step 4/5: Installing Meshtastic CLI via pipx...")
            result = self.system_manager.run_command(
                ["pipx", "install", "meshtastic[cli]"],
                timeout=600  # 10 minute timeout
            )
            if result.returncode != 0:
                raise InstallationError(f"Failed to install Meshtastic CLI: {result.stderr}")
            logging.info("✅ Meshtastic CLI installed successfully via pipx")
            
            # Step 5: Ensure pipx path
            logging.info("Step 5/5: Ensuring pipx PATH configuration...")
            try:
                result = self.system_manager.run_command(["pipx", "ensurepath"], timeout=60)
                if result.returncode == 0:
                    logging.info("✅ pipx PATH configured successfully")
                else:
                    logging.warning(f"⚠️ pipx ensurepath warning")
            except Exception as e:
                logging.warning(f"⚠️ pipx ensurepath issue: {e}")
            
            # Step 6: Verify installation
            logging.info("Step 6/6: Verifying installation...")
            try:
                result = self.system_manager.run_command(["meshtastic", "--version"], timeout=30)
                if result.returncode == 0:
                    version_info = result.stdout.strip()
                    logging.info(f"✅ INSTALLATION COMPLETED SUCCESSFULLY!")
                    logging.info(f"Meshtastic CLI version: {version_info}")
                    console.print(f"[green]✓ Python CLI installed successfully: {version_info}[/green]")
                    console.print("[yellow]IMPORTANT: Restart your terminal for PATH changes to take effect.[/yellow]")
                else:
                    logging.warning("⚠️ Installation completed but version check failed")
                    console.print("[green]✓ Python CLI installed (restart terminal required)[/green]")
            except Exception as e:
                logging.warning(f"⚠️ Version check failed: {e}")
                console.print("[green]✓ Python CLI installed (verification failed)[/green]")
                
        except Exception as e:
            logging.error(f"❌ PYTHON CLI INSTALLATION ERROR: {e}")
            console.print(f"[red]✗ Python CLI installation failed: {e}[/red]")
        finally:
            progress.stop()
    
    def _show_python_cli_version(self):
        """Show current Python CLI version"""
        try:
            logging.info("Checking Meshtastic Python CLI version...")
            result = self.system_manager.run_command(["meshtastic", "--version"])
            if result.returncode == 0:
                version_info = result.stdout.strip()
                logging.info(f"✅ Meshtastic Python CLI version: {version_info}")
                console.print(f"[green]✓ Meshtastic Python CLI version: {version_info}[/green]")
            else:
                logging.error("❌ Failed to get Python CLI version")
                console.print("[red]✗ Failed to get Python CLI version[/red]")
        except Exception as e:
            logging.error(f"Error checking Python CLI version: {e}")
            console.print(f"[red]✗ Error checking Python CLI version: {e}[/red]")
    
    def _show_send_message_dialog(self):
        """Show dialog for sending messages"""
        console.print("\n[bold]Send Message to Mesh Network[/bold]")
        console.print("Enter the message you want to send to the mesh:")
        
        message_text = Prompt.ask("Message (max 200 characters)", default="Hello from CLI!")
        
        if len(message_text) > 200:
            console.print("[red]Message too long. Maximum 200 characters.[/red]")
            return
        
        if Confirm.ask(f"Send message: '{message_text}'?"):
            self._send_mesh_message(message_text)
    
    def _send_mesh_message(self, message_text: str):
        """Send message to mesh network"""
        progress = ProgressDots(f"Sending message")
        progress.start()
        
        try:
            logging.info(f"Sending message to mesh: '{message_text}'")
            result = self.system_manager.run_command(
                ["meshtastic", "--host", "localhost", "--sendtext", message_text],
                timeout=self.config.CLI_TIMEOUT
            )
            
            if result.returncode == 0:
                logging.info("✅ Message sent successfully!")
                if result.stdout.strip():
                    logging.info(f"Response: {result.stdout.strip()}")
                console.print(f"[green]✓ Message sent successfully![/green]")
            else:
                error_msg = result.stderr.strip() if result.stderr.strip() else "Unknown error"
                raise MeshtasticError(f"Failed to send message: {error_msg}")
                
        except Exception as e:
            logging.error(f"❌ Message sending failed: {e}")
            console.print(f"[red]✗ Failed to send message: {e}[/red]")
            console.print("[yellow]Make sure meshtasticd is running and a device is connected.[/yellow]")
        finally:
            progress.stop()
    
    def _show_region_selection_dialog(self):
        """Show dialog for region selection"""
        current_region = self.status_cache.get("lora_region", "Unknown")
        
        console.print(f"\n[bold]Set LoRa Region[/bold]")
        console.print(f"Current Region: {current_region}")
        
        if current_region == "UNSET":
            console.print("[red]⚠️ Region is UNSET - This must be configured![/red]")
        
        console.print("\nSelect your region (most common options first):")
        
        # Define regions (common ones first, then alphabetical)
        regions = [
            ("US", "United States (902-928 MHz)"),
            ("EU_868", "Europe 868 MHz"),
            ("ANZ", "Australia/New Zealand (915-928 MHz)"),
            ("", "─── Other Regions ───"),  # Separator
            ("CN", "China (470-510 MHz)"),
            ("EU_433", "Europe 433 MHz"),
            ("IN", "India (865-867 MHz)"),
            ("JP", "Japan (920-923 MHz)"),
            ("KR", "Korea (920-923 MHz)"),
            ("MY_433", "Malaysia 433 MHz"),
            ("MY_919", "Malaysia 919-924 MHz"),
            ("RU", "Russia (868-870 MHz)"),
            ("SG_923", "Singapore 920-925 MHz"),
            ("TH", "Thailand (920-925 MHz)"),
            ("TW", "Taiwan (920-925 MHz)"),
            ("UA_433", "Ukraine 433 MHz"),
            ("UA_868", "Ukraine 868 MHz"),
            ("UNSET", "Unset (must be configured)")
        ]
        
        region_list = []
        for i, (region_code, region_name) in enumerate(regions, 1):
            if region_code == "":  # Separator
                console.print(f"    {region_name}")
                continue
            region_list.append(region_code)
            marker = " [current]" if region_code == current_region else ""
            console.print(f"  {len(region_list)}. {region_code} - {region_name}{marker}")
        
        try:
            choice = IntPrompt.ask("Select region", 
                                 choices=[str(i) for i in range(1, len(region_list) + 1)])
            new_region = region_list[choice - 1]
            
            if new_region == current_region:
                console.print(f"[green]Region is already set to {new_region}[/green]")
                return
            
            if Confirm.ask(f"Set region to {new_region}?"):
                self._set_lora_region(new_region, current_region)
                
        except (ValueError, IndexError):
            console.print("[red]Invalid selection.[/red]")
    
    def _set_lora_region(self, new_region: str, old_region: str):
        """Set the LoRa region"""
        progress = ProgressDots(f"Setting LoRa region to {new_region}")
        progress.start()
        
        try:
            logging.info(f"Changing LoRa region from {old_region} to {new_region}...")
            result = self.system_manager.run_command(
                ["meshtastic", "--host", "localhost", "--set", "lora.region", new_region],
                timeout=self.config.CLI_TIMEOUT
            )
            
            if result.returncode == 0:
                logging.info("✅ LoRa region updated successfully!")
                if result.stdout.strip():
                    logging.info(f"Response: {result.stdout.strip()}")
                console.print(f"[green]✓ LoRa region updated successfully![/green]")
                console.print(f"[green]Changed from: {old_region} to: {new_region}[/green]")
                console.print("[yellow]The device may need to restart for changes to take full effect.[/yellow]")
            else:
                error_msg = result.stderr.strip() if result.stderr.strip() else "Unknown error"
                raise MeshtasticError(f"Failed to set LoRa region: {error_msg}")
                
        except Exception as e:
            logging.error(f"❌ Region setting failed: {e}")
            console.print(f"[red]✗ Failed to update LoRa region: {e}[/red]")
            console.print("[yellow]Make sure meshtasticd is running and a device is connected.[/yellow]")
        finally:
            progress.stop()
    
    def _enable_avahi(self):
        """Enable Avahi for auto-discovery - FIXED"""
        progress = ProgressDots("Setting up Avahi")
        progress.start()
        
        try:
            logging.info("="*50)
            logging.info("STARTING AVAHI SETUP")
            logging.info("="*50)
            
            # Check if avahi-daemon is installed
            logging.info("Step 1/4: Checking if avahi-daemon is installed...")
            avahi_installed = self.system_manager.check_package_installed("avahi-daemon")
            
            if not avahi_installed:
                logging.info("Installing avahi-daemon...")
                self.system_manager.safe_apt_command(["sudo", "apt", "update"], timeout=120)
                result = self.system_manager.safe_apt_command(["sudo", "apt", "install", "-y", "avahi-daemon"], 
                                                            timeout=300)
                if not result or result.returncode != 0:
                    raise InstallationError("Failed to install avahi-daemon")
                logging.info("✅ avahi-daemon installed successfully")
            else:
                logging.info("✅ avahi-daemon is already installed")
            
            # Create service file
            logging.info("Step 2/4: Creating Meshtastic service file...")
            service_file = "/etc/avahi/services/meshtastic.service"
            service_content = """<?xml version="1.0" standalone="no"?><!--*-nxml-*-->
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
<n>Meshtastic</n>
<service protocol="ipv4">
<type>_meshtastic._tcp</type>
<port>4403</port>
</service>
</service-group>"""
            
            self.system_manager.run_sudo_command(["mkdir", "-p", "/etc/avahi/services"])
            result = self.system_manager.run_sudo_command(["tee", service_file], 
                                                        input_text=service_content)
            
            if result.returncode == 0:
                logging.info("✅ Meshtastic service file created successfully")
            else:
                raise ConfigurationError("Failed to create service file")
            
            # Enable and start service
            logging.info("Step 3/4: Enabling avahi-daemon service...")
            self.system_manager.run_sudo_command(["systemctl", "enable", "avahi-daemon"])
            
            logging.info("Step 4/4: Starting avahi-daemon service...")
            self.system_manager.run_sudo_command(["systemctl", "start", "avahi-daemon"])
            
            logging.info("✅ AVAHI SETUP COMPLETED SUCCESSFULLY!")
            logging.info("Android clients can now auto-discover this device")
            console.print("[green]✓ Avahi enabled successfully![/green]")
            console.print("[green]Android clients can now auto-discover this device[/green]")
            
        except Exception as e:
            logging.error(f"❌ AVAHI SETUP ERROR: {e}")
            console.print(f"[red]✗ Avahi setup failed: {e}[/red]")
        finally:
            progress.stop()
    
    def _disable_avahi(self):
        """Disable Avahi and remove Meshtastic service - FIXED"""
        progress = ProgressDots("Disabling Avahi")
        progress.start()
        
        try:
            logging.info("="*50)
            logging.info("STARTING AVAHI REMOVAL")
            logging.info("="*50)
            
            # Stop service
            logging.info("Step 1/3: Stopping avahi-daemon service...")
            self.system_manager.run_sudo_command(["systemctl", "stop", "avahi-daemon"])
            logging.info("✅ avahi-daemon service stopped")
            
            # Disable service
            logging.info("Step 2/3: Disabling avahi-daemon...")
            self.system_manager.run_sudo_command(["systemctl", "disable", "avahi-daemon"])
            logging.info("✅ avahi-daemon disabled")
            
            # Remove service file
            logging.info("Step 3/3: Removing Meshtastic service file...")
            service_file = "/etc/avahi/services/meshtastic.service"
            
            if os.path.exists(service_file):
                self.system_manager.run_sudo_command(["rm", service_file])
                logging.info("✅ Meshtastic service file removed")
            else:
                logging.info("ℹ️ Meshtastic service file was not found")
            
            logging.info("✅ AVAHI REMOVAL COMPLETED SUCCESSFULLY!")
            console.print("[green]✓ Avahi disabled successfully![/green]")
            
        except Exception as e:
            logging.error(f"❌ AVAHI REMOVAL ERROR: {e}")
            console.print(f"[red]✗ Avahi removal failed: {e}[/red]")
        finally:
            progress.stop()
    
    def install_meshtasticd(self):
        """Install meshtasticd with channel selection"""
        console.print("\n[bold]Select Meshtastic Channel:[/bold]")
        
        channels = [
            ("beta", "Beta (Safe)"),
            ("alpha", "Alpha (Might be safe, might not)"),
            ("daily", "Daily (Are you mAd MAn?)")
        ]
        
        for i, (channel_code, channel_name) in enumerate(channels, 1):
            console.print(f"  {i}. {channel_name}")
        
        try:
            choice = IntPrompt.ask("Select channel", choices=["1", "2", "3"], default=1)
            channel = channels[choice - 1][0]
            
            if Confirm.ask(f"Install Meshtastic from {channel} channel?"):
                self._perform_installation(channel)
        except (ValueError, IndexError):
            console.print("[red]Invalid selection.[/red]")
    
    def _perform_installation(self, channel: str):
        """Perform the actual installation - FIXED"""
        progress = ProgressDots(f"Installing meshtasticd ({channel} channel)")
        progress.start()
        
        try:
            logging.info("="*50)
            logging.info(f"STARTING MESHTASTIC INSTALLATION - {channel.upper()} CHANNEL")
            logging.info("="*50)
            
            # Step 0: Check and fix apt locks
            logging.info("Step 0/5: Checking for apt lock issues...")
            self.system_manager.check_and_fix_apt_locks()
            
            # Step 1: Create repository configuration
            repo_url = f"http://download.opensuse.org/repositories/network:/Meshtastic:/{channel}/{self.config.OS_VERSION}/"
            list_file = f"{self.config.REPO_DIR}/{self.config.REPO_PREFIX}:{channel}.list"
            gpg_file = f"{self.config.GPG_DIR}/network_Meshtastic_{channel}.gpg"
            
            logging.info(f"Step 1/5: Creating repository configuration...")
            repo_content = f"deb {repo_url} /\n"
            result = self.system_manager.run_sudo_command(["tee", list_file], input_text=repo_content)
            if result.returncode != 0:
                raise InstallationError("Failed to create repository file")
            logging.info(f"✅ Repository file created successfully")
            
            # Step 2: Download GPG key
            logging.info(f"Step 2/5: Downloading GPG key...")
            result = self.system_manager.run_command(["curl", "-fsSL", f"{repo_url}Release.key"])
            if result.returncode != 0:
                raise InstallationError("Failed to download GPG key")
            logging.info(f"✅ GPG key downloaded successfully")
            
            # Step 3: Process and install GPG key
            logging.info(f"Step 3/5: Processing GPG key...")
            gpg_process = subprocess.Popen(
                ["gpg", "--dearmor"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            gpg_output, gpg_error = gpg_process.communicate(input=result.stdout.encode('utf-8'))
            
            if gpg_process.returncode != 0:
                raise InstallationError("GPG key processing failed")
            
            # Write GPG key
            with open('/tmp/temp_gpg_key', 'wb') as temp_file:
                temp_file.write(gpg_output)
            
            write_result = self.system_manager.run_sudo_command(["mv", "/tmp/temp_gpg_key", gpg_file])
            if write_result.returncode != 0:
                raise InstallationError("Failed to install GPG key")
            
            self.system_manager.run_sudo_command(["chmod", "644", gpg_file])
            logging.info(f"✅ GPG key installed successfully")
            
            # Step 4: Update package database
            logging.info(f"Step 4/5: Updating package database...")
            result = self.system_manager.safe_apt_command(["sudo", "apt", "update"], timeout=120)
            if result and result.returncode != 0:
                logging.warning(f"⚠️ Package update had issues, continuing anyway")
            else:
                logging.info(f"✅ Package database updated successfully")
            
            # Step 5: Install package
            logging.info(f"Step 5/5: Installing meshtasticd package...")
            
            # Check if config file exists (might need user input during install)
            config_exists = os.path.exists(f"{self.config.CONFIG_DIR}/config.yaml")
            
            if config_exists:
                logging.info("Existing configuration detected - handling potential config file prompts...")
                
                # Use DEBIAN_FRONTEND=noninteractive with force-confold to keep existing configs
                env = os.environ.copy()
                env['DEBIAN_FRONTEND'] = 'noninteractive'
                env['APT_LISTCHANGES_FRONTEND'] = 'none'
                
                result = self.system_manager.safe_apt_command([
                    "sudo", "-E", "apt", "install", "-y", 
                    "-o", "Dpkg::Options::=--force-confdef", 
                    "-o", "Dpkg::Options::=--force-confold", 
                    self.config.PKG_NAME
                ], timeout=self.config.APT_TIMEOUT)
            else:
                # No existing config, should install without prompts
                env = os.environ.copy()
                env['DEBIAN_FRONTEND'] = 'noninteractive'
                
                result = self.system_manager.safe_apt_command([
                    "sudo", "-E", "apt", "install", "-y", self.config.PKG_NAME
                ], timeout=self.config.APT_TIMEOUT)
            
            if result and result.returncode == 0:
                logging.info(f"✅ INSTALLATION COMPLETED SUCCESSFULLY!")
                logging.info(f"Meshtasticd {channel} channel has been installed")
                console.print(f"[green]✓ Meshtasticd {channel} installed successfully![/green]")
                console.print("[green]You can now configure and start the service[/green]")
            else:
                logging.error(f"❌ Installation failed")
                if result and result.stderr.strip():
                    logging.error(f"Error details: {result.stderr}")
                raise InstallationError(f"Package installation failed: {result.stderr if result else 'Unknown error'}")
            
        except Exception as e:
            logging.error(f"❌ INSTALLATION ERROR: {e}")
            console.print(f"[red]✗ Installation failed: {e}[/red]")
        finally:
            progress.stop()
    
    def remove_meshtasticd(self):
        """Remove meshtasticd - FIXED"""
        progress = ProgressDots("Removing meshtasticd")
        progress.start()
        
        try:
            logging.info("="*50)
            logging.info("STARTING MESHTASTIC REMOVAL")
            logging.info("="*50)
            
            # Step 0: Check and fix apt locks
            logging.info("Step 0/4: Checking for apt lock issues...")
            self.system_manager.check_and_fix_apt_locks()
            
            # Step 1: Stop service
            logging.info("Step 1/4: Stopping meshtasticd service...")
            result = self.system_manager.run_sudo_command(["systemctl", "stop", self.config.PKG_NAME])
            if result.returncode == 0:
                logging.info("✅ Service stopped successfully")
            else:
                logging.info("ℹ️ Service was not running or already stopped")
            
            # Step 2: Disable service
            logging.info("Step 2/4: Disabling meshtasticd service...")
            result = self.system_manager.run_sudo_command(["systemctl", "disable", self.config.PKG_NAME])
            if result.returncode == 0:
                logging.info("✅ Service disabled successfully")
            else:
                logging.info("ℹ️ Service was not enabled or already disabled")
            
            # Step 3: Remove package
            logging.info("Step 3/4: Removing meshtasticd package...")
            result = self.system_manager.safe_apt_command([
                "sudo", "apt", "remove", "-y", self.config.PKG_NAME
            ], timeout=300, interactive_input="n\n")
            
            if result and result.returncode == 0:
                logging.info("✅ Package removed successfully")
                
                # Step 4: Clean up repository files
                logging.info("Step 4/4: Cleaning up repository files...")
                try:
                    repo_files = list(Path(self.config.REPO_DIR).glob(f"{self.config.REPO_PREFIX}:*.list"))
                    gpg_files = list(Path(self.config.GPG_DIR).glob("network_Meshtastic_*.gpg"))
                    
                    files_removed = 0
                    for repo_file in repo_files:
                        result = self.system_manager.run_sudo_command(["rm", str(repo_file)])
                        if result.returncode == 0:
                            logging.info(f"✅ Removed repository file: {repo_file.name}")
                            files_removed += 1
                        
                    for gpg_file in gpg_files:
                        result = self.system_manager.run_sudo_command(["rm", str(gpg_file)])
                        if result.returncode == 0:
                            logging.info(f"✅ Removed GPG key: {gpg_file.name}")
                            files_removed += 1
                            
                    if files_removed > 0:
                        logging.info(f"✅ Cleaned up {files_removed} repository files")
                    else:
                        logging.info("ℹ️ No repository files found to clean up")
                        
                except Exception as e:
                    logging.warning(f"⚠️ Repository cleanup had issues: {e}")
                
                logging.info("✅ REMOVAL COMPLETED SUCCESSFULLY!")
                console.print("[green]✓ Meshtasticd has been completely uninstalled[/green]")
            else:
                logging.error("❌ REMOVAL FAILED!")
                console.print("[red]✗ Package removal failed![/red]")
            
        except Exception as e:
            logging.error(f"❌ REMOVAL ERROR: {e}")
            console.print(f"[red]✗ Removal failed: {e}[/red]")
        finally:
            progress.stop()
    
    def run_menu_mode(self):
        """Run the interactive menu interface - FIXED"""
        try:
            console.print("[bold green]Meshtastic Configuration Tool - CLI Version[/bold green]")
            console.print("Starting interactive configuration interface...\n")
            
            # Initial status check
            self.update_status_indicators()
            
            while self.running:
                self.show_main_menu()
                choice = self.get_menu_choice()
                
                if choice == 1:
                    self.handle_install_remove()
                elif choice == 2:
                    self.handle_enable_spi()
                elif choice == 3:
                    self.handle_enable_i2c()
                elif choice == 4:
                    self.handle_enable_gps_uart()
                elif choice == 5:
                    self.handle_hat_specific()
                elif choice == 6:
                    self.handle_hat_config()
                elif choice == 7:
                    self.handle_edit_config()
                elif choice == 8:
                    self.handle_enable_boot()
                elif choice == 9:
                    self.handle_start_stop()
                elif choice == 10:
                    self.handle_install_python_cli()
                elif choice == 11:
                    self.handle_send_message()
                elif choice == 12:
                    self.handle_set_region()
                elif choice == 13:
                    self.handle_enable_disable_avahi()
                elif choice == 14:
                    console.print("Refreshing status...")
                    self.force_status_refresh()
                    console.print("[green]✓ Status refreshed[/green]")
                elif choice == 15:
                    console.print("[green]Goodbye![/green]")
                    break
                
                # Add pause after each operation except refresh and exit
                if choice not in [14, 15]:
                    Prompt.ask("\nPress Enter to continue")
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user[/yellow]")
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            console.print(f"[red]Fatal error: {e}[/red]")
        finally:
            self.thread_manager.shutdown()

# Command-line interface with both menu and direct command support
@click.group(invoke_without_command=True)
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--config-path', '-c', default='/etc/meshtasticd/config.yaml', 
              help='Path to configuration file')
@click.option('--log-level', default='INFO', 
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']))
@click.pass_context
def main(ctx, verbose, config_path, log_level):
    """
    Meshtastic Configuration Tool - CLI Version
    
    Interactive command-line interface for configuring Meshtastic daemon
    on Raspberry Pi devices. Run without arguments for interactive menu,
    or use specific commands for direct operations.
    """
    
    # Set up logging level
    log_level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO, 
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR
    }
    
    if verbose:
        log_level = 'DEBUG'
    
    # Check if running as root for system operations
    #if os.geteuid() != 0:
        #console.print("[red]Warning: Some operations require root privileges.[/red]")
        #console.print("[yellow]Consider running with sudo for full functionality.[/yellow]")
        #console.print()
    
    # Check SSH environment
    if 'SSH_CLIENT' in os.environ or 'SSH_TTY' in os.environ:
        console.print("[blue]SSH session detected - CLI mode optimized[/blue]")
        console.print()
    
    # Store context for subcommands
    ctx.ensure_object(dict)
    ctx.obj['config_path'] = config_path
    ctx.obj['log_level'] = log_level_map[log_level]
    
    # If no subcommand, run interactive menu
    if ctx.invoked_subcommand is None:
        try:
            cli = MeshtasticCLI()
            cli.run_menu_mode()
        except Exception as e:
            console.print(f"[red]Failed to start CLI interface: {e}[/red]")
            sys.exit(1)

# Direct command implementations
@main.command()
@click.option('--channel', type=click.Choice(['beta', 'alpha', 'daily']), default='beta')
@click.pass_context
def install(ctx, channel):
    """Install meshtasticd package"""
    cli = MeshtasticCLI()
    cli._perform_installation(channel)

@main.command()
@click.pass_context
def remove(ctx):
    """Remove meshtasticd package"""
    cli = MeshtasticCLI()
    cli.remove_meshtasticd()

@main.command()
@click.pass_context
def enable_spi(ctx):
    """Enable SPI interface"""
    cli = MeshtasticCLI()
    cli._enable_spi()

@main.command()
@click.pass_context
def enable_i2c(ctx):
    """Enable I2C interface"""
    cli = MeshtasticCLI()
    cli._enable_i2c()

@main.command()
@click.pass_context
def enable_uart(ctx):
    """Enable GPS/UART interface"""
    cli = MeshtasticCLI()
    cli._enable_gps_uart()

@main.command()
@click.pass_context
def start_service(ctx):
    """Start meshtasticd service"""
    cli = MeshtasticCLI()
    cli._start_service()

@main.command()
@click.pass_context
def stop_service(ctx):
    """Stop meshtasticd service"""
    cli = MeshtasticCLI()
    cli._stop_service()

@main.command()
@click.pass_context
def enable_boot(ctx):
    """Enable meshtasticd to start on boot"""
    cli = MeshtasticCLI()
    cli._enable_boot_service()

@main.command()
@click.pass_context
def install_cli(ctx):
    """Install Python CLI"""
    cli = MeshtasticCLI()
    cli._install_python_cli()

@main.command()
@click.argument('message')
@click.pass_context
def send_message(ctx, message):
    """Send a message to the mesh network"""
    cli = MeshtasticCLI()
    cli._send_mesh_message(message)

@main.command()
@click.argument('region', type=click.Choice(['US', 'EU_868', 'EU_433', 'ANZ', 'CN', 'IN', 'JP', 'KR', 
                                            'MY_433', 'MY_919', 'RU', 'SG_923', 'TH', 'TW', 'UA_433', 'UA_868']))
@click.pass_context
def set_region(ctx, region):
    """Set LoRa region"""
    cli = MeshtasticCLI()
    cli.update_status_indicators()
    current_region = cli.status_cache.get("lora_region", "Unknown")
    cli._set_lora_region(region, current_region)

@main.command()
@click.pass_context
def enable_avahi(ctx):
    """Enable Avahi service"""
    cli = MeshtasticCLI()
    cli._enable_avahi()

@main.command()
@click.pass_context
def disable_avahi(ctx):
    """Disable Avahi service"""
    cli = MeshtasticCLI()
    cli._disable_avahi()

@main.command()
@click.pass_context
def status(ctx):
    """Show comprehensive status"""
    cli = MeshtasticCLI()
    cli.update_status_indicators()
    
    # Display status in a nice table
    table = Table(title="Meshtastic System Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="white")
    
    status_items = [
        ("Meshtasticd Package", cli.get_status_symbol("meshtasticd")),
        ("SPI Interface", cli.get_status_symbol("spi")),
        ("I2C Interface", cli.get_status_symbol("i2c")),
        ("GPS/UART Interface", cli.get_status_symbol("gps_uart")),
        ("HAT Specific Config", cli.get_status_symbol("hat_specific")),
        ("HAT Config Applied", cli.get_status_symbol("hat_config")),
        ("Config File Exists", cli.get_status_symbol("config_exists")),
        ("Python CLI", cli.get_status_symbol("python_cli")),
        ("LoRa Region", cli.get_status_symbol("lora_region")),
        ("Avahi Service", cli.get_status_symbol("avahi")),
        ("Boot Enabled", cli.get_status_symbol("boot_enabled")),
        ("Service Running", cli.get_status_symbol("service_running")),
    ]
    
    for component, status in status_items:
        table.add_row(component, status)
    
    console.print(table)

if __name__ == "__main__":
    main()
                    
