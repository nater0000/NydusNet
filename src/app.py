import customtkinter as ctk
import logging
import threading
import os
import socket
from PIL import Image
import pystray
from tkinter import filedialog
import time

from views.dashboard_view import DashboardView
from views.settings_view import SettingsView
from views.history_view import HistoryView
from views.debug_view import DebugView
from views.dialogs import (
    UnlockDialog, ServerDialog, TunnelDialog, InviteDialog,
    ConfirmationDialog, RecoveryKeyDialog, ErrorDialog, LoadingDialog, LogViewerDialog,
    ProvisionDialog, ProvisioningLogDialog
)

from controllers.config_manager import ConfigManager
from controllers.tunnel_manager import TunnelManager
from controllers.syncthing_manager import SyncthingManager
from controllers.server_provisioner import ServerProvisioner
from utils.crypto import CryptoManager

class App(ctk.CTk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.title("NydusNet")
        self.geometry("420x300")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.is_unlocked = False
        self.is_shutting_down = False
        self.syncthing_id_ready = threading.Event()

        self.config_manager = ConfigManager(self)
        self.syncthing_manager = SyncthingManager(self)
        self.tunnel_manager = TunnelManager(self)
        self.crypto_manager = CryptoManager()

        container = ctk.CTkFrame(self)
        container.pack(side="top", fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for F in (DashboardView, SettingsView, HistoryView, DebugView):
            page_name = F.__name__
            frame = F(parent=container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.withdraw()
        self.after(100, self.show_unlock_dialog)
        self.tray_icon = None

    def on_syncthing_id_ready(self):
        """Callback from SyncthingManager when the device ID is available."""
        logging.info("Syncthing ID is ready. Refreshing relevant views.")
        self.syncthing_id_ready.set()
        if self.frames["SettingsView"].winfo_viewable():
            self.after(0, self.frames["SettingsView"].enter)
        self.after(0, self.refresh_dashboard)

    def _setup_tray_icon(self):
        try:
            base_path = getattr(os, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
            icon_path = os.path.join(base_path, "resources", "images", "nydusnet.ico")
            icon_image = Image.open(icon_path)
        except Exception:
            logging.warning("System tray icon not found, using a placeholder.")
            icon_image = Image.new('RGB', (64, 64), color='blue')

        menu = (
            pystray.MenuItem('Show', self.show_window, default=True),
            pystray.MenuItem('Quit', self.quit_application)
        )
        self.tray_icon = pystray.Icon("NydusNet", icon_image, "NydusNet", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def quit_application(self):
        logging.info("Quit command received from tray icon.")
        if self.tray_icon:
            self.tray_icon.stop()
        self.on_closing(force_quit=True)

    def on_closing(self, force_quit=False):
        if force_quit:
            if not self.is_shutting_down:
                self.is_shutting_down = True
                logging.info("Application closing. Shutting down services...")
                if self.is_unlocked:
                    self.tunnel_manager.stop()
                    self.syncthing_manager.stop()
                self.after(200, self.destroy)
        else:
            logging.info("Minimizing to system tray.")
            self.withdraw()

    def show_unlock_dialog(self):
        if self.is_unlocked: return
        is_first_run = not self.config_manager.is_configured()
        dialog = UnlockDialog(self, first_run=is_first_run, controller=self)
        password = dialog.get_input()

        if password is None:
            self.destroy()
            return

        if is_first_run:
            self.handle_first_run(password)
        else:
            self.attempt_unlock(password)

    def handle_first_run(self, password: str):
        unlock_successful, recovery_key = self.config_manager.unlock_with_password(password)
        if unlock_successful:
            self.is_unlocked = True
            logging.info("First run: Generating and saving SSH key pair for automation.")
            priv_path, pub_path = self.crypto_manager.generate_ssh_key_pair()
            self.save_or_update_automation_credentials(priv_path, pub_path)
            key_dialog = RecoveryKeyDialog(self, recovery_key=recovery_key)
            key_dialog.get_input()
            if not self.tray_icon: self._setup_tray_icon()
            self._start_backend_services_threaded()
        else:
            self.show_error("Failed to create password. Please try again.")
            self.show_unlock_dialog()

    def attempt_unlock(self, password: str):
        unlock_successful, _ = self.config_manager.unlock_with_password(password)
        if unlock_successful:
            self.is_unlocked = True
            if not self.tray_icon: self._setup_tray_icon()
            self._start_backend_services_threaded()
        else:
            self.show_error("Incorrect master password. Please try again.")
            self.show_unlock_dialog()

    def _start_backend_services_threaded(self):
        loading_dialog = LoadingDialog(self)
        def service_starter():
            if not self.syncthing_manager.start():
                self.after(0, loading_dialog.destroy)
                self.after(0, lambda: self.show_error("Syncthing failed to start. Check logs."))
                self.after(0, self.destroy)
            else:
                self.after(0, loading_dialog.destroy)
                self.after(0, self.deiconify)
                self.after(0, lambda: self.show_frame("DashboardView"))
        threading.Thread(target=service_starter, daemon=True).start()

    def forgot_password(self):
        logging.info("Starting password reset workflow.")
        recovery_dialog = RecoveryKeyDialog(self, title="Password Reset", input_mode=True)
        recovery_key = recovery_dialog.get_input()
        if not recovery_key: return

        new_password_dialog = UnlockDialog(self, first_run=True, title="Create New Master Password")
        new_password = new_password_dialog.get_input()
        if not new_password: return
        
        if self.config_manager.re_encrypt_with_new_password(old_key=recovery_key, new_password=new_password):
            logging.info("Password successfully reset.")
            self.attempt_unlock(new_password)
        else:
            self.show_error("Password reset failed. The recovery key was likely incorrect.")
            self.show_unlock_dialog()

    def change_master_password(self):
        logging.info("Starting master password change workflow.")
        old_password_dialog = UnlockDialog(self, title="Enter Old Master Password")
        old_password = old_password_dialog.get_input()
        if not old_password: return
        
        try:
            with open(self.config_manager.check_file, 'rb') as f:
                encrypted_check_data = f.read()
            if self.config_manager.crypto_manager.decrypt_data(encrypted_check_data, old_password):
                new_password_dialog = UnlockDialog(self, first_run=True, title="Enter New Master Password")
                new_password = new_password_dialog.get_input()
                if not new_password: return
                if self.config_manager.re_encrypt_with_new_password(old_key=old_password, new_password=new_password):
                    ConfirmationDialog(self, title="Success", message="Password successfully changed!")
                else:
                    self.show_error("Failed to change password during re-encryption.")
            else:
                self.show_error("Incorrect old password.")
        except Exception as e:
            self.show_error(f"An error occurred: {e}")

    def view_recovery_key(self):
        logging.info("Attempting to display recovery key.")
        recovery_key = self.config_manager.get_recovery_key()
        if recovery_key:
            RecoveryKeyDialog(self, recovery_key=recovery_key)
        else:
            self.show_error("Recovery key not found or could not be decrypted.")

    def show_frame(self, page_name: str):
        if not self.is_unlocked: return
        logging.info(f"Switching to view: {page_name}")
        frame = self.frames[page_name]
        if hasattr(frame, 'enter') and callable(getattr(frame, 'enter')):
            frame.enter()
        frame.tkraise()

    def refresh_dashboard(self):
        if self.is_shutting_down: return
        dashboard = self.frames.get("DashboardView")
        if dashboard and self.is_unlocked:
            self.after(0, dashboard.load_tunnels)

    def show_error(self, message: str):
        ErrorDialog(self, message=message)
        
    def set_appearance_mode(self, mode: str):
        logging.info(f"Setting appearance mode to: {mode}")
        ctk.set_appearance_mode(mode)

    def provision_server(self, server_id):
        server = self.get_object_by_id(server_id)
        if not server:
            self.show_error("Server not found."); return

        dialog = ProvisionDialog(self, server['name'], server['ip_address'])
        creds = dialog.get_input()
        if not creds: return

        creds_obj = self.get_automation_credentials()
        if not creds_obj or not creds_obj.get('ssh_public_key_path'):
            self.show_error("Public SSH key not configured. Please check Security settings.")
            return
        
        pub_key_path = creds_obj['ssh_public_key_path']
        try:
            with open(pub_key_path, 'r') as f:
                pub_key_string = f.read().strip()
        except FileNotFoundError:
            self.show_error(f"Public SSH key not found at path:\n{pub_key_path}")
            return
            
        provisioner = ServerProvisioner(server['ip_address'], creds['user'], creds['password'], pub_key_string)
        log_dialog = ProvisioningLogDialog(self, server['name'])

        def run_in_thread():
            success, final_log = provisioner.run()
            self.after(0, lambda: log_dialog.complete(success))
            if success:
                updated_server = server.copy()
                updated_server['is_provisioned'] = True
                if not updated_server.get('tunnel_user'):
                    updated_server['tunnel_user'] = "tunnel"
                self.config_manager.update_object(server_id, updated_server)
                self.after(10, self.frames["SettingsView"].enter)
        
        def log_monitor():
            while provision_thread.is_alive():
                self.after(100, lambda: log_dialog.update_log(provisioner.log_output))
                time.sleep(0.2)
            self.after(0, lambda: log_dialog.update_log(provisioner.log_output))

        provision_thread = threading.Thread(target=run_in_thread, daemon=True)
        provision_thread.start()
        monitor_thread = threading.Thread(target=log_monitor, daemon=True)
        monitor_thread.start()

    # --- Passthrough Methods ---
    def get_all_objects_for_debug(self): return self.config_manager.get_all_objects_for_debug()
    def get_object_by_id(self, obj_id: str): return self.config_manager.get_object_by_id(obj_id)
    def get_tunnels(self): return self.config_manager.get_tunnels()
    def get_servers(self): return self.config_manager.get_servers()
    def get_clients(self): return self.config_manager.get_clients()
    def get_server_name(self, server_id): return self.config_manager.get_server_name(server_id)
    def get_client_name(self, client_id): return self.config_manager.get_client_name(client_id)
    def get_automation_credentials(self): return self.config_manager.get_automation_credentials()
    def get_my_device_id(self): return self.syncthing_manager.my_device_id
    def get_my_device_name(self):
        try: return socket.gethostname()
        except Exception: return "Unknown Device"
    def get_clients_for_dropdown(self):
        clients = self.get_clients()
        my_id = self.get_my_device_id()
        my_name = f"{self.get_my_device_name()} (This Device)"
        client_map = {my_name: my_id}
        for client in clients:
            if client.get('syncthing_id') != my_id:
                name = client.get('name', client.get('syncthing_id', 'Unknown'))
                client_map[name] = client.get('syncthing_id')
        return client_map, sorted(list(client_map.keys()))
    def save_or_update_automation_credentials(self, priv, pub): self.config_manager.save_or_update_automation_credentials(priv, pub)
    def browse_for_file(self, title="Select a file"): return filedialog.askopenfilename(title=title)
    def add_new_tunnel(self):
        if not any(s.get('is_provisioned') for s in self.get_servers()):
            self.show_error("You must register and provision a Server before creating a tunnel.")
            return
        dialog = TunnelDialog(self, controller=self, title="Add New Tunnel")
        data = dialog.get_input()
        if data:
            new_id = self.config_manager.add_object('tunnel', data)
            if data.get('enabled') and data.get('assigned_client_id') == self.get_my_device_id():
                self.start_tunnel(new_id)
            self.refresh_dashboard()
    def edit_tunnel(self, tunnel_id):
        tunnel_data = self.get_object_by_id(tunnel_id)
        dialog = TunnelDialog(self, controller=self, title="Edit Tunnel", initial_data=tunnel_data)
        new_data = dialog.get_input()
        if new_data: self.config_manager.update_object(tunnel_id, new_data); self.refresh_dashboard()
    def delete_tunnel(self, tunnel_id):
        tunnel = self.get_object_by_id(tunnel_id)
        if not tunnel: return
        dialog = ConfirmationDialog(self, message=f"Delete tunnel '{tunnel.get('hostname')}'?")
        if dialog.get_input(): self.stop_tunnel(tunnel_id); self.config_manager.delete_object(tunnel_id); self.refresh_dashboard()
    def view_tunnel_log(self, tunnel_id: str):
        logs = self.tunnel_manager.get_tunnel_log(tunnel_id); tunnel = self.get_object_by_id(tunnel_id)
        title = f"Logs for {tunnel.get('hostname', tunnel_id[:8])}"; LogViewerDialog(self, log_content=logs, title=title)
    def start_tunnel(self, tunnel_id: str):
        success, message = self.tunnel_manager.start_tunnel(tunnel_id)
        if not success: self.show_error(message)
        self.refresh_dashboard()
    def stop_tunnel(self, tunnel_id: str): self.tunnel_manager.stop_tunnel(tunnel_id); self.refresh_dashboard()
    def start_all_tunnels(self): self.tunnel_manager.start_all_tunnels()
    def stop_all_tunnels(self): self.tunnel_manager.stop_all_tunnels()
    def get_tunnel_statuses(self): return self.tunnel_manager.get_tunnel_statuses()
    def add_new_device(self):
        invite_string = self.syncthing_manager.generate_invite()
        if invite_string: InviteDialog(self, invite_string=invite_string)
    def add_new_server(self):
        dialog = ServerDialog(self, title="Register New Server")
        server_info = dialog.get_input()
        if server_info: self.config_manager.add_object('server', server_info); self.frames["SettingsView"].enter()
    def edit_server(self, server_id):
        server_data = self.get_object_by_id(server_id)
        dialog = ServerDialog(self, title="Edit Server", initial_data=server_data)
        new_data = dialog.get_input()
        if new_data: self.config_manager.update_object(server_id, new_data); self.frames["SettingsView"].enter()
    def delete_server(self, server_id):
        server_name = self.config_manager.get_server_name(server_id)
        dialog = ConfirmationDialog(self, message=f"Delete server '{server_name}'?")
        if dialog.get_input(): self.config_manager.delete_object(server_id); self.frames["SettingsView"].enter()
    def remove_client(self, client_id):
        client_name = self.get_client_name(client_id)
        dialog = ConfirmationDialog(self, message=f"Remove device '{client_name}'?")
        if dialog.get_input():
            self.syncthing_manager.remove_device(client_id)
            client_to_delete = next((c for c in self.get_clients() if c.get('syncthing_id') == client_id), None)
            if client_to_delete: self.config_manager.delete_object(client_to_delete['id'])
            self.frames["SettingsView"].enter()
    def get_history_file_index(self): return self.config_manager.get_history_file_index()
    def get_file_version_history(self, file_id): return self.config_manager.get_file_version_history(file_id)
    def get_file_content_at_version(self, file_id, timestamp): return self.config_manager.get_file_content_at_version(file_id, timestamp)

