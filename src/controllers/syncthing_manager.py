import subprocess
import logging
import os
import time
import threading
import xml.etree.ElementTree as ET
import syncthing

class SyncthingManager:
    """
    Manages the embedded Syncthing process and its API for decentralized config syncing.
    """
    def __init__(self, controller):
        self.controller = controller
        self.process = None
        self.api_key = None
        self.api_client = None
        self.my_device_id = None
        self.is_running = False
        
        self.app_data_path = os.path.join(os.getenv('APPDATA'), 'NydusNet')
        self.sync_folder_path = os.path.join(self.app_data_path, 'SyncData')
        self.syncthing_exe_path = os.path.join(os.getcwd(), "resources", "syncthing", "syncthing.exe")
        self.folder_label = "NydusNetConfig"
        
    def start(self, base_port=8385, max_retries=10) -> bool:
        """
        Launches an isolated Syncthing instance, finding an open port.
        Returns True on success, False on failure.
        """
        if self.is_running:
            logging.info("Syncthing is already running.")
            return True

        if not os.path.exists(self.syncthing_exe_path):
            logging.error(f"Syncthing executable not found at {self.syncthing_exe_path}. Cannot start service.")
            return False

        for i in range(max_retries):
            current_port = base_port + i
            config_path = os.path.join(self.app_data_path, f"syncthing_config")
            log_path = os.path.join(config_path, "syncthing.log")
            
            os.makedirs(config_path, exist_ok=True)

            command = [
                self.syncthing_exe_path,
                f"-home={config_path}",
                f"-gui-address=127.0.0.1:{current_port}",
                "-no-browser",
                f"-logfile={log_path}"
            ]

            logging.info(f"Attempting to start Syncthing on port {current_port}...")
            self.process = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(4)

            if self.process.poll() is not None:
                try:
                    with open(log_path, 'r') as log_file:
                        if "FATAL: Listen" in log_file.read():
                            logging.warning(f"Port {current_port} is in use. Retrying...")
                            continue
                except FileNotFoundError:
                    logging.error("Syncthing failed to start and log file not found.")
                    continue
            
            logging.info(f"Syncthing started successfully on port {current_port}!")
            self._initialize_api_client(config_path, current_port)
            self.is_running = True
            return True

        logging.error("Failed to start Syncthing after multiple attempts.")
        return False

    def _initialize_api_client(self, config_path, port):
        """Reads the API key from config.xml and connects the Python client."""
        try:
            config_xml_path = os.path.join(config_path, "config.xml")
            # Wait for config file to be created
            retries = 5
            while not os.path.exists(config_xml_path) and retries > 0:
                time.sleep(1)
                retries -= 1

            tree = ET.parse(config_xml_path)
            root = tree.getroot()
            self.api_key = root.find('.//gui/apikey').text
            
            self.api_client = syncthing.Syncthing(self.api_key, port=port)
            self.my_device_id = self.api_client.system.status()['myID']
            logging.info(f"Syncthing API client connected. This device ID is {self.my_device_id}")
            
            threading.Thread(target=self._auto_accept_loop, daemon=True).start()

        except Exception as e:
            logging.error(f"Failed to initialize Syncthing API client: {e}")

    def stop(self):
        """Stops the Syncthing subprocess."""
        if self.process and self.process.poll() is None:
            logging.info("Shutting down Syncthing process.")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.is_running = False

    def create_initial_share(self):
        """Creates and shares the main config folder for the first time."""
        if not self.api_client: return
        try:
            logging.info(f"Creating initial share for folder: {self.folder_label}")
            self.api_client.folders.add(id=self.folder_label, label=self.folder_label, path=self.sync_folder_path)
        except Exception as e:
            logging.error(f"Failed to create initial share: {e}")

    def generate_invite(self) -> str | None:
        """Generates an invitation string containing this device's ID and the folder ID."""
        if not self.api_client: return None
        try:
            folder = self.api_client.folders.get(label=self.folder_label)
            return f"{self.my_device_id}|{folder.id}"
        except syncthing.exceptions.SyncthingError:
             logging.warning(f"Could not generate invite: Folder '{self.folder_label}' not found.")
             return None
        except Exception as e:
            logging.error(f"Could not generate invite: {e}")
            return None

    def accept_invite(self, invite_string: str):
        """Uses an invite string to connect to another device and add the folder."""
        if not self.api_client: return
        try:
            device_id, folder_id = invite_string.split('|')
            logging.info(f"Accepting invite. Adding device {device_id} and folder {folder_id}")
            
            # The folder path must match what Syncthing expects
            self.api_client.devices.add(device_id=device_id, name="Synced Device", auto_accept_folders=False)
            self.api_client.folders.add(id=folder_id, label=self.folder_label, path=self.sync_folder_path, devices=[device_id])

        except Exception as e:
            logging.error(f"Failed to accept invite: {e}")
            
    def remove_device(self, device_id: str):
        """Unshares the folder from a device and removes the device."""
        if not self.api_client: return
        try:
            logging.info(f"Removing device {device_id} from sync group.")
            folder = self.api_client.folders.get(label=self.folder_label)
            folder.unshare(device=device_id)
            self.api_client.devices.delete(device_id=device_id)
        except Exception as e:
            logging.error(f"Failed to remove device {device_id}: {e}")

    def _auto_accept_loop(self):
        """A background thread that uses the event API to auto-accept new devices and folders."""
        last_event_id = 0
        while self.is_running:
            try:
                if not self.api_client:
                    time.sleep(2)
                    continue

                events = self.api_client.events.get(since=last_event_id, limit=10, timeout=30)
                
                if not events: continue

                for event in events:
                    last_event_id = event.id
                    
                    if event.type == "PendingDevicesChanged":
                        for device_id, device_info in event.data.get('added', {}).items():
                            logging.info(f"Auto-accepting new device: {device_info.get('name', device_id)}")
                            self.api_client.devices.update(device_id=device_id, introducer=False, paused=False)

                    if event.type == "PendingFoldersChanged":
                        for folder_id, folder_info in event.data.get('added', {}).items():
                            device_id = folder_info.get('addedBy')
                            logging.info(f"Auto-accepting folder '{folder_info.get('label')}' from device {device_id}")
                            self.api_client.folders.add(id=folder_id, label=self.folder_label, path=self.sync_folder_path, devices=[device_id])

            except syncthing.exceptions.SyncthingError as e:
                if "timeout" not in str(e).lower():
                    logging.error(f"Error in auto-accept loop: {e}")
                    time.sleep(10)
            except Exception as e:
                logging.error(f"Unexpected error in auto-accept loop: {e}")
                time.sleep(10)
