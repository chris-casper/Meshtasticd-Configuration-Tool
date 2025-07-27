# Meshtasticd-Configuration-Tool

  
  A collection of helper scripts designed to make your life easier

  ---
## 1. Meshtasticd Configuration Tool (Python GUI)

This is a python tool that can do it all, install meshtasticd, setup all the needed /boot/firmware/config.txt options, choose your hat config file, edit /etc/meshtasticd/config.yaml, even help you install other helpful tools like Meshtastic Python CLI. This tool will help get you from fresh install to sending a test message. Designed for Raspberry Pi OS (Bookworm). Tested on Pi 4 and Pi 5. 


  ![](https://github.com/chrismyers2000/Meshtasticd-Configuration-Tool/blob/aa0be9ae25465e10088bb557f3c7a1932d0ba315/Gui/ConfigTool1.png)
- Installation

  - Copy the python script to your pi
  ```bash
  wget https://raw.githubusercontent.com/chrismyers2000/Meshtasticd-Configuration-Tool/refs/heads/main/Gui/meshtasticd_config_tool_GUI.py
  ```

  - Change permissions to executable
  ```bash
  sudo chmod +x meshtasticd_config_tool_GUI.py
  ```

  - Run the script
  ```bash
  ./meshtasticd_config_tool_GUI.py
  ```
  - Please note, you will need to reboot a few times for everything to be fully functional
  - After installing the Meshtastic Python CLI, you need to close the GUI and terminal window so the CLI can show up in the proper PATH.
  ---
## 2. CLI Text based installer

This is an interactive text-based version of the above GUI application.
This is experimental at this point, but is fully working in my testing over SSH from windows to raspberry pi.
 
  ![](https://github.com/chrismyers2000/Meshtasticd-Configuration-Tool/blob/49839dc9cead11e6ab28af5db4857b1550991c85/Command-line/ConfigToolCLI.png)
  - Installation:
    
    - Copy the script to your pi
    ```bash
    wget https://raw.githubusercontent.com/chrismyers2000/Meshtasticd-Configuration-Tool/refs/heads/main/Command-line/meshtasticd_config_tool_CLI.py
    ```
  
    - Change permissions to executable
    ```bash
    sudo chmod +x meshtasticd_config_tool_CLI.py
    ```
  
    - Run the script
    ```bash
    ./meshtasticd_config_tool_CLI.py
    ```
