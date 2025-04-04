import os
import shutil

# Dictionary mapping router number to its folder ID and router name
router_folder_corresp = {
    5 : ("16824cb4-07da-4102-ac91-41489d3bff62", "i5"),
    1 : ("bea7df85-0622-49e6-a664-06f9c4e0bc68", "i1"),
    8 : ("71744ad3-824e-433c-9a9c-31f92a632d52", "i8"),
    6: ("41b2f867-c5df-4e47-9c16-9cc2a8814009", "i6"),
    4 : ("38e99975-b7f6-43a7-ab78-28ec20cc0e56", "i4"),
    2 : ("7e56a6da-0635-4c76-8066-17a6f78f9b89", "i2"),
    3 : ("6be769d8-533b-4e6e-99f5-0e574fbf4029", "i3"),
    7 : ("3cf0b563-e4f3-4d7c-8a44-0c068686bb29", "i7"),
}

# Folder where the router configuration files are stored
config_folder = "config_files"
# Destination folder where GNS3 expects the configuration files to be moved
destination = "/home/srmili/GNS3/projects/GNS_Project1/project-files/dynamips"


def delete_existing_cfg_files(dest_folder):
    """
    Deletes all .cfg files from the destination folder (if they exist).
    This is to avoid conflicts with existing configurations before moving the new ones.
    """
    if os.path.exists(dest_folder):
        for file in os.listdir(dest_folder):
            if file.endswith(".cfg"):   # Filter to only .cfg files
                file_path = os.path.join(dest_folder, file)
                os.remove(file_path)    # Remove the file
                print(f"Deleted existing .cfg file: {file_path}")


def delete_nvram_file(router_folder):
    """
    Deletes any NVRAM files in the router folder.
    NVRAM files can be problematic in certain scenarios, so they are removed before adding new configurations.
    """
    if os.path.exists(router_folder):
        for file in os.listdir(router_folder):
            if "nvram" in file:  # Search for files containing 'nvram' in their name
                file_path = os.path.join(router_folder, file)
                os.remove(file_path)    # Remove the file
                print(f"Deleted NVRAM file: {file_path}")


def move_configs():
    """
    This function moves configuration files from the source folder to the appropriate destination folder
    based on the router folder and router number mapping provided in 'router_folder_corresp'.
    It also handles the deletion of existing configuration and NVRAM files as needed.
    """
    # Iterate over each router in the mapping dictionary
    for router_number, (folder_id, router_name) in router_folder_corresp.items():
        router_folder = os.path.join(destination, folder_id)  # Router's main folder path
        dest_folder = os.path.join(router_folder, "configs")  # Path to the 'configs' subfolder
        src_file = os.path.join(config_folder, f"R{router_number}_startup-config.cfg")  # Source config file
        dest_file = os.path.join(dest_folder, f"{router_name}_startup-config.cfg") # Destination config file with router's local ID

        # Delete NVRAM file in the router's main folder before moving the new config file
        delete_nvram_file(router_folder)

        # Delete any existing .cfg files in the destination config folder to avoid conflicts
        if os.path.exists(dest_folder):
            delete_existing_cfg_files(dest_folder)

        # Move the new configuration file from the source to the destination folder
        if os.path.exists(src_file):
            if not os.path.exists(dest_folder):
                os.makedirs(dest_folder)    # Create the destination folder if it doesn't exist
            shutil.move(src_file, dest_file)    # Move the config file to the destination
            print(f"Moved {src_file} to {dest_file}")
        else:
            print(f"Source file not found: {src_file}")

if __name__ == "__main__":
    move_configs()  # Call the function to start moving the config files