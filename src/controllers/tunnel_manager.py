import subprocess
import logging
import os
import threading
import time # Added for sleep
import signal
import re # Added for error parsing
from collections import deque
import tempfile

# --- *** ADD ctypes for Windows API call *** ---
import ctypes

class TunnelManager:
    def __init__(self, controller):
        self.controller = controller
        self.active_tunnels = {} # { tunnel_id: subprocess.Popen }
        self.tunnel_logs = {} # { tunnel_id: deque() }
        self.tunnel_error_messages = {} # { tunnel_id: "error message" }
        self.ssh_executable = "C:\\Windows\\System32\\OpenSSH\\ssh.exe"
        self._lock = threading.Lock()

        self._is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_tunnels, daemon=True)
        self.monitor_thread.start()

    def stop(self):
        """Stops the monitoring thread, waits for it, then stops tunnels."""
        logging.info("Stopping tunnel monitor.")
        self._is_monitoring = False
        if self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=3)
            if self.monitor_thread.is_alive():
                logging.warning("Tunnel monitor thread did not exit cleanly.")
        self.stop_all_tunnels()


    def stop_all_tunnels(self):
        """Stops all currently active tunnel processes."""
        logging.info("Stopping all active tunnels...")
        with self._lock:
            tunnel_ids = list(self.active_tunnels.keys())

        if not tunnel_ids:
            logging.info("No active tunnels to stop.")
            return

        for tunnel_id in tunnel_ids:
            self.stop_tunnel(tunnel_id, refresh_ui=False)

        logging.info("All active tunnels stopped.")
        self.controller.refresh_dashboard()


    def _monitor_tunnels(self):
        """A background thread that periodically checks for crashed tunnels."""
        while self._is_monitoring:
            try:
                exited_tunnels_ids = []
                with self._lock:
                    for tid, process in list(self.active_tunnels.items()):
                        if process and process.poll() is not None:
                            exited_tunnels_ids.append(tid)
                            self.active_tunnels.pop(tid, None) 

                if exited_tunnels_ids:
                    logging.info(f"Monitor detected exited tunnels: {exited_tunnels_ids}.")
                    self.controller.after(0, self.controller.refresh_dashboard)

                time.sleep(5)

            except Exception as e:
                 logging.error(f"Error in tunnel monitor thread: {e}", exc_info=True)
                 time.sleep(10)

    def _stream_reader(self, stream, tunnel_id, stream_name):
        """Reads output from a stream, logs it, and parses for errors."""
        with self._lock:
            if tunnel_id not in self.tunnel_logs:
                self.tunnel_logs[tunnel_id] = deque(maxlen=500)
                self.tunnel_logs[tunnel_id].append(f"--- Log stream initialized ---\n")

        if stream_name == 'stderr':
            with self._lock:
                self.tunnel_error_messages.pop(tunnel_id, None)

        try:
            for line in iter(stream.readline, ''):
                if not line: break
                log_line = f"[{stream_name.upper()}] {line.strip()}"
                is_debug_line = line.strip().lower().startswith('debug')
                if not is_debug_line: logging.info(f"[TUNNEL:{tunnel_id}] {log_line}")
                with self._lock:
                    if tunnel_id in self.tunnel_logs: self.tunnel_logs[tunnel_id].append(log_line + "\n")
                if stream_name == 'stderr':
                    line_lower = line.lower(); error_msg = None
                    if "remote port forwarding failed" in line_lower: error_msg = "Port in use on server"
                    elif "permission denied" in line_lower: error_msg = "Permission denied (Key?)"
                    elif "could not resolve hostname" in line_lower: error_msg = "Server host not found"
                    elif "connection refused" in line_lower: error_msg = "Connection refused by server"
                    elif "no route to host" in line_lower: error_msg = "No route to host"
                    elif "exitonforwardfailure=yes" in line_lower and ("forwarding failed" in line_lower or "cannot listen" in line_lower): error_msg = "Forwarding setup failed"
                    elif "bad file descriptor" in line_lower: error_msg = "Bad file descriptor (Internal Error)"
                    if error_msg:
                        with self._lock:
                            if tunnel_id not in self.tunnel_error_messages:
                                self.tunnel_error_messages[tunnel_id] = error_msg
                                logging.warning(f"[TUNNEL:{tunnel_id}] Detected error: {error_msg}")
        except ValueError: logging.debug(f"Stream {stream_name} for tunnel {tunnel_id} closed (ValueError).")
        except Exception as e: logging.error(f"Error reading from {stream_name} for tunnel {tunnel_id}: {e}")
        finally:
            try:
                if stream: stream.close()
            except Exception: pass
            logging.debug(f"Stream {stream_name} for tunnel {tunnel_id} closed.")

    def start_tunnel(self, tunnel_id: str) -> tuple[bool, str]:
        with self._lock:
            if tunnel_id in self.active_tunnels:
                process = self.active_tunnels.get(tunnel_id)
                if process and process.poll() is None:
                    msg = f"Tunnel {tunnel_id} is already running."; logging.warning(msg); return True, msg
                else:
                    logging.debug(f"Found dead process handle for {tunnel_id}, allowing restart.")
                    self.active_tunnels.pop(tunnel_id, None)

            self.tunnel_error_messages.pop(tunnel_id, None)
            self.tunnel_logs.pop(tunnel_id, None)

            tunnel_config = self.controller.get_object_by_id(tunnel_id)
            if not tunnel_config: return False, "Tunnel configuration not found."

            my_device_id = self.controller.get_my_device_id()
            assigned_device_id = tunnel_config.get('client_device_id')
            if not assigned_device_id or assigned_device_id != my_device_id:
                name = self.controller.get_client_name(assigned_device_id) or "another device"
                msg = f"Cannot start tunnel. It is assigned to '{name}'."; logging.info(msg); return False, msg

            server_config = self.controller.get_object_by_id(tunnel_config.get('server_id'))
            if not server_config: return False, "Server config not found."

            automation_creds = self.controller.get_automation_credentials()
            if not automation_creds:
                msg = "Automation credentials (SSH key) not found."; logging.error(msg)
                return False, f"{msg}\nPlease configure in Settings."

            ssh_key_path = automation_creds.get('ssh_private_key_path')
            if not ssh_key_path or not os.path.exists(ssh_key_path):
                msg = f"SSH key not found at path: {ssh_key_path}"; logging.error(msg)
                return False, f"{msg}\nPlease correct in Settings."

            tunnel_user = server_config.get('tunnel_user') or "tunnel"

            command = [
                self.ssh_executable,
                '-v',
                '-i', ssh_key_path,
                '-o', "ServerAliveInterval=30",
                '-o', "ExitOnForwardFailure=yes",
                '-o', "StrictHostKeyChecking=no",
                '-o', "UserKnownHostsFile=nul",
                '-4',
                # '-N' IS REMOVED
                '-R', f"{tunnel_config['remote_port']}:{tunnel_config['local_destination']}",
                f"{tunnel_user}@{server_config['ip_address']}",
                # --- *** THIS IS THE FIX *** ---
                # Send the hostname and port as the command.
                # This populates $SSH_ORIGINAL_COMMAND on the server.
                f"{tunnel_config['hostname']} {tunnel_config['remote_port']}"
                # --- *** END FIX *** ---
            ]

            logging.info(f"Starting tunnel '{tunnel_config['hostname']}' (ID: {tunnel_id})")
            logging.debug(f"SSH command list: {command}")
            try:
                startupinfo = None
                creationflags = 0
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                
                preexec_fn = os.setsid if os.name != 'nt' else None

                process = subprocess.Popen(
                    command, shell=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    startupinfo=startupinfo,
                    creationflags=creationflags,
                    preexec_fn=preexec_fn
                )
                
                self.active_tunnels[tunnel_id] = process

                self.tunnel_logs[tunnel_id] = deque(maxlen=500)
                self.tunnel_logs[tunnel_id].append(f"--- Tunnel process starting... ---\n")

                threading.Thread(target=self._stream_reader, args=(process.stdout, tunnel_id, "stdout"), daemon=True).start()
                threading.Thread(target=self._stream_reader, args=(process.stderr, tunnel_id, "stderr"), daemon=True).start()

                if hasattr(self.controller, 'after'):
                    self.controller.after(0, self.controller.refresh_dashboard)

                return True, "Tunnel process started."
            except FileNotFoundError:
                msg = f"SSH executable not found at '{self.ssh_executable}'."; logging.error(msg)
                self.active_tunnels.pop(tunnel_id, None); return False, msg
            except Exception as e:
                msg = f"An unexpected error occurred while starting the tunnel: {e}"; logging.error(msg, exc_info=True)
                self.active_tunnels.pop(tunnel_id, None); return False, msg
            
    # --- *** REVISED stop_tunnel (Use GenerateConsoleCtrlEvent) *** ---
    def stop_tunnel(self, tunnel_id: str, refresh_ui: bool = True):
        """Stops a specific tunnel process, trying GenerateConsoleCtrlEvent first on Windows."""
        logging.debug(f"Attempting to stop tunnel {tunnel_id}. Refresh UI: {refresh_ui}")
        process_handle = None
        pid_to_kill = None
        terminated_gracefully = False

        with self._lock:
            self.tunnel_error_messages.pop(tunnel_id, None)
            process_handle = self.active_tunnels.pop(tunnel_id, None) # Remove entry first

            if not process_handle:
                logging.debug(f"[{tunnel_id}] Tunnel ID not found in active_tunnels (already stopped?).")
            elif process_handle.poll() is not None:
                logging.debug(f"[{tunnel_id}] Process (PID: {process_handle.pid}) already terminated before stop attempt.")
                process_handle = None # Don't try to stop a dead process
            else:
                pid_to_kill = process_handle.pid
                logging.info(f"[{tunnel_id}] Process (PID: {pid_to_kill}) is running. Attempting graceful shutdown...")

        # --- Termination logic (outside the lock) ---
        if process_handle and pid_to_kill:
            try:
                # 1. Try graceful shutdown
                if os.name == 'nt':
                    # --- *** Use GenerateConsoleCtrlEvent API *** ---
                    logging.debug(f"[{tunnel_id}] Sending CTRL_CLOSE_EVENT via GenerateConsoleCtrlEvent to PID {pid_to_kill}...")
                    # Arguments: (event_type, process_group_id)
                    # Use pid as process_group_id because of CREATE_NEW_PROCESS_GROUP
                    CTRL_CLOSE_EVENT = 2
                    if ctypes.windll.kernel32.GenerateConsoleCtrlEvent(CTRL_CLOSE_EVENT, pid_to_kill):
                         logging.debug(f"[{tunnel_id}] GenerateConsoleCtrlEvent call succeeded.")
                    else:
                         # Get error code if the API call itself failed
                         error_code = ctypes.windll.kernel32.GetLastError()
                         logging.error(f"[{tunnel_id}] GenerateConsoleCtrlEvent call failed. Error code: {error_code}")
                         # If API call fails, we can't rely on graceful, force fallback
                         raise OSError(f"GenerateConsoleCtrlEvent failed with code {error_code}")
                else:
                    # On Linux/macOS, send SIGTERM to the process group
                    logging.debug(f"[{tunnel_id}] Sending SIGTERM to process group {os.getpgid(pid_to_kill)}...")
                    os.killpg(os.getpgid(pid_to_kill), signal.SIGTERM)

                # Wait for the process to exit (regardless of platform)
                process_handle.wait(timeout=5) # Increase timeout slightly for API call
                logging.info(f"[{tunnel_id}] Process (PID: {pid_to_kill}) terminated gracefully.")
                terminated_gracefully = True

            except subprocess.TimeoutExpired:
                logging.warning(f"[{tunnel_id}] Graceful shutdown timed out. Forcing kill...")
                terminated_gracefully = False
            except ProcessLookupError: 
                 logging.info(f"[{tunnel_id}] Process not found during graceful shutdown (already terminated).")
                 terminated_gracefully = True
            except OSError as e: # Catch API call failure or other OS errors
                 logging.warning(f"[{tunnel_id}] OSError during graceful shutdown: {e}. Forcing kill...")
                 terminated_gracefully = False
            except Exception as e:
                logging.warning(f"[{tunnel_id}] Error during graceful shutdown: {e}. Forcing kill...")
                terminated_gracefully = False 

            # 2. If graceful failed, force-kill
            if not terminated_gracefully:
                try:
                    if os.name == 'nt':
                        logging.debug(f"[{tunnel_id}] Using taskkill /T /F on PID {pid_to_kill}...")
                        result = subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid_to_kill), "/T"],
                            check=False, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5
                        )
                        if result.returncode == 0:
                            logging.info(f"[{tunnel_id}] Successfully force-terminated process tree for PID {pid_to_kill}.")
                        elif result.returncode == 128:
                            logging.info(f"[{tunnel_id}] taskkill failed (rc=128), process not found (already terminated).")
                        else:
                            logging.warning(f"[{tunnel_id}] taskkill failed for PID {pid_to_kill}. RC: {result.returncode}, Stderr: {result.stderr.decode('utf-8', 'ignore')}")
                    else: 
                        logging.debug(f"[{tunnel_id}] Using process.kill() on PID {pid_to_kill}...")
                        process_handle.kill()
                        process_handle.wait(timeout=2)
                        logging.info(f"[{tunnel_id}] Successfully force-killed process (PID: {pid_to_kill}).")
                except Exception as e:
                    logging.error(f"[{tunnel_id}] Error during forceful termination: {e}")

        if refresh_ui:
            logging.debug(f"[{tunnel_id}] Scheduling UI refresh...")
            try:
                if hasattr(self.controller, 'after'): self.controller.after(0, self.controller.refresh_dashboard)
                else: logging.error(f"[{tunnel_id}] Controller has no 'after' method.")
            except Exception as e: logging.error(f"[{tunnel_id}] Error scheduling UI refresh: {e}")

        logging.debug(f"[{tunnel_id}] stop_tunnel method finished.")


    def start_all_tunnels(self):
        """Starts tunnels marked for auto-start on this device."""
        logging.info("Starting auto-start tunnels assigned to this device...")
        my_device_id = self.controller.get_my_device_id()
        all_tunnels = self.controller.get_tunnels()

        tunnels_to_start = [
            t for t in all_tunnels
            if my_device_id in t.get('auto_start_on_device_ids', [])
        ]

        logging.info(f"Found {len(tunnels_to_start)} tunnels configured to auto-start on this device.")
        started_count = 0
        failed_count = 0
        for tunnel in tunnels_to_start:
            success, _ = self.start_tunnel(tunnel['id'])
            if success: started_count += 1
            else: failed_count += 1

        logging.info(f"Attempted to start {started_count} auto-start tunnels ({failed_count} failures).")
        self.controller.after(50, self.controller.refresh_dashboard)

    def get_tunnel_statuses(self) -> dict:
        """Gets the status of all tunnels."""
        statuses = {}
        processed_ids = set()

        with self._lock:
            active_ids = list(self.active_tunnels.keys())

        for tunnel_id in active_ids:
            process = None
            with self._lock:
                process = self.active_tunnels.get(tunnel_id)

            if process is None: continue

            exit_code = process.poll()

            if exit_code is None:
                statuses[tunnel_id] = {'status': 'running', 'message': 'Connected'}
                processed_ids.add(tunnel_id)
            else: 
                with self._lock:
                    error_msg = self.tunnel_error_messages.get(tunnel_id, f"Exited unexpectedly (Code: {exit_code})")
                    self.active_tunnels.pop(tunnel_id, None) 

                logging.warning(f"Tunnel {tunnel_id} found exited unexpectedly. Status message: {error_msg}")
                statuses[tunnel_id] = {'status': 'error', 'message': error_msg}
                processed_ids.add(tunnel_id)

        all_tunnel_configs = self.controller.get_tunnels()
        my_device_id = self.controller.get_my_device_id()

        for tunnel in all_tunnel_configs:
            tid = tunnel['id']
            if tid not in processed_ids:
                assigned_id = tunnel.get('client_device_id')
                if assigned_id == my_device_id:
                    statuses[tid] = {'status': 'stopped', 'message': 'Stopped'}
                elif not assigned_id:
                     statuses[tid] = {'status': 'stopped', 'message': 'Stopped (Unassigned)'}
                else:
                    client_name = self.controller.get_client_name(assigned_id) or "another device"
                    statuses[tid] = {'status': 'disabled', 'message': f'Managed by {client_name}'}

        return statuses

    def get_tunnel_log(self, tunnel_id: str) -> str:
        with self._lock:
            log_deque = self.tunnel_logs.get(tunnel_id)
            if log_deque: return "".join(list(log_deque))
            error_msg = self.tunnel_error_messages.get(tunnel_id)
            if error_msg: return f"--- Tunnel Exited with Error ---\n{error_msg}\n--- No further logs available ---"
            return "No logs available for this tunnel yet."