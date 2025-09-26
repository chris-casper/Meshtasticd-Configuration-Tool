# Meshtasticd-Configuration-Tool

  
This is a fork of the original (Meshtasticd-Configuration-Tool)[https://github.com/chrismyers2000/Meshtasticd-Configuration-Tool], adding support and optimization for nebra meshtasticd nodes. 

This is NOT yet operational.

  ---
## 1. Meshtasticd Configuration Tool (CLI only)

This is a stripped down CLI only python tool that can do it all, install meshtasticd, setup all the needed /boot/firmware/config.txt options, choose your hat config file, edit /etc/meshtasticd/config.yaml, even help you install other helpful tools like Meshtastic Python CLI. This tool will help get you from fresh install to sending a test message. Designed for default 64 bit Raspberry Pi OS (Bookworm). It'll be tested on Nebra Pi CM3, Pi 3, Pi 4 and maybe Pi 5. 

This is an interactive text-based version of the above GUI application.
This is experimental at this point, but geared entirely around SSH to a Nebra Outdoor Miner. 

Option 7 does not work and will be removed. 


See my (blog post)[https://casper.im/Recycling-Old-Crypto-Miners/] on Nebras.

Follow instructions on flashing the emmc key, reinstalling it, powering up the unit and connecting via PuTTy or SSH to the nebra. 

 
 - Installation:
    
	
    - Log into Nebra and paste this
    ```bash
	# New system updates
    sudo apt update -y
    sudo DEBIAN_FRONTEND=noninteractive \
    apt-get -y \
      -o Dpkg::Options::="--force-confdef" \
      -o Dpkg::Options::="--force-confold" \
      dist-upgrade
	# Install python3
	apt install python3 python3-rich-click python3-yaml -y
	# Get script
    wget https://raw.githubusercontent.com/chris-casper/Meshtasticd-Configuration-Tool/refs/heads/main/Command-line/meshtasticd_config_tool_CLI.py
	# 
    sudo chmod +x meshtasticd_config_tool_CLI.py
    ./meshtasticd_config_tool_CLI.py
    ```
