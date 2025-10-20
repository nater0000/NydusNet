import customtkinter as ctk
import qrcode
from PIL import Image
import logging
import re
import os

class ToolTip(ctk.CTkToplevel):
    def __init__(self, widget, text):
        # THE FIX: Wrap initialization to prevent creating zombie objects
        try:
            if not widget or not widget.winfo_exists():
                logging.warning("ToolTip's parent widget does not exist. Aborting creation.")
                self._is_valid = False
                return
            
            super().__init__(widget)
            self.widget = widget
            self.text = text
            self._is_valid = True
            self.withdraw()
            self.overrideredirect(True)
            self.label = ctk.CTkLabel(self, text=self.text, corner_radius=5, fg_color="#3D3D3D", wraplength=200)
            self.label.pack(ipadx=5, ipady=3)
            self.widget.bind("<Enter>", self.show, add="+")
            self.widget.bind("<Leave>", self.hide, add="+")
        except Exception as e:
            self._is_valid = False
            logging.warning(f"ToolTip creation failed, likely due to a race condition: {e}")
            if self.winfo_exists():
                self.destroy()

    def show(self, event):
        try:
            if not getattr(self, '_is_valid', False) or not self.widget.winfo_exists() or not self.winfo_exists(): return
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + 20
            self.geometry(f"+{x}+{y}")
            self.deiconify()
        except Exception:
            pass

    def hide(self, event):
        try:
            if not getattr(self, '_is_valid', False) or not self.winfo_exists(): return
            self.withdraw()
        except Exception:
            pass

    def destroy(self):
        if hasattr(self, 'widget') and self.widget and self.widget.winfo_exists():
            try:
                self.widget.unbind("<Enter>")
                self.widget.unbind("<Leave>")
            except Exception:
                pass
        if self.winfo_exists():
            super().destroy()

class BaseDialog(ctk.CTkToplevel):
    def __init__(self, parent, title="Dialog"):
        super().__init__(parent)
        self.title(title)
        self.result = None
        self._parent = parent
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # --- FIX: Store the 'after' ID ---
        self._center_window_after_id = self.after(50, self._center_window)

    def _center_window(self):
        # --- FIX: Clear the ID after it runs ---
        self._center_window_after_id = None

        # Check if window still exists before trying to update it
        if not self.winfo_exists():
            return

        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"+{x}+{y}")

    def _on_ok(self, event=None):
        # --- FIX: Consolidate cleanup into destroy() ---
        self.destroy()

    def _on_cancel(self):
        self.result = None
        # --- FIX: Consolidate cleanup into destroy() ---
        self.destroy()

    def get_input(self):
        self.wait_window()
        return self.result

    # --- FIX: Add a new, safer destroy method ---
    def destroy(self):
        # Safely cancel any pending 'after' tasks
        if hasattr(self, '_center_window_after_id') and self._center_window_after_id:
            self.after_cancel(self._center_window_after_id)
            self._center_window_after_id = None

        # Safely release grab
        try:
            self.grab_release()
        except Exception:
            pass # Window might already be gone

        # Call the original CTkToplevel destroy
        if self.winfo_exists():
            super().destroy()
            
