import os
import json
import uuid
import logging
import shutil
import time
from datetime import datetime, timezone
from utils.crypto import CryptoManager
import diff_match_patch as dmp_module

class ConfigManager:
    """
    Manages all configuration data, including encryption, delta-based versioning,
    and conflict resolution. This class is the single source of truth for all data.
    """
    def __init__(self, app_controller):
        self.controller = app_controller
        self.sync_path = os.path.join(os.getenv('APPDATA'), 'NydusNet', 'SyncData')
        self.history_dir = os.path.join(self.sync_path, 'history')
        self.index_file = os.path.join(self.history_dir, '_index.json')
        self.check_file = os.path.join(self.sync_path, 'verification.dat')
        self.recovery_key_file = os.path.join(self.sync_path, 'recovery.dat') # New path for the encrypted recovery key
        
        self.crypto_manager = CryptoManager()
        self.dmp = dmp_module.diff_match_patch()
        
        self._master_password = None
        self._in_memory_state = {}
        self._file_index = {}

        os.makedirs(self.history_dir, exist_ok=True)

    def unlock_with_password(self, password: str) -> bool:
        if not os.path.exists(self.check_file):
            logging.info("First-time setup: creating new configuration and check file.")
            self._master_password = password
            check_data = "NydusNetVerification".encode('utf-8')
            encrypted_check = self.crypto_manager.encrypt_data(check_data, self._master_password)
            with open(self.check_file, 'wb') as f:
                f.write(encrypted_check)
            self.load_configuration()
            return True

        try:
            with open(self.check_file, 'rb') as f:
                encrypted_data = f.read()
            decrypted_data = self.crypto_manager.decrypt_data(encrypted_data, password)
            if decrypted_data and decrypted_data.decode('utf-8') == "NydusNetVerification":
                self._master_password = password
                self.load_configuration()
                logging.info("Configuration successfully unlocked.")
                return True
            else:
                logging.warning("Password verification failed.")
                return False
        except Exception as e:
            logging.error(f"Failed to unlock configuration: {e}", exc_info=True)
            return False

    def re_encrypt_with_new_password(self, old_key: str, new_password: str) -> bool:
        if not os.path.exists(self.check_file): return False
        try:
            with open(self.check_file, 'rb') as f:
                encrypted_data = f.read()
            new_encrypted_data = self.crypto_manager.re_encrypt_with_new_password(encrypted_data, old_key, new_password)
            if new_encrypted_data:
                with open(self.check_file, 'wb') as f:
                    f.write(new_encrypted_data)
                
                # Also re-encrypt the recovery key with the new password
                if os.path.exists(self.recovery_key_file):
                    with open(self.recovery_key_file, 'rb') as f:
                        encrypted_recovery_key = f.read()
                    
                    decrypted_recovery_key = self.crypto_manager.decrypt_data(encrypted_recovery_key, old_key)
                    if decrypted_recovery_key:
                        new_encrypted_recovery_key = self.crypto_manager.encrypt_data(decrypted_recovery_key, new_password)
                        with open(self.recovery_key_file, 'wb') as f:
                            f.write(new_encrypted_recovery_key)
                
                self._master_password = new_password
                logging.info("Check and recovery key files have been re-encrypted with a new password.")
                return True
            else:
                return False
        except Exception as e:
            logging.error(f"Failed during password recovery: {e}", exc_info=True)
            return False

    def save_recovery_key(self, recovery_key: str):
        """Encrypts and saves the recovery key to a file using the master password."""
        if not self._master_password:
            logging.error("Cannot save recovery key, application is locked.")
            return

        try:
            encrypted_key = self.crypto_manager.encrypt_data(recovery_key.encode('utf-8'), self._master_password)
            with open(self.recovery_key_file, 'wb') as f:
                f.write(encrypted_key)
            logging.info("Recovery key saved successfully.")
        except Exception as e:
            logging.error(f"Failed to save recovery key: {e}", exc_info=True)
            
    def get_recovery_key(self) -> str | None:
        """Decrypts and returns the recovery key from the file."""
        if not self._master_password:
            logging.error("Cannot retrieve recovery key, application is locked.")
            return None

        if not os.path.exists(self.recovery_key_file):
            logging.warning("Recovery key file not found.")
            return None

        try:
            with open(self.recovery_key_file, 'rb') as f:
                encrypted_key = f.read()
            
            decrypted_key = self.crypto_manager.decrypt_data(encrypted_key, self._master_password)
            if decrypted_key:
                return decrypted_key.decode('utf-8')
            else:
                logging.warning("Failed to decrypt recovery key.")
                return None
        except Exception as e:
            logging.error(f"Failed to retrieve recovery key: {e}", exc_info=True)
            return None

    def load_configuration(self):
        logging.info("Reconstructing configuration state from history...")
        if not self._master_password:
            logging.error("Cannot load configuration, application is locked.")
            return

        if os.path.exists(self.index_file):
            with open(self.index_file, 'r', encoding='utf-8') as f:
                self._file_index = json.load(f)

        history_files = sorted(os.listdir(self.history_dir))
        self._in_memory_state = self._reconstruct_state_from_events(history_files)
        logging.info(f"Configuration loaded with {len(self._in_memory_state)} objects.")

    def _reconstruct_state_from_events(self, event_files):
        """Helper function to replay a list of history event files."""
        state = {}
        active_file_ids = set()
        for filename in event_files:
            if filename.endswith('_manifest_delta.json'):
                path = os.path.join(self.history_dir, filename)
                with open(path, 'r', encoding='utf-8') as f:
                    try:
                        delta = json.load(f)
                        if delta.get('action') == 'add': active_file_ids.add(delta.get('file_id'))
                        elif delta.get('action') == 'remove': active_file_ids.discard(delta.get('file_id'))
                    except (json.JSONDecodeError, KeyError): pass

        for file_id in active_file_ids:
            content_deltas = sorted([f for f in event_files if f.startswith(file_id) and f.endswith('_content_delta.txt')])
            reconstructed_content = ""
            for delta_file in content_deltas:
                path = os.path.join(self.history_dir, delta_file)
                with open(path, 'r', encoding='utf-8') as f:
                    patch_text = f.read()
                patches = self.dmp.patch_fromText(patch_text)
                reconstructed_content, _ = self.dmp.patch_apply(patches, reconstructed_content)
            
            try:
                state[file_id] = json.loads(reconstructed_content)
            except json.JSONDecodeError:
                logging.error(f"Failed to decode reconstructed JSON for file ID {file_id}")
        return state

    def _commit_event(self, action: str, file_id: str, content_delta_text: str = None):
        """Writes manifest and content deltas to the history journal."""
        timestamp = datetime.now(timezone.utc).isoformat().replace(":", "-").replace("+00-00", "Z")
        manifest_delta = {'action': action, 'file_id': file_id, 'timestamp': timestamp}
        manifest_delta_path = os.path.join(self.history_dir, f"{timestamp}_{file_id}_manifest_delta.json")
        with open(manifest_delta_path, 'w', encoding='utf-8') as f: json.dump(manifest_delta, f)

        if content_delta_text is not None:
            content_delta_path = os.path.join(self.history_dir, f"{timestamp}_{file_id}_content_delta.txt")
            with open(content_delta_path, 'w', encoding='utf-8') as f: f.write(content_delta_text)
        
        self.load_configuration()

    def add_object(self, obj_type: str, data: dict):
        obj_id = str(uuid.uuid4())
        data['id'] = obj_id
        
        self._file_index[obj_id] = {"name": data.get('name') or data.get('hostname'), "type": obj_type}
        with open(self.index_file, 'w', encoding='utf-8') as f: json.dump(self._file_index, f, indent=2)

        content_text = json.dumps(data, indent=2)
        patches = self.dmp.patch_make("", content_text)
        patch_text = self.dmp.patch_toText(patches)
        
        self._commit_event('add', obj_id, patch_text)
        return obj_id

    def update_object(self, obj_id: str, new_data: dict):
        if obj_id not in self._in_memory_state: return
        old_text = json.dumps(self._in_memory_state[obj_id], indent=2)
        new_text = json.dumps(new_data, indent=2)
        patches = self.dmp.patch_make(old_text, new_text)
        patch_text = self.dmp.patch_toText(patches)
        self._commit_event('update', obj_id, patch_text)
        
    def delete_object(self, obj_id: str):
        if obj_id not in self._in_memory_state: return
        self._commit_event('remove', obj_id)

    def get_object_by_id(self, obj_id: str): return self._in_memory_state.get(obj_id)
    def get_tunnels(self): return [obj for obj in self._in_memory_state.values() if 'hostname' in obj]
    def get_servers(self): return [obj for obj in self._in_memory_state.values() if 'ip_address' in obj]
    def get_clients(self): return [obj for obj in self._in_memory_state.values() if 'syncthing_id' in obj]
    def get_server_name(self, server_id: str):
        server = self.get_object_by_id(server_id)
        return server.get('name', 'Unknown') if server else "Unknown"

    def detect_conflict(self) -> bool:
        for filename in os.listdir(self.history_dir):
            if ".sync-conflict" in filename:
                return True
        return False

    def initiate_conflict_resolution(self):
        """Manages the leader election process for resolving a conflict."""
        my_client_id = self.controller.syncthing_manager.my_device_id
        if not my_client_id:
            logging.error("Cannot start leader election: own client ID is unknown.")
            return

        lock_file = os.path.join(self.sync_path, 'merge.lock')
        
        if not os.path.exists(lock_file):
            try:
                with open(lock_file, 'w') as f: json.dump({'leader_id': my_client_id}, f)
            except IOError: pass

        time.sleep(3) # Allow time for Syncthing to propagate the lock file

        is_leader = False
        if os.path.exists(lock_file):
            try:
                with open(lock_file, 'r') as f:
                    leader_data = json.load(f)
                    if leader_data.get('leader_id') == my_client_id:
                        is_leader = True
            except (json.JSONDecodeError, FileNotFoundError, IOError):
                is_leader = False

        if is_leader:
            self._perform_merge_as_leader()
        else:
            self.controller.show_status_message("Conflict detected. Waiting for another device to resolve...")

    def _perform_merge_as_leader(self):
        logging.info("Leader is performing the merge.")
        
        all_history_files = os.listdir(self.history_dir)
        unified_events = []
        for filename in all_history_files:
            # Syncthing conflict format: filename.sync-conflict-YYYYMMDD-HHMMSS-DeviceID.ext
            original_name = filename.split('.sync-conflict-')[0] if '.sync-conflict-' in filename else filename
            unified_events.append(original_name)
        
        proposed_state = self._reconstruct_state_from_events(sorted(list(set(unified_events))))

        all_objects = proposed_state.values()
        server_conflicts = self._find_conflicts_by_key([o for o in all_objects if 'ip_address' in o], 'ip_address')
        tunnel_conflicts = self._find_conflicts_by_key([o for o in all_objects if 'hostname' in o], lambda t: f"{t.get('server_id')}_{t.get('hostname')}")

        server_resolutions = self.controller.prompt_for_server_merge(server_conflicts) or {}
        tunnel_resolutions = self.controller.prompt_for_tunnel_merge(tunnel_conflicts) or {}

        winner_ids = set(r['id'] for r in server_resolutions.values()) | set(r['id'] for r in tunnel_resolutions.values())
        all_loser_ids = set()
        remap_server_ids = {}

        for key, winner in server_resolutions.items():
            losers = [s for s in server_conflicts.get(key, []) if s['id'] != winner['id']]
            all_loser_ids.update(l['id'] for l in losers)
            for loser in losers: remap_server_ids[loser['id']] = winner['id']
        
        for key, winner in tunnel_resolutions.items():
            losers = [t for t in tunnel_conflicts.get(key, []) if t['id'] != winner['id']]
            all_loser_ids.update(l['id'] for l in losers)

        final_objects = []
        for obj_id, obj in proposed_state.items():
            if obj_id not in all_loser_ids:
                if 'server_id' in obj and obj['server_id'] in remap_server_ids:
                    obj['server_id'] = remap_server_ids[obj['server_id']]
                final_objects.append(obj)

        final_ids = {obj['id'] for obj in final_objects}
        current_ids = set(self._in_memory_state.keys())
        
        for obj_id in current_ids - final_ids:
            if self.get_object_by_id(obj_id): self.delete_object(obj_id)
        
        for obj in final_objects:
            if obj['id'] not in current_ids:
                obj_type = "client" if "syncthing_id" in obj else "server" if "ip_address" in obj else "tunnel"
                self.add_object(obj_type, obj)
            elif obj != self._in_memory_state.get(obj['id']):
                self.update_object(obj['id'], obj)

        for root, _, files in os.walk(self.sync_path):
            for file in files:
                if ".sync-conflict" in file or file == "merge.lock":
                    os.remove(os.path.join(root, file))
        
        logging.info("Merge complete. Final state committed to history.")
        self.load_configuration()
        self.controller.refresh_dashboard()

    def _find_conflicts_by_key(self, object_list, key_func):
        groups = {}
        key = key_func if callable(key_func) else lambda obj: obj.get(key_func)
        for obj in object_list:
            if key(obj) is not None:
                groups.setdefault(key(obj), []).append(obj)
        return {k: v for k, v in groups.items() if len(v) > 1}
        
    def is_configured(self) -> bool:
        """
        Checks if the application has been configured with a master password.
        This is determined by the existence of the verification file.
        """
        return os.path.exists(self.check_file)
