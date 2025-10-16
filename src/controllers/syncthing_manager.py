import subprocess
import logging
import os
import time
import threading
import xml.etree.ElementTree as ET
import syncthing
import sys
import requests
from syncthing import SyncthingError

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
        
        if getattr(sys, 'frozen', False):
            base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            self.syncthing_exe_path = os.path.join(base_path, "_internal", "syncthing", "syncthing.exe")
        else:
            # Correct path for development environment (assuming syncthing_manager.py is in src/controllers)
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            self.syncthing_exe_path = os.path.join(base_path, "resources", "syncthing", "syncthing.exe")

        self.app_data_path = os.path.join(os.getenv('APPDATA'), 'NydusNet')
        self.sync_folder_path = os.path.join(self.app_data_path, 'SyncData')
        self.folder_label = "NydusNetConfig"
        
    def start(self, base_port=8385, max_retries=10) -> bool:
        if self.is_running:
            logging.info("Syncthing is already running.")
            return True

        if not os.path.exists(self.syncthing_exe_path):
            logging.error(f"Syncthing executable not found at {self.syncthing_exe_path}. Cannot start service.")
            return False

        for i in range(max_retries):
            current_port = base_port + i
            config_path = os.path.join(self.app_data_path, "syncthing_config")
            log_path = os.path.join(config_path, "syncthing.log")
            
            os.makedirs(config_path, exist_ok=True)

            command = [
                f'"{self.syncthing_exe_path}"',
                '--home', f'"{config_path}"',
                '--gui-address', f'"127.0.0.1:{current_port}"',
                "--no-browser",
                '--logfile', f'"{log_path}"'
            ]
            
            command_str = ' '.join(command)
            logging.info(f"Attempting to start Syncthing with command: {command_str}")

            try:
                # Use Popen for non-blocking start
                self.process = subprocess.Popen(
                    command_str, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                # Wait a moment to see if it fails immediately
                time.sleep(2)
                
                if self.process.poll() is not None: # Process has terminated
                    stdout, stderr = self.process.communicate()
                    if "FATAL: Listen" in stderr:
                        logging.warning(f"Port {current_port} is in use. Retrying...")
                        continue
                    else:
                        logging.error(f"Syncthing process exited immediately on port {current_port}.")
                        logging.error(f"STDOUT: {stdout.strip()}")
                        logging.error(f"STDERR: {stderr.strip()}")
                        continue
                
                logging.info(f"Syncthing started successfully on port {current_port}!")
                self._initialize_api_client(config_path, current_port)
                self.is_running = True
                return True

            except Exception as e:
                logging.error(f"Failed to start Syncthing: {e}", exc_info=True)
                continue

        logging.error("Failed to start Syncthing after multiple attempts.")
        return False

    def _initialize_api_client(self, config_path, port):
        try:
            config_xml_path = os.path.join(config_path, "config.xml")
            retries = 5
            while not os.path.exists(config_xml_path) and retries > 0:
                time.sleep(1)
                retries -= 1

            if not os.path.exists(config_xml_path):
                logging.error("Syncthing config.xml not found after waiting.")
                return

            tree = ET.parse(config_xml_path)
            root = tree.getroot()
            self.api_key = root.find('.//gui/apikey').text
            
            self.api_client = syncthing.Syncthing(self.api_key, port=port)
            self.my_device_id = self.api_client.system.status()['myID']
            logging.info(f"Syncthing API client connected. This device ID is {self.my_device_id}")
            
            # --- FIX: Notify the controller that the ID is now available ---
            self.controller.on_syncthing_id_ready()
            
            self.create_initial_share()
            
            threading.Thread(target=self._auto_accept_loop, daemon=True).start()
        except Exception as e:
            logging.error(f"Failed to initialize Syncthing API client: {e}", exc_info=True)

    def stop(self):
        if self.process and self.process.poll() is None:
            logging.info("Shutting down Syncthing process.")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.is_running = False

    def create_initial_share(self):
        if not self.api_client: return
        try:
            config = self.api_client.system.config()
            folder_exists = any(f['label'] == self.folder_label for f in config.get('folders', []))
            
            if not folder_exists:
                logging.info(f"Creating initial share for folder: {self.folder_label}")
                # Ensure 'folders' key exists
                if 'folders' not in config:
                    config['folders'] = []
                config['folders'].append({
                    'id': self.folder_label,
                    'label': self.folder_label,
                    'path': self.sync_folder_path,
                    'devices': []
                })
                self.api_client.system.set_config(config)
        except Exception as e:
            logging.error(f"Failed to create initial share: {e}", exc_info=True)

    def generate_invite(self) -> str | None:
        if not self.api_client or not self.my_device_id: return None
        try:
            return f"{self.my_device_id}|{self.folder_label}"
        except Exception as e:
            logging.error(f"Could not generate invite: {e}")
            return None

    def accept_invite(self, invite_string: str):
        if not self.api_client: return
        try:
            device_id, folder_id = invite_string.split('|')
            logging.info(f"Accepting invite. Adding device {device_id} and folder {folder_id}")
            
            config = self.api_client.system.config()
            
            # Ensure 'devices' key exists
            if 'devices' not in config:
                config['devices'] = []
            if not any(d['deviceID'] == device_id for d in config.get('devices', [])):
                config['devices'].append({'deviceID': device_id, 'name': 'Synced Device'})

            for folder in config.get('folders', []):
                if folder['id'] == folder_id:
                    if 'devices' not in folder:
                        folder['devices'] = []
                    if not any(d['deviceID'] == device_id for d in folder.get('devices', [])):
                        folder['devices'].append({'deviceID': device_id})
                    break
            
            self.api_client.system.set_config(config)
        except Exception as e:
            logging.error(f"Failed to accept invite: {e}")
            
    def remove_device(self, device_id: str):
        if not self.api_client: return
        try:
            logging.info(f"Removing device {device_id} from sync group.")
            config = self.api_client.system.config()

            for folder in config.get('folders', []):
                if folder['label'] == self.folder_label:
                    folder['devices'] = [d for d in folder.get('devices', []) if d.get('deviceID') != device_id]
                    break
            
            config['devices'] = [d for d in config.get('devices', []) if d.get('deviceID') != device_id]
            
            self.api_client.system.set_config(config)
        except Exception as e:
            logging.error(f"Failed to remove device {device_id}: {e}")

    def _auto_accept_loop(self):
        logging.info("Auto-accept loop is currently disabled for stability.")
        pass