class UnlockDialog(BaseDialog):
    def __init__(self, parent, first_run: bool = False, controller=None, title=None):
        title = title or ("Create Master Password" if first_run else "Unlock NydusNet")
        super().__init__(parent, title=title)
        self.controller = controller
        self.first_run = first_run
        
        # --- Get images from controller, which loaded them in app.py ---
        try:
            # Check if controller and images exist
            if self.controller and hasattr(self.controller, 'images'):
                self.show_icon = self.controller.images.get("eye-show")
                self.hide_icon = self.controller.images.get("eye-hide")
                self.bg_image = self.controller.images.get("bg_gradient")
            else:
                raise ValueError("Controller or images not available")

            if not self.show_icon or not self.hide_icon:
                raise ValueError("Eye icons not found")
                
            self.use_image_icons = True
        except Exception as e:
            logging.warning(f"Icons not found ({e}). Show/hide password feature will use text.")
            self.show_icon = "👁️"
            self.hide_icon = "🔒"
            self.use_image_icons = False
            self.bg_image = None
        
        # --- Set up background and main frame (from example_background_image.py) ---
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        if self.bg_image:
            self.bg_label = ctk.CTkLabel(self, text="", image=self.bg_image)
            self.bg_label.grid(row=0, column=0)
        
        # This frame holds the content, centered on the background
        self.main_frame = ctk.CTkFrame(self, corner_radius=10)
        # Place frame in the center of the bg image
        self.main_frame.grid(row=0, column=0, padx=30, pady=30, sticky="")
        
        # Set a minsize for the dialog
        self.geometry("400x300")
        self.resizable(False, False)

        if first_run:
            self._create_password_setup_ui()
        else:
            self._create_unlock_ui()
            
    def _toggle_password_visibility(self, entry, button):
        if entry.cget("show") == "*":
            entry.configure(show="")
            button.configure(image=self.hide_icon if self.use_image_icons else None, text=self.hide_icon if not self.use_image_icons else "")
        else:
            entry.configure(show="*")
            button.configure(image=self.show_icon if self.use_image_icons else None, text=self.show_icon if not self.use_image_icons else "")
            
    def _create_unlock_ui(self):
        # Widgets are now packed into self.main_frame
        ctk.CTkLabel(self.main_frame, text="NydusNet", font=ctk.CTkFont(size=20, weight="bold")).pack(padx=30, pady=(30, 10))
        ctk.CTkLabel(self.main_frame, text="Enter Master Password:").pack(padx=30, pady=(10, 0))
        
        entry_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        entry_frame.pack(padx=30, pady=10)
        
        self.entry1 = ctk.CTkEntry(entry_frame, show="*", width=200) # Reduced width
        self.entry1.pack(side="left")
        self.entry1.bind("<Return>", self._on_ok)
        self.after(10, self.entry1.focus_set)
        
        toggle_btn1 = ctk.CTkButton(entry_frame, image=self.show_icon if self.use_image_icons else None, 
                                    text=self.show_icon if not self.use_image_icons else "", 
                                    width=28, command=lambda: self._toggle_password_visibility(self.entry1, toggle_btn1))
        toggle_btn1.pack(side="left", padx=(5, 0))
        
        button_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        button_frame.pack(padx=30, pady=(10, 20))
        
        ctk.CTkButton(button_frame, text="Unlock", command=self._on_ok, width=110).pack(side="left", padx=5)
        ctk.CTkButton(button_frame, text="Forgot Password?", command=self._on_forgot, width=110, fg_color="transparent", border_width=1).pack(side="left", padx=5)

    def _create_password_setup_ui(self):
        # Widgets are now packed into self.main_frame
        ctk.CTkLabel(self.main_frame, text="Welcome to NydusNet", font=ctk.CTkFont(size=20, weight="bold")).pack(padx=30, pady=(30, 10))
        ctk.CTkLabel(self.main_frame, text="Create a New Master Password:").pack(padx=30, pady=(10, 0))
        
        entry_frame1 = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        entry_frame1.pack(padx=30, pady=5)
        self.entry1 = ctk.CTkEntry(entry_frame1, show="*", width=200)
        self.entry1.pack(side="left")
        self.after(10, self.entry1.focus_set)
        toggle_btn1 = ctk.CTkButton(entry_frame1, image=self.show_icon if self.use_image_icons else None, text=self.show_icon if not self.use_image_icons else "", width=28, command=lambda: self._toggle_password_visibility(self.entry1, toggle_btn1))
        toggle_btn1.pack(side="left", padx=(5, 0))
        
        ctk.CTkLabel(self.main_frame, text="Confirm Master Password:").pack(padx=30, pady=(10, 0))
        entry_frame2 = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        entry_frame2.pack(padx=30, pady=5)
        self.entry2 = ctk.CTkEntry(entry_frame2, show="*", width=200)
        self.entry2.pack(side="left")
        self.entry2.bind("<Return>", self._on_ok)
        toggle_btn2 = ctk.CTkButton(entry_frame2, image=self.show_icon if self.use_image_icons else None, text=self.show_icon if not self.use_image_icons else "", width=28, command=lambda: self._toggle_password_visibility(self.entry2, toggle_btn2))
        toggle_btn2.pack(side="left", padx=(5, 0))
        
        ctk.CTkLabel(self.main_frame, text="Allowed characters: A-Z, a-z, 0-9, and !@#$%^&*()_+-=[]{}|;:,.<>?", font=("", 10), wraplength=250).pack(padx=30, pady=5)
        ctk.CTkButton(self.main_frame, text="Create", command=self._on_ok, width=230).pack(padx=30, pady=20)

    def _on_ok(self, event=None):
        password = self.entry1.get()
        if self.first_run:
            password2 = self.entry2.get()
            allowed_chars = r"^[A-Za-z0-9!@#$%^&*()_+\-=\[\]{}|;:,.<>?]*$"
            if password != password2:
                ErrorDialog(self, message="Passwords do not match.")
                return
            if not password:
                ErrorDialog(self, message="Password cannot be empty.")
                return
            if not re.fullmatch(allowed_chars, password):
                ErrorDialog(self, message="Password contains invalid characters.")
                return
        self.result = password
        super()._on_ok()

    def _on_forgot(self):
        self.result = None
        self.grab_release()
        self.destroy()
        if self.controller:
            self.controller.forgot_password()

