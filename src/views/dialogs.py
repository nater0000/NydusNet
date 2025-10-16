import customtkinter as ctk
import qrcode
from PIL import Image
import logging
import re
import os

# --- A simple Tooltip class for the '?' buttons ---
class ToolTip(ctk.CTkToplevel):
    def __init__(self, widget, text):
        super().__init__(widget)
        self.widget = widget
        self.text = text
        self.withdraw()
        self.overrideredirect(True)
        self.label = ctk.CTkLabel(self, text=self.text, corner_radius=5, fg_color="#3D3D3D", wraplength=200)
        self.label.pack(ipadx=5, ipady=3)
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)

    def show(self, event):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.geometry(f"+{x}+{y}")
        self.deiconify()

    def hide(self, event):
        self.withdraw()

class BaseDialog(ctk.CTkToplevel):
    """A base class for all modal dialogs in the application."""
    def __init__(self, parent, title="Dialog"):
        super().__init__(parent)
        self.title(title)
        self.result = None
        self._parent = parent
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.after(50, self._center_window)
        
    def _center_window(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.geometry(f"+{x}+{y}")

    def _on_ok(self, event=None):
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()

    def get_input(self):
        self.wait_window()
        return self.result

class UnlockDialog(BaseDialog):
    def __init__(self, parent, first_run: bool = False, controller=None, title=None):
        title = title or ("Create Master Password" if first_run else "Unlock NydusNet")
        super().__init__(parent, title=title)
        self.controller = controller
        self.first_run = first_run
        
        try:
            # Use a path relative to this file's location
            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            show_icon_path = os.path.join(base_path, "resources", "images", "eye-show.png")
            hide_icon_path = os.path.join(base_path, "resources", "images", "eye-hide.png")
            self.show_icon = ctk.CTkImage(Image.open(show_icon_path), size=(20, 20))
            self.hide_icon = ctk.CTkImage(Image.open(hide_icon_path), size=(20, 20))
            self.use_image_icons = True
        except Exception:
            logging.warning("Eyeball icons not found. Show/hide password feature will use text.")
            self.show_icon = "👁️"
            self.hide_icon = "🔒"
            self.use_image_icons = False

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
        ctk.CTkLabel(self, text="Enter Master Password:").pack(padx=20, pady=(20, 0))
        
        entry_frame = ctk.CTkFrame(self, fg_color="transparent")
        entry_frame.pack(padx=20, pady=10)
        self.entry1 = ctk.CTkEntry(entry_frame, show="*", width=250)
        self.entry1.pack(side="left")
        self.entry1.bind("<Return>", self._on_ok)
        self.after(10, self.entry1.focus_set)
        
        toggle_btn1 = ctk.CTkButton(entry_frame, image=self.show_icon if self.use_image_icons else None, text=self.show_icon if not self.use_image_icons else "", width=28,
                                    command=lambda: self._toggle_password_visibility(self.entry1, toggle_btn1))
        toggle_btn1.pack(side="left", padx=(5, 0))

        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(padx=20, pady=(10, 20))
        ok_button = ctk.CTkButton(button_frame, text="Unlock", command=self._on_ok)
        ok_button.pack(side="left", padx=10)
        forgot_button = ctk.CTkButton(button_frame, text="Forgot Password?", command=self._on_forgot)
        forgot_button.pack(side="left", padx=10)

    def _create_password_setup_ui(self):
        ctk.CTkLabel(self, text="Create a New Master Password:").pack(padx=20, pady=(20, 0))
        
        entry_frame1 = ctk.CTkFrame(self, fg_color="transparent")
        entry_frame1.pack(padx=20, pady=5)
        self.entry1 = ctk.CTkEntry(entry_frame1, show="*", width=250)
        self.entry1.pack(side="left")
        self.after(10, self.entry1.focus_set)
        toggle_btn1 = ctk.CTkButton(entry_frame1, image=self.show_icon if self.use_image_icons else None, text=self.show_icon if not self.use_image_icons else "", width=28,
                                    command=lambda: self._toggle_password_visibility(self.entry1, toggle_btn1))
        toggle_btn1.pack(side="left", padx=(5, 0))

        ctk.CTkLabel(self, text="Confirm Master Password:").pack(padx=20, pady=(10, 0))
        
        entry_frame2 = ctk.CTkFrame(self, fg_color="transparent")
        entry_frame2.pack(padx=20, pady=5)
        self.entry2 = ctk.CTkEntry(entry_frame2, show="*", width=250)
        self.entry2.pack(side="left")
        self.entry2.bind("<Return>", self._on_ok)
        toggle_btn2 = ctk.CTkButton(entry_frame2, image=self.show_icon if self.use_image_icons else None, text=self.show_icon if not self.use_image_icons else "", width=28,
                                    command=lambda: self._toggle_password_visibility(self.entry2, toggle_btn2))
        toggle_btn2.pack(side="left", padx=(5, 0))

        allowed_chars_text = "Allowed characters: A-Z, a-z, 0-9, and !@#$%^&*()_+-=[]{}|;:,.<>?"
        ctk.CTkLabel(self, text=allowed_chars_text, font=("", 10), wraplength=300).pack(padx=20, pady=5)

        ok_button = ctk.CTkButton(self, text="Create", command=self._on_ok)
        ok_button.pack(padx=20, pady=20)

    def _on_ok(self, event=None):
        password = self.entry1.get()
        if self.first_run:
            password2 = self.entry2.get()
            allowed_chars_pattern = r"^[A-Za-z0-9!@#$%^&*()_+\-=\[\]{}|;:,.<>?]*$"
            
            if password != password2:
                ErrorDialog(self, message="Passwords do not match.")
                return
            if not password:
                ErrorDialog(self, message="Password cannot be empty.")
                return
            if not re.fullmatch(allowed_chars_pattern, password):
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
        
class ServerDialog(BaseDialog):
    def __init__(self, parent, title="Server Details", initial_data=None):
        super().__init__(parent, title=title)
        self.initial_data = initial_data or {}
        
        ctk.CTkLabel(self, text="Server Name:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.name_entry = ctk.CTkEntry(self, width=250)
        self.name_entry.grid(row=0, column=1, padx=10, pady=5)
        self.name_entry.insert(0, self.initial_data.get("name", ""))
        
        ctk.CTkLabel(self, text="IP Address:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.ip_entry = ctk.CTkEntry(self, width=250)
        self.ip_entry.grid(row=1, column=1, padx=10, pady=5)
        self.ip_entry.insert(0, self.initial_data.get("ip_address", ""))

        ctk.CTkLabel(self, text="Sudo Username:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.user_entry = ctk.CTkEntry(self, width=250)
        self.user_entry.grid(row=2, column=1, padx=10, pady=5)
        self.user_entry.insert(0, self.initial_data.get("user", "root"))

        ctk.CTkLabel(self, text="SSH Password:").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.pass_entry = ctk.CTkEntry(self, show="*", width=250)
        self.pass_entry.grid(row=3, column=1, padx=10, pady=5)
        
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=4, column=0, columnspan=2, padx=20, pady=20)
        
        ok_button = ctk.CTkButton(button_frame, text="Save", command=self._on_ok)
        ok_button.pack(side="left", padx=10)
        
        cancel_button = ctk.CTkButton(button_frame, text="Cancel", command=self._on_cancel)
        cancel_button.pack(side="left", padx=10)

    def _on_ok(self, event=None):
        name = self.name_entry.get()
        ip_address = self.ip_entry.get()
        user = self.user_entry.get()
        password = self.pass_entry.get()

        if not all([name, ip_address, user]):
            ErrorDialog(self, message="Name, IP Address, and Username are required.")
            return

        # Only include password if it was entered, allowing edits without re-typing it
        self.result = self.initial_data.copy()
        self.result.update({
            "type": "server",
            "name": name,
            "ip_address": ip_address,
            "user": user
        })
        if password:
            self.result["password"] = password

        super()._on_ok()
        
class TunnelDialog(BaseDialog):
    def __init__(self, parent, controller, title="Tunnel Details", initial_data=None):
        super().__init__(parent, title=title)
        self.controller = controller
        self.initial_data = initial_data or {}
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Server:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.server_map = {s['name']: s['id'] for s in self.controller.get_servers()}
        server_names = list(self.server_map.keys()) or ["No servers configured"]
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
        local_dest_frame.grid(row=4, column=1, padx=10, pady=5, sticky="ew")
        self.local_dest_entry = ctk.CTkEntry(local_dest_frame)
        self.local_dest_entry.pack(side="left", fill="x", expand=True)
        local_dest_help = ctk.CTkLabel(local_dest_frame, text="?", width=20, cursor="hand2")
        local_dest_help.pack(side="left", padx=(5,0))
        ToolTip(local_dest_help, "Local address and port (e.g., 'localhost:3000').")

        # Set initial values
        if not self.server_map: self.server_menu.configure(state="disabled")
        elif self.initial_data.get("server_id"):
             for name, sid in self.server_map.items():
                if sid == self.initial_data["server_id"]: self.server_menu.set(name)

        if self.initial_data.get("assigned_client_id"):
            for name, cid in self.client_map.items():
                if cid == self.initial_data["assigned_client_id"]:
                    self.client_menu.set(name)
        else: # Default to this device if not set
            my_name = f"{self.controller.get_my_device_name()} (This Device)"
            if my_name in client_names:
                self.client_menu.set(my_name)

        self.hostname_entry.insert(0, self.initial_data.get("hostname", ""))
        self.remote_port_entry.insert(0, str(self.initial_data.get("remote_port", "")))
        self.local_dest_entry.insert(0, self.initial_data.get("local_destination", "localhost:"))
        
        self.enabled_var = ctk.BooleanVar(value=self.initial_data.get("enabled", False))
        self.enabled_check = ctk.CTkCheckBox(self, text="Start tunnel now", variable=self.enabled_var)
        self.enabled_check.grid(row=5, column=1, padx=10, pady=10, sticky="w")

        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=6, column=0, columnspan=2, padx=20, pady=20)
        ok_button = ctk.CTkButton(button_frame, text="Save", command=self._on_ok)
        ok_button.pack(side="left", padx=10)
        cancel_button = ctk.CTkButton(button_frame, text="Cancel", command=self._on_cancel)
        cancel_button.pack(side="left", padx=10)

    def _on_ok(self, event=None):
        try:
            if not self.server_map:
                ErrorDialog(self, message="Cannot save. Add a server in Settings first.")
                return

            server_id = self.server_map.get(self.server_menu.get())
            client_id = self.client_map.get(self.client_menu.get())
            if not server_id or not client_id:
                 ErrorDialog(self, message="A valid Server and Managing Device must be selected.")
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
                "enabled": self.enabled_var.get(),
            })
            super()._on_ok()
        except ValueError:
            ErrorDialog(self, message="Invalid input: Remote Port must be a number.")
        except Exception as e:
            logging.error(f"Tunnel Dialog Validation Error: {e}")
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
        
        close_button = ctk.CTkButton(self, text="Close", command=self._on_cancel)
        close_button.pack(pady=20)

