import subprocess
import logging
import os
import time
import threading
import xml.etree.ElementTree as ET
import sys
from syncthing import Syncthing, SyncthingError

class SyncthingManager:
    """
    Manages the embedded Syncthing process and its API for decentralized config syncing.
    This version uses the modern 'syncthing2' library.
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
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            self.syncthing_exe_path = os.path.join(base_path, "resources", "syncthing", "syncthing.exe")
        
        self.app_data_path = os.path.join(os.getenv('APPDATA'), 'NydusNet')
        self.sync_folder_path = os.path.join(self.app_data_path, 'SyncData')
        self.folder_label = "NydusNetConfig"
        
    def start(self, base_port=8385, max_retries=10) -> bool:
        if self.is_running:
            return True

        if not os.path.exists(self.syncthing_exe_path):
            logging.error(f"Syncthing executable not found at {self.syncthing_exe_path}")
            return False

        for i in range(max_retries):
            current_port = base_port + i
            config_path = os.path.join(self.app_data_path, "syncthing_config")
            log_path = os.path.join(config_path, "syncthing.log")
            os.makedirs(config_path, exist_ok=True)

            command = [
                f'"{self.syncthing_exe_path}"', '--home', f'"{config_path}"',
                '--gui-address', f'"127.0.0.1:{current_port}"',
                "--no-browser", '--logfile', f'"{log_path}"'
            ]
            
            command_str = ' '.join(command)
            logging.info(f"Attempting to start Syncthing: {command_str}")

            try:
                self.process = subprocess.Popen(
                    command_str, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                # We still wait a moment to catch immediate failures
                time.sleep(2) 
                if self.process.poll() is not None:
                    _, stderr = self.process.communicate()
                    if "FATAL: Listen" in stderr or "address already in use" in stderr:
                        logging.warning(f"Port {current_port} is in use. Retrying...")
                        continue
                    else:
                        logging.error(f"Syncthing failed on port {current_port}. Stderr: {stderr.strip()}")
                        continue
                
                logging.info(f"Syncthing process started on port {current_port}! Initializing API client...")
                self._initialize_api_client(config_path, current_port)
                self.is_running = True
                return True
            except Exception as e:
                logging.error(f"Failed to launch Syncthing: {e}", exc_info=True)
                continue

        logging.error("Failed to start Syncthing after multiple attempts.")
        return False

    def _initialize_api_client(self, config_path, port):
        try:
            config_xml_path = os.path.join(config_path, "config.xml")
            # Wait for config file to be created by Syncthing
            for _ in range(10): # Wait up to 10 seconds
                if os.path.exists(config_xml_path): break
                time.sleep(1)
            else:
                raise FileNotFoundError("Syncthing config.xml was not created in time.")

            tree = ET.parse(config_xml_path)
            self.api_key = tree.getroot().find('.//gui/apikey').text
            
            # THE FIX: Create the client first, then poll for connection.
            self.api_client = Syncthing(self.api_key, host="127.0.0.1", port=port, is_https=False)
            
            for i in range(10): # Try to connect for up to 10 seconds
                try:
                    status = self.api_client.system.status()
                    self.my_device_id = status['myID']
                    logging.info(f"Syncthing API connected successfully. This device ID: {self.my_device_id}")
                    
                    self.controller.on_syncthing_id_ready()
                    self.create_initial_share()
                    return # Success!
                except SyncthingError as e:
                    # This specific error indicates the API is not ready yet
                    if "http request error" in str(e):
                        logging.debug(f"Syncthing API not ready yet (attempt {i+1}/10). Retrying in 1 second...")
                        time.sleep(1)
                    else:
                        raise # It's a different, unexpected API error, so raise it
            
            # If the loop finishes without returning, it means we failed to connect
            raise ConnectionError("Could not connect to Syncthing API after multiple retries.")

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
        try:
            config = self.api_client.system.config()
            if not any(f['label'] == self.folder_label for f in config.get('folders', [])):
                logging.info(f"Creating initial share for folder: {self.folder_label}")
                config['folders'].append({
                    'id': self.folder_label, 'label': self.folder_label,
                    'path': self.sync_folder_path, 'devices': []
                })
                self.api_client.system.post_config(config)
        except Exception as e:
            logging.error(f"Failed to create initial share: {e}", exc_info=True)

    def generate_invite(self) -> str | None:
        return f"{self.my_device_id}|{self.folder_label}" if self.my_device_id else None

    def accept_invite(self, invite_string: str):
        try:
            device_id, folder_id = invite_string.split('|')
            logging.info(f"Accepting invite from {device_id} for folder {folder_id}")
            config = self.api_client.system.config()
            if not any(d['deviceID'] == device_id for d in config.get('devices', [])):
                config['devices'].append({'deviceID': device_id, 'name': 'Synced Device'})
            for folder in config.get('folders', []):
                if folder['id'] == folder_id and not any(d['deviceID'] == device_id for d in folder.get('devices', [])):
                    folder['devices'].append({'deviceID': device_id})
                    break
            self.api_client.system.post_config(config)
        except Exception as e:
            logging.error(f"Failed to accept invite: {e}")
            
    def remove_device(self, device_id: str):
        try:
            logging.info(f"Removing device {device_id}")
            config = self.api_client.system.config()
            for folder in config.get('folders', []):
                if folder['label'] == self.folder_label:
                    folder['devices'] = [d for d in folder.get('devices', []) if d.get('deviceID') != device_id]
            config['devices'] = [d for d in config.get('devices', []) if d.get('deviceID') != device_id]
            self.api_client.system.post_config(config)
        except Exception as e:
            logging.error(f"Failed to remove device {device_id}: {e}")