class LoadingDialog(BaseDialog):
    def __init__(self, parent, title="Loading..."):
        super().__init__(parent, title=title)
        ctk.CTkLabel(self, text="Please wait...").pack(padx=40, pady=40)
        self.protocol("WM_DELETE_WINDOW", lambda: None)

class ProvisionDialog(BaseDialog):
    def __init__(self, parent, server_name, server_ip):
        super().__init__(parent, title=f"Setup Server: {server_name}")
        ctk.CTkLabel(self, text=f"Enter administrative credentials for {server_ip}.\nThese are used once for setup and are NOT saved.", wraplength=350).pack(padx=20, pady=10)
        ctk.CTkLabel(self, text="Sudo Username:").pack(padx=20, pady=(10, 0), anchor="w")
        self.user_entry = ctk.CTkEntry(self, width=250)
        self.user_entry.pack(padx=20, pady=5, fill="x") # <-- **TYPO FIX**
        self.user_entry.insert(0, "root")
        ctk.CTkLabel(self, text="Sudo Password:").pack(padx=20, pady=(10, 0), anchor="w")
        self.pass_entry = ctk.CTkEntry(self, show="*", width=250)
        self.pass_entry.pack(padx=20, pady=5, fill="x")
        self.pass_entry.bind("<Return>", self._on_ok)
        self.after(100, self.pass_entry.focus_set)
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(padx=20, pady=20)
        ctk.CTkButton(button_frame, text="Begin Setup", command=self._on_ok).pack(side="left", padx=10)
        ctk.CTkButton(button_frame, text="Cancel", command=self._on_cancel).pack(side="left", padx=10)
        
    def _on_ok(self, event=None):
        user = self.user_entry.get()
        password = self.pass_entry.get()
        if not user or not password:
            ErrorDialog(self, message="Username and Password are required.")
            return
        self.result = {"user": user, "password": password}
        super()._on_ok()

class ProvisioningLogDialog(BaseDialog):
    def __init__(self, parent, server_name):
        super().__init__(parent, title=f"Setting up {server_name}...")
        self.geometry("600x400")
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.textbox = ctk.CTkTextbox(self, wrap="word", font=("Courier New", 12))
        self.textbox.pack(expand=True, fill="both", padx=10, pady=10)
        self.textbox.configure(state="disabled")
        self.status_label = ctk.CTkLabel(self, text="Provisioning in progress...")
        self.status_label.pack(pady=5)
        self.close_button = ctk.CTkButton(self, text="Close", command=self._on_cancel, state="disabled")
        self.close_button.pack(pady=10)
        
    def update_log(self, log_lines):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", "\n".join(log_lines))
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def complete(self, success):
        if success:
            self.status_label.configure(text="✅ Setup Complete!", text_color="green")
        else:
            self.status_label.configure(text="❌ Setup Failed. Check logs for details.", text_color="red")
        self.close_button.configure(state="normal")
        
