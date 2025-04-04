import os
import re

def parse_config(file_path):
    """
    Parse a router config file and return a dictionary of interfaces and their IP addresses.
    """
    interfaces = {}
    current_interface = None
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            # Check for interface definition
            if line.startswith('interface'):
                current_interface = line.split()[1]  # Extract interface name (e.g., GigabitEthernet0/0)
                interfaces[current_interface] = "no IP"  # Default to "no IP" if no address is found
            # Check for IP address within the current interface block
            elif line.startswith('ip address') and current_interface:
                parts = line.split()
                if len(parts) >= 3:  # Ensure there are enough parts (ip address <ip> <mask>)
                    ip = parts[2]    # IP address
                    mask = parts[3]  # Subnet mask
                    interfaces[current_interface] = f"{ip} {mask}"
    return interfaces

def get_adress_file():
    """
    Main function to process all config files and write the interface summary.
    """
    configs_dir = 'configs'
    all_configs = {}

    # Iterate through files in the configs directory
    for file in os.listdir(configs_dir):
        if file.endswith('_startup-config.cfg'):
            router_name = file.split('_')[0]  # Extract router name from filename (e.g., R1)
            file_path = os.path.join(configs_dir, file)
            interfaces = parse_config(file_path)
            all_configs[router_name] = interfaces

    # Write the results to interface_summary.txt
    with open('interface_summary.txt', 'w') as f:
        for router in sorted(all_configs.keys()):  # Sort routers alphabetically
            f.write(f"Router: {router}\n")
            for interface in sorted(all_configs[router].keys()):  # Sort interfaces alphabetically
                ip = all_configs[router][interface]
                f.write(f"  Interface: {interface}, IP: {ip}\n")
            f.write("\n")  # Add a blank line between routers


    