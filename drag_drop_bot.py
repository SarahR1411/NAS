import os
import shutil

# Dictionary mapping router number to its folder ID and router name
router_folder_corresp = {
    5 : ("8936d624-47db-464e-8324-7850715336a4", "i5"),
    1 : ("0908260c-1447-42d4-8572-70b6cd9be6e9", "i1"),
    8 : ("186ecb23-5e4d-4932-9081-40bf631515f9", "i8"),
    6: ("f6169b8b-fec9-40b8-be99-82118ebe5313", "i6"),
    4 : ("81830e03-089c-4b84-9afb-4adecace1ac6", "i4"),
    2 : ("8308f3c9-ccc2-4020-80d2-ae61ea234fd4", "i2"),
    3 : ("f4882832-ecf9-409d-9387-3303c106a53c", "i3"),
    7 : ("cf3f1615-9b1b-4d38-a0b3-b99218c02904", "i7"),
    10 : ("2c4d2dd5-316d-4d95-9ae4-ff2bb20c7bb8", "i10"),
    9 : ("ded58d48-a425-4001-bf29-d8340c471c4f", "i9"),
    11 : ("fd8a44b5-b69a-4d00-9cd8-a658838f6b05", "i11"),
    12 : ("853ea17d-cca2-4710-8e56-34113d7e0a41", "i12")

}

# Folder where the router configuration files are stored
config_folder = "configs"
# Destination folder where GNS3 expects the configuration files to be moved
destination = "/home/srmili/Bureau/NAS_proj_new/project-files/dynamips"


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