class ServerDialog(BaseDialog):
    def __init__(self, parent, title="Server Details", initial_data=None):
        super().__init__(parent, title=title)
        self.initial_data = initial_data or {}
        ctk.CTkLabel(self, text="Server Name:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.name_entry = ctk.CTkEntry(self, width=250)
        self.name_entry.grid(row=0, column=1, padx=10, pady=5)
        self.name_entry.insert(0, self.initial_data.get("name", ""))
        ctk.CTkLabel(self, text="IP Address:").grid(row=1, column=0, padx=10, pady=5, sticky="w") # <-- **SYNTAX ERROR FIX**
        self.ip_entry = ctk.CTkEntry(self, width=250)
        self.ip_entry.grid(row=1, column=1, padx=10, pady=5)
        self.ip_entry.insert(0, self.initial_data.get("ip_address", ""))
        ctk.CTkLabel(self, text="Tunnel Username (Override):").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.tunnel_user_entry = ctk.CTkEntry(self, width=250)
        self.tunnel_user_entry.grid(row=2, column=1, padx=10, pady=5)
        self.tunnel_user_entry.insert(0, self.initial_data.get("tunnel_user", ""))
        ToolTip(self.tunnel_user_entry, "Advanced: Override the default 'tunnel' username.")
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=3, column=0, columnspan=2, padx=20, pady=20)
        ctk.CTkButton(button_frame, text="Save", command=self._on_ok).pack(side="left", padx=10)
        ctk.CTkButton(button_frame, text="Cancel", command=self._on_cancel).pack(side="left", padx=10)
        
    def _on_ok(self, event=None):
        name = self.name_entry.get()
        ip_address = self.ip_entry.get()
        tunnel_user = self.tunnel_user_entry.get()
        if not all([name, ip_address]):
            ErrorDialog(self, message="Server Name and IP Address are required.")
            return
        self.result = self.initial_data.copy()
        self.result.update({
            "name": name,
            "ip_address": ip_address,
            "tunnel_user": tunnel_user,
            "type": "server"
        })
        if "is_provisioned" not in self.result:
            self.result["is_provisioned"] = False
        super()._on_ok()
        