class ConfirmationDialog(BaseDialog):
    def __init__(self, parent, title="Confirm", message="Are you sure?"):
        super().__init__(parent, title=title)
        ctk.CTkLabel(self, text=message, wraplength=300).pack(padx=20, pady=20)
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(padx=20, pady=20)
        yes_button = ctk.CTkButton(button_frame, text="Yes", command=self._on_ok)
        yes_button.pack(side="left", padx=10)
        no_button = ctk.CTkButton(button_frame, text="No", command=self._on_cancel)
        no_button.pack(side="left", padx=10)

    def _on_ok(self, event=None):
        self.result = True
        super()._on_ok()

class RecoveryKeyDialog(BaseDialog):
    def __init__(self, parent, recovery_key: str = None, input_mode: bool = False, title=None):
        title = title or ("Enter Recovery Key" if input_mode else "Save Your Recovery Key!")
        super().__init__(parent, title=title)
        
        if input_mode:
            message = "Enter your recovery key to reset your password:"
            ctk.CTkLabel(self, text=message, wraplength=350).pack(padx=20, pady=10)
            self.key_entry = ctk.CTkEntry(self, width=350, font=("Courier", 14))
            self.key_entry.pack(padx=20, pady=10)
            self.after(10, self.key_entry.focus_set)
            self.key_entry.bind("<Return>", self._on_ok)
            button_frame = ctk.CTkFrame(self, fg_color="transparent")
            button_frame.pack(padx=20, pady=20)
            ok_button = ctk.CTkButton(button_frame, text="OK", command=self._on_ok)
            ok_button.pack(side="left", padx=10)
            cancel_button = ctk.CTkButton(button_frame, text="Cancel", command=self._on_cancel)
            cancel_button.pack(side="left", padx=10)
        else:
            message = "This is your recovery key. Save it in a secure place."
            ctk.CTkLabel(self, text=message, wraplength=350).pack(padx=20, pady=10)
            key_entry = ctk.CTkEntry(self, width=350, font=("Courier", 14))
            key_entry.insert(0, recovery_key)
            key_entry.configure(state="readonly")
            key_entry.pack(padx=20, pady=10)
            self.confirm_check_var = ctk.StringVar(value="off")
            confirm_check = ctk.CTkCheckBox(self, text="I have saved this key in a secure place.",
                                            variable=self.confirm_check_var, onvalue="on", offvalue="off")
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

        close_button = ctk.CTkButton(self, text="Close", command=self._on_cancel)
        close_button.pack(pady=10)

