import subprocess
import logging
import os
import threading
from collections import deque

class TunnelManager:
    def __init__(self, controller):
        self.controller = controller
        self.active_tunnels = {}
        self.tunnel_logs = {}
        self.ssh_executable = "C:\\Windows\\System32\\OpenSSH\\ssh.exe"
        self._lock = threading.Lock()
        
        self._is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_tunnels, daemon=True)
        self.monitor_thread.start()

    def stop(self):
        """Stops the monitoring thread, waits for it to exit, then stops all tunnels."""
        logging.info("Stopping tunnel monitor.")
        self._is_monitoring = False
        self.monitor_thread.join(timeout=1.5)
        self.stop_all_tunnels()
        
    def stop_all_tunnels(self):
        """Stops all currently active tunnel processes."""
        logging.info("Stopping all active tunnels...")
        with self._lock:
            tunnel_ids = list(self.active_tunnels.keys())
        for tunnel_id in tunnel_ids:
            self.stop_tunnel(tunnel_id)

    def _monitor_tunnels(self):
        """A background thread that periodically checks for crashed tunnels."""
        while self._is_monitoring:
            if not self._is_monitoring: break
            
            exited_tunnels = []
            with self._lock:
                for tid, p in self.active_tunnels.items():
                    if p.poll() is not None:
                        exited_tunnels.append(tid)

            if exited_tunnels:
                logging.info("Monitor detected a change in tunnel status. Refreshing dashboard.")
                self.controller.refresh_dashboard()
            
            # Use a slightly longer sleep to reduce CPU usage
            for _ in range(50):
                if not self._is_monitoring: break
                threading.Event().wait(0.1)

    def _stream_reader(self, stream, tunnel_id, stream_name):
        """Reads output from a stream and logs it."""
        self.tunnel_logs[tunnel_id] = deque(maxlen=500)
        self.tunnel_logs[tunnel_id].append(f"--- Log stream initialized for {stream_name} ---\n")
        try:
            while True:
                line = stream.readline()
                if not line:
                    break
                log_line = f"[{stream_name.upper()}] {line.strip()}"
                logging.info(f"[TUNNEL:{tunnel_id}] {log_line}")
                self.tunnel_logs[tunnel_id].append(log_line + "\n")
        except Exception as e:
            logging.error(f"Error reading from {stream_name} for tunnel {tunnel_id}: {e}")
        finally:
            stream.close()


    def start_tunnel(self, tunnel_id: str) -> tuple[bool, str]:
        with self._lock:
            if tunnel_id in self.active_tunnels and self.active_tunnels[tunnel_id].poll() is None:
                msg = f"Tunnel {tunnel_id} is already running."
                logging.warning(msg)
                return True, msg

            tunnel_config = self.controller.get_object_by_id(tunnel_id)
            if not tunnel_config:
                return False, "Tunnel configuration not found."

            # --- DEVICE ASSIGNMENT ENFORCEMENT ---
            my_device_id = self.controller.get_my_device_id()
            assigned_device_id = tunnel_config.get('assigned_client_id')
            if assigned_device_id and assigned_device_id != my_device_id:
                assigned_device_name = self.controller.get_client_name(assigned_device_id) or "another device"
                msg = f"Cannot start tunnel. It is assigned to '{assigned_device_name}'."
                logging.error(msg)
                return False, msg

            server_config = self.controller.get_object_by_id(tunnel_config['server_id'])
            if not server_config:
                return False, "Server configuration for this tunnel not found."
            
            automation_creds = self.controller.get_automation_credentials()
            if not automation_creds:
                msg = "Automation credentials (SSH key) not found."
                logging.error(msg)
                return False, f"{msg}\nPlease configure your SSH keys in Settings."

            ssh_key_path = automation_creds.get('ssh_private_key_path')
            
            # --- SSH KEY FILE CHECK ---
            if not ssh_key_path or not os.path.exists(ssh_key_path):
                msg = f"SSH private key file not found at path: {ssh_key_path}"
                logging.error(msg)
                return False, f"{msg}\nPlease correct the path in Settings or ensure the file exists."

            command = [
                self.ssh_executable, '-v', '-i', f'"{ssh_key_path}"',
                '-o', "ServerAliveInterval=30", '-o', "ExitOnForwardFailure=yes",
                '-o', "StrictHostKeyChecking=no", '-o', "UserKnownHostsFile=nul",
                '-N', '-R', f"{tunnel_config['remote_port']}:{tunnel_config['local_destination']}",
                f"{server_config['user']}@{server_config['ip_address']}"
            ]

            logging.info(f"Starting tunnel '{tunnel_config['hostname']}' (ID: {tunnel_id})")
            try:
                process = subprocess.Popen(
                    ' '.join(command), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW
                )
                self.active_tunnels[tunnel_id] = process
                
                threading.Thread(target=self._stream_reader, args=(process.stdout, tunnel_id, "stdout"), daemon=True).start()
                threading.Thread(target=self._stream_reader, args=(process.stderr, tunnel_id, "stderr"), daemon=True).start()

                return True, "Tunnel process started."
            except FileNotFoundError:
                msg = f"SSH executable not found at '{self.ssh_executable}'."
                logging.error(msg)
                return False, msg
            except Exception as e:
                msg = f"An unexpected error occurred while starting the tunnel: {e}"
                logging.error(msg, exc_info=True)
                return False, msg

    def stop_tunnel(self, tunnel_id: str):
        with self._lock:
            if tunnel_id in self.active_tunnels:
                process = self.active_tunnels.pop(tunnel_id)
                if process.poll() is None:
                    logging.info(f"Terminating tunnel process for ID {tunnel_id}")
                    process.terminate()

    def start_all_tunnels(self):
        logging.info("Starting all enabled tunnels assigned to this device...")
        my_device_id = self.controller.get_my_device_id()
        all_tunnels = self.controller.get_tunnels()
        
        tunnels_to_start = [
            t for t in all_tunnels 
            if t.get('enabled', True) and t.get('assigned_client_id') == my_device_id
        ]
        
        for tunnel in tunnels_to_start:
            self.start_tunnel(tunnel['id'])
        self.controller.refresh_dashboard()

    def get_tunnel_statuses(self) -> dict:
        statuses = {}
        with self._lock:
            active_ids = list(self.active_tunnels.keys())

        for tunnel_id in active_ids:
            with self._lock:
                process = self.active_tunnels.get(tunnel_id)

            if process is None: continue # It might have been stopped by another thread

            if process.poll() is None:
                statuses[tunnel_id] = "running"
            else:
                statuses[tunnel_id] = "error" if process.returncode != 0 else "stopped"
                # Clean up the ended process
                with self._lock:
                    self.active_tunnels.pop(tunnel_id, None)

        return statuses

    def get_tunnel_log(self, tunnel_id: str) -> str:
        with self._lock:
            log_deque = self.tunnel_logs.get(tunnel_id)
            if log_deque:
                return "".join(list(log_deque))
            return "No logs available for this tunnel yet."