class TunnelDialog(BaseDialog):
    def __init__(self, parent, controller, title="Tunnel Details", initial_data=None):
        super().__init__(parent, title=title)
        self.controller = controller
        self.initial_data = initial_data or {}
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text="Server:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.server_map = {s['name']: s['id'] for s in self.controller.get_servers() if s.get('is_provisioned')}
        server_names = list(self.server_map.keys()) or ["No provisioned servers available"]
        self.server_menu = ctk.CTkOptionMenu(self, values=server_names)
        self.server_menu.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(self, text="Managed By:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.client_map, client_names = self.controller.get_clients_for_dropdown()
        self.client_menu = ctk.CTkOptionMenu(self, values=client_names)
        self.client_menu.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(self, text="Hostname:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        hostname_frame = ctk.CTkFrame(self, fg_color="transparent")
        hostname_frame.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        self.hostname_entry = ctk.CTkEntry(hostname_frame)
        self.hostname_entry.pack(side="left", fill="x", expand=True)
        hostname_help = ctk.CTkLabel(hostname_frame, text="?", width=20, cursor="hand2")
        hostname_help.pack(side="left", padx=(5,0))
        ToolTip(hostname_help, "The subdomain for this tunnel (e.g., 'service1').")
        ctk.CTkLabel(self, text="Remote Port:").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        remote_port_frame = ctk.CTkFrame(self, fg_color="transparent")
        remote_port_frame.grid(row=3, column=1, padx=10, pady=5, sticky="ew")
        self.remote_port_entry = ctk.CTkEntry(remote_port_frame)
        self.remote_port_entry.pack(side="left", fill="x", expand=True)
        remote_port_help = ctk.CTkLabel(remote_port_frame, text="?", width=20, cursor="hand2")
        remote_port_help.pack(side="left", padx=(5,0))
        ToolTip(remote_port_help, "The public port on your VPS (e.g., 443 for HTTPS).")
        ctk.CTkLabel(self, text="Local Destination:").grid(row=4, column=0, padx=10, pady=5, sticky="w")
        local_dest_frame = ctk.CTkFrame(self, fg_color="transparent")
        local_dest_frame.grid(row=4, column=1, padx=10, pady=5, sticky="ew") # <-- **SYNTAX ERROR FIX**
        self.local_dest_entry = ctk.CTkEntry(local_dest_frame)
        self.local_dest_entry.pack(side="left", fill="x", expand=True)
        local_dest_help = ctk.CTkLabel(local_dest_frame, text="?", width=20, cursor="hand2")
        local_dest_help.pack(side="left", padx=(5,0))
        ToolTip(local_dest_help, "Local address and port (e.g., 'localhost:3000').")
        if not self.server_map:
            self.server_menu.configure(state="disabled")
        elif self.initial_data.get("server_id"):
             for name, sid in self.server_map.items():
                if sid == self.initial_data["server_id"]:
                    self.server_menu.set(name)
        if self.initial_data.get("assigned_client_id"):
            for name, cid in self.client_map.items():
                if cid == self.initial_data["assigned_client_id"]:
                    self.client_menu.set(name)
        else:
            my_name = f"{self.controller.get_my_device_name()} (This Device)"
            if my_name in client_names:
                self.client_menu.set(my_name)
        self.hostname_entry.insert(0, self.initial_data.get("hostname", ""))
        self.remote_port_entry.insert(0, str(self.initial_data.get("remote_port", "")))
        self.local_dest_entry.insert(0, self.initial_data.get("local_destination", "localhost:8080"))
        self.enabled_var = ctk.BooleanVar(value=self.initial_data.get("enabled", False))
        self.enabled_check = ctk.CTkCheckBox(self, text="Start tunnel now", variable=self.enabled_var)
        self.enabled_check.grid(row=5, column=1, padx=10, pady=10, sticky="w")
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=6, column=0, columnspan=2, padx=20, pady=20)
        ctk.CTkButton(button_frame, text="Save", command=self._on_ok).pack(side="left", padx=10)
        ctk.CTkButton(button_frame, text="Cancel", command=self._on_cancel).pack(side="left", padx=10)
        
    def _on_ok(self, event=None):
        try:
            if not self.server_map: # <-- **TYPO FIX**
                ErrorDialog(self, message="Cannot save. A provisioned server must be selected.")
                return
            server_id = self.server_map.get(self.server_menu.get())
            client_id = self.client_map.get(self.client_menu.get())
            if not server_id or not client_id:
                ErrorDialog(self, message="A valid Server and Device must be selected.")
                return
            hostname = self.hostname_entry.get()
            remote_port = int(self.remote_port_entry.get())
            local_destination = self.local_dest_entry.get()
            if not all([hostname, local_destination]):
                ErrorDialog(self, message="Hostname and Local Destination are required.")
                return
            if ":" not in local_destination:
                ErrorDialog(self, message="Local Destination must include a port (e.g., localhost:3000).")
                return
            self.result = self.initial_data.copy()
            self.result.update({
                "type": "tunnel",
                "server_id": server_id,
                "assigned_client_id": client_id,
                "hostname": hostname,
                "remote_port": remote_port,
                "local_destination": local_destination,
                "enabled": self.enabled_var.get()
            })
            super()._on_ok()
        except ValueError:
            ErrorDialog(self, message="Invalid input: Remote Port must be a number.")
        except Exception as e:
            logging.error(f"Tunnel Dialog Error: {e}")
            ErrorDialog(self, message=f"An unexpected error occurred.")

class InviteDialog(BaseDialog):
    def __init__(self, parent, invite_string: str):
        super().__init__(parent, title="Add a New Device")
        ctk.CTkLabel(self, text="On your new device, scan this QR code or copy the string:").pack(padx=20, pady=10)
        qr_img_pil = qrcode.make(invite_string).resize((250, 250))
        self.qr_photo = ctk.CTkImage(light_image=qr_img_pil, dark_image=qr_img_pil, size=(250, 250))
        qr_label = ctk.CTkLabel(self, image=self.qr_photo, text="")
        qr_label.pack(padx=20, pady=10)
        invite_entry = ctk.CTkEntry(self, width=400)
        invite_entry.insert(0, invite_string)
        invite_entry.pack(padx=20, pady=10)
        ctk.CTkButton(self, text="Close", command=self._on_cancel).pack(pady=20)

class ConfirmationDialog(BaseDialog):
    def __init__(self, parent, title="Confirm", message="Are you sure?"):
        super().__init__(parent, title=title)
        ctk.CTkLabel(self, text=message, wraplength=300).pack(padx=20, pady=20)
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(padx=20, pady=20)
        ctk.CTkButton(button_frame, text="Yes", command=self._on_ok).pack(side="left", padx=10)
        ctk.CTkButton(button_frame, text="No", command=self._on_cancel).pack(side="left", padx=10)
        
    def _on_ok(self, event=None):
        self.result = True
        super()._on_ok()

class RecoveryKeyDialog(BaseDialog):
    def __init__(self, parent, recovery_key: str = None, input_mode: bool = False, title=None):
        title = title or ("Enter Recovery Key" if input_mode else "Save Your Recovery Key!")
        super().__init__(parent, title=title)
        if input_mode:
            ctk.CTkLabel(self, text="Enter your recovery key to reset your password:", wraplength=350).pack(padx=20, pady=10)
            self.key_entry = ctk.CTkEntry(self, width=350, font=("Courier", 14))
            self.key_entry.pack(padx=20, pady=10)
            self.after(10, self.key_entry.focus_set)
            self.key_entry.bind("<Return>", self._on_ok)
            button_frame = ctk.CTkFrame(self, fg_color="transparent")
            button_frame.pack(padx=20, pady=20)
            ctk.CTkButton(button_frame, text="OK", command=self._on_ok).pack(side="left", padx=10)
            ctk.CTkButton(button_frame, text="Cancel", command=self._on_cancel).pack(side="left", padx=10)
        else:
            ctk.CTkLabel(self, text="This is your recovery key. Save it in a secure place.", wraplength=350).pack(padx=20, pady=10)
            key_entry = ctk.CTkEntry(self, width=350, font=("Courier", 14))
            key_entry.insert(0, recovery_key)
            key_entry.configure(state="readonly")
            key_entry.pack(padx=20, pady=10)
            self.confirm_check_var = ctk.StringVar(value="off")
            confirm_check = ctk.CTkCheckBox(self, text="I have saved this key.", variable=self.confirm_check_var, onvalue="on", offvalue="off")
            confirm_check.pack(padx=20, pady=10)
            self.ok_button = ctk.CTkButton(self, text="Continue", command=self._on_ok, state="disabled")
            self.ok_button.pack(pady=20)
            self.confirm_check_var.trace_add("write", self._check_state)
            
    def _check_state(self, *args):
        if self.confirm_check_var.get() == "on":
            self.ok_button.configure(state="normal")
        else:
            self.ok_button.configure(state="disabled")
            
    def _on_ok(self, event=None):
        if hasattr(self, 'key_entry'):
            self.result = self.key_entry.get()
        else:
            self.result = True
        super()._on_ok()

class ErrorDialog(BaseDialog):
    def __init__(self, parent, message: str):
        super().__init__(parent, title="Error")
        ctk.CTkLabel(self, text=message, wraplength=300).pack(padx=20, pady=20)
        ok_button = ctk.CTkButton(self, text="OK", command=self._on_ok)
        ok_button.pack(pady=10)
        self.after(10, ok_button.focus_set)
        
class LogViewerDialog(BaseDialog):
    def __init__(self, parent, log_content: str, title: str = "Log Viewer"):
        super().__init__(parent, title=title)
        self.geometry("800x600")
        textbox = ctk.CTkTextbox(self, wrap="word", font=("Courier New", 12))
        textbox.pack(expand=True, fill="both", padx=10, pady=10)
        textbox.insert("1.0", log_content)
        textbox.configure(state="disabled")
        ctk.CTkButton(self, text="Close", command=self._on_cancel).pack(pady=10)